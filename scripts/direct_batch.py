#!/usr/bin/env python3
"""Preflight a bounded KIE batch, then run independent jobs in isolated workers."""
from __future__ import annotations
import argparse
import contextlib
import io
import os
import hashlib
import re
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
import json
from pathlib import Path
import sys

import batch_render as batch
import render
from logo_reference import validate_manifest_logo
from kie_model import PROVIDER, RESOLUTION, ESTIMATED_CREDITS_PER_IMAGE, nearest_aspect_ratio, geometry_report
from series_chain import validate_series
from visual_directions import validate_visual_plan
from execution_policy import normalize_policy


def render_args(job, validate):
    input_path = batch.write_render_input(job)
    return argparse.Namespace(
        input_json=str(input_path), prompt=None, aspect_ratio=None, size=None,
        resolution=None, quality=None, reference=[], output=str(job["output"]),
        api_base=None, upload_base=None, retries=3, poll_timeout=render.DEFAULT_POLL_TIMEOUT,
        validate_only=validate, approved_in_current_task=not validate,
    )


def invoke(job, validate):
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        if validate:
            code = render.run(render_args(job, True))
        else:
            with render.output_lock(Path(job["output"]).expanduser().resolve()):
                code = render.run(render_args(job, False))
    if code:
        raise render.KieError(f"job {job['job_id']} stopped; retain its task state", code)
    return json.loads(output.getvalue())


_UPLOAD_LOCK = threading.Lock()


def invoke_paid(job, policy):
    """Workers have separate stdout, model state and output locks."""
    cache_path = Path(policy["upload_cache_path"])
    state = render.load_output_state(Path(job["output"]))
    if state.get("status") == "restart_ready" and policy["max_timeout_restarts"] < state["timeout_restarts"]:
        raise render.KieError("timeout replacement is not authorized for this configuration", 3)
    if not state.get("task_id"):
        render.autoload_dotenv()
        key = os.environ.get("KIE_API_KEY", "").strip()
        if not key:
            raise render.KieError("KIE_API_KEY is missing", 2)
        refs = render.normalize_reference_items(job.get("references") or job.get("reference_images") or [])
        paths = [render.resolve_reference_path(ref["path"], batch.repository_root(), render.SCRIPT_DIR.parent) for ref in refs]
        with _UPLOAD_LOCK:
            cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
            render.upload_references(os.environ.get("KIE_UPLOAD_BASE_URL", render.DEFAULT_UPLOAD_BASE), key, paths, 3, cache=cache)
            batch.atomic_write_json(cache_path, cache)
    input_path = batch.write_render_input(job)
    command = [sys.executable, str(render.SCRIPT_DIR / "render.py"), "--input-json", str(input_path),
               "--output", str(job["output"]), "--poll-timeout", str(policy["generation_timeout_seconds"]),
               "--max-timeout-restarts", str(policy["max_timeout_restarts"]), "--upload-cache", str(cache_path),
               "--approved-in-current-task"]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.stderr:
        Path(job["output"]).with_suffix(".render.log").write_text(result.stderr)
    if result.returncode:
        raise render.KieError(f"job {job['job_id']} stopped; retain its task state: {result.stderr.strip()}", result.returncode)
    return json.loads(result.stdout)


def execution_policy(args, config, manifest_path):
    policy = normalize_policy(config.get("execution_policy"), legacy="execution_policy" not in config)
    if getattr(args, "concurrency", None) is not None:
        policy = normalize_policy({**policy, "concurrency": args.concurrency})
    identity = str(config.get("request_id") or hashlib.sha256(str(manifest_path).encode()).hexdigest()[:16])
    identity = re.sub(r"[^a-zA-Z0-9_.-]", "_", identity).strip(".") or "batch"
    policy["upload_cache_path"] = str(batch.repository_root() / ".runtime" / identity / "reference-upload-cache.json")
    return policy


