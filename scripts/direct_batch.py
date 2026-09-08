#!/usr/bin/env python3
"""Validate and run one bounded, sequential KIE image batch."""
from __future__ import annotations
import argparse
import contextlib
import io
import json
from pathlib import Path
import sys

import batch_render as batch
import render
from logo_reference import validate_manifest_logo


def render_args(job, validate):
    input_path = batch.write_render_input(job)
    return argparse.Namespace(
        input_json=str(input_path), prompt=None, aspect_ratio=None, size=None,
        resolution=None, quality=None, reference=[], output=str(job["output"]),
        api_base=None, upload_base=None, retries=3, poll_timeout=900,
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


def execute(args):
    manifest_path = args.manifest.expanduser().resolve()
    manifest = batch.load_manifest(manifest_path)
    config = json.loads(args.config.read_text())
    validate_manifest_logo(manifest, config)
    if len(config.get("placements", [])) != 1:
        raise ValueError("saved config must have exactly one placement")
    jobs = manifest["jobs"]
    if len(jobs) > 20 or (len(jobs) > 12 and args.approved_count != len(jobs)):
        raise ValueError("batch limit is 12; explicit --approved-count permits up to 20")
    outputs = [str(Path(j["output"]).expanduser().resolve()) for j in jobs]
    if len(set(outputs)) != len(outputs):
        raise ValueError("each job must use a unique output path")
    for job in jobs:
        invoke(job, True)
    if args.validate_only:
        print(json.dumps({"valid": True, "candidate_count": len(jobs)}))
        return 0
    if not args.approved_in_current_task:
        raise ValueError("paid KIE generation requires --approved-in-current-task")
    states, results = {}, []
    result_path = manifest_path.parent / "image-render-result.json"
    pending = list(jobs)
    failed = []
    try:
        while pending:
            ready = next((j for j in pending if all(states.get(str(d)) == "completed" for d in j.get("depends_on", []))), None)
            if ready is None:
                raise ValueError("cyclic or failed dependencies")
            result = invoke(ready, False)
            states[str(ready["job_id"])] = "completed"
            results.append({"job_id": ready["job_id"], **result})
            pending.remove(ready)
            save_result(result_path, manifest, states, results, failed)
    except (Exception, KeyboardInterrupt) as exc:
        failed.append({"job_id": ready["job_id"] if ready else None, "error": str(exc)})
        save_result(result_path, manifest, states, results, failed)
        raise
    save_result(result_path, manifest, states, results, failed)
    print(json.dumps({"status": "completed", "result": str(result_path)}))
    return 0


def save_result(path, manifest, states, results, failed):
    batch.atomic_write_json(path, {
        "request_id": manifest.get("request_id"),
        "provider": "kie-gpt-image-2",
        "status": "completed" if len(states) == len(manifest["jobs"]) else "partial_failed",
        "sets": batch.set_results(manifest["jobs"], states),
        "jobs": results, "failed_jobs": failed,
    })


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--approved-in-current-task", action="store_true")
    parser.add_argument("--approved-count", type=int)
    args = parser.parse_args()
    try:
        with render.output_lock(args.manifest.expanduser().resolve()):
            return execute(args)
    except (ValueError, OSError, render.KieError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