def execute(args):
    manifest_path = args.manifest.expanduser().resolve()
    manifest = batch.load_manifest(manifest_path)
    config = json.loads(args.config.read_text())
    validate_manifest_logo(manifest, config)
    if len(config.get("placements", [])) != 1:
        raise ValueError("saved config must have exactly one placement")
    validate_visual_plan(manifest, config)
    jobs = manifest["jobs"]
    policy = execution_policy(args, config, manifest_path)
    branches = validate_series(manifest, config)
    placement = config["placements"][0]
    width, height = placement.get("target_width"), placement.get("target_height")
    if width and height:
        for job in jobs:
            if job.get("target_width", width) != width or job.get("target_height", height) != height:
                raise ValueError("job target dimensions conflict with saved placement")
            job.update({"target_width": width, "target_height": height, "size": f"{width}x{height}", "aspect_ratio": nearest_aspect_ratio(width, height)})
            if geometry_report(width, height)["needs_safe_area"] and not job.get("frame_layout_path"):
                raise ValueError("预计裁切达到6%：先运行 scripts/blue_frame.py 准备参考图，再为job填写 frame_layout_path 和对应Prompt。")
    if len(jobs) > 20 or (len(jobs) > 12 and args.approved_count != len(jobs)):
        raise ValueError("batch limit is 12; explicit --approved-count permits up to 20")
    outputs = [str(Path(j["output"]).expanduser().resolve()) for j in jobs]
    if len(set(outputs)) != len(outputs):
        raise ValueError("each job must use a unique output path")
    for job in jobs:
        if job["job_id"] in branches:
            # The dependency and its future path are validated now. Its actual
            # bytes/fingerprint are checked only after this batch creates it.
            refs = render.normalize_reference_items(job.get("references") or job.get("reference_images") or [])
            render.normalize_resolution(job.get("resolution"))
            render.validate_legacy_quality(job.get("quality"))
            render.validate_reference_labels(job["prompt"], refs)
            render.generation_geometry(str(job.get("size") or ""), str(job.get("aspect_ratio") or ""))
            render.load_output_state(Path(job["output"]).expanduser().resolve())
            if job.get("frame_layout_path"):
                from blue_frame import has_prompt_rule
                if not has_prompt_rule(job["prompt"], "参考图1"):
                    raise ValueError("branch prompt must inherit the base blue-frame range")
        else:
            invoke(job, True)
    if args.validate_only:
        print(json.dumps({"valid": True, "candidate_count": len(jobs), "model": render.MODEL, "resolution": RESOLUTION, "estimated_credits": len(jobs) * ESTIMATED_CREDITS_PER_IMAGE, "execution_policy": {k: v for k, v in policy.items() if k != "upload_cache_path"}, "max_estimated_credits": len(jobs) * ESTIMATED_CREDITS_PER_IMAGE * (1 + policy["max_timeout_restarts"])}))
        return 0
    if not args.approved_in_current_task:
        raise ValueError("paid KIE generation requires --approved-in-current-task")
    states, results = {}, []
    result_path = manifest_path.parent / "image-render-result.json"
    pending = list(jobs)
    failed = []
    error = None
    with ThreadPoolExecutor(max_workers=policy["concurrency"]) as pool:
        active = {}
        while pending or active:
            if error is None:
                ready = [job for job in pending if all(states.get(str(dep)) == "completed" for dep in job.get("depends_on", []))]
                for job in ready[:policy["concurrency"] - len(active)]:
                    try:
                        if job["job_id"] in branches:
                            base_path = Path(branches[job["job_id"]]["output"]).expanduser().resolve()
                            state = render.load_task_state(render.task_state_path(base_path))
                            if state.get("status") != "downloaded" or not base_path.is_file() or state.get("sha256") != render.sha256_file(base_path):
                                raise ValueError("branch base PNG must match its downloaded task receipt")
                            job["base_image_path"] = str(base_path)
                            invoke(job, True)
                        active[pool.submit(invoke_paid, job, policy)] = job
                        pending.remove(job)
                    except Exception as exc:
                        error = exc
                        failed.append({"job_id": job["job_id"], "error": str(exc)})
                        break
            if not active:
                if pending and error is None:
                    error = ValueError("cyclic or failed dependencies")
                    failed.append({"job_id": None, "error": str(error)})
                break
            done, _ = wait(active, return_when=FIRST_COMPLETED)
            for future in done:
                job = active.pop(future)
                try:
                    result = future.result()
                    states[str(job["job_id"])] = "completed"
                    results.append({"job_id": job["job_id"], **result})
                except Exception as exc:
                    error = error or exc
                    failed.append({"job_id": job["job_id"], "error": str(exc)})
            save_result(result_path, manifest, states, results, failed)
    save_result(result_path, manifest, states, results, failed)
    if error is not None:
        raise error
    print(json.dumps({"status": "completed", "result": str(result_path)}))
    return 0


def save_result(path, manifest, states, results, failed):
    sets = batch.set_results(manifest["jobs"], states)
    results_by_id = {item["job_id"]: item for item in results}
    for group in sets:
        findings = list(group.get("review_findings", []))
        completed_jobs = sorted(
            [job for job in manifest["jobs"] if job["set_id"] == group["set_id"] and states.get(job["job_id"]) == "completed"],
            key=lambda job: int(job.get("slot") or 1),
        )
        group["images"] = [results_by_id.get(job["job_id"], {}).get("candidate_filepath", job["output"]) for job in completed_jobs]
        for job in manifest["jobs"]:
            if job["set_id"] == group["set_id"]:
                findings.extend(results_by_id.get(job["job_id"], {}).get("review_findings", []))
        if findings:
            group["review_findings"] = list(dict.fromkeys(findings))
    batch.atomic_write_json(path, {
        "request_id": manifest.get("request_id"),
        "provider": PROVIDER,
        "resolution": RESOLUTION,
        "status": "completed" if len(states) == len(manifest["jobs"]) else "partial_failed",
        "sets": sets,
        "jobs": results, "failed_jobs": failed,
    })


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--approved-in-current-task", action="store_true")
    parser.add_argument("--approved-count", type=int)
    parser.add_argument("--concurrency", type=int)
    args = parser.parse_args()
    try:
        with render.output_lock(args.manifest.expanduser().resolve()):
            return execute(args)
    except (ValueError, OSError, render.KieError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
