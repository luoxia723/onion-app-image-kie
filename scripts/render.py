#!/usr/bin/env python3
"""Validate, submit and resume APP image tasks directly through KIE API."""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import mimetypes
import os
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any
from contextlib import contextmanager


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
from logo_reference import logo_prompt_rule, validate_asset_reference_bindings, validate_logo_prompt_rule  # noqa: E402
from kie_model import MODEL, RESOLUTION, ASPECT_RATIOS, ESTIMATED_CREDITS_PER_IMAGE, normalize_resolution, nearest_aspect_ratio, geometry_report, cover_crop_report  # noqa: E402


DEFAULT_API_BASE = "https://api.kie.ai"
DEFAULT_UPLOAD_BASE = "https://kieai.redpandaai.co"
RESOLUTION_CHOICES = {RESOLUTION}
LEGACY_QUALITY_CHOICES = {"low", "medium", "high"}
ENV_FILE = Path.home() / ".config" / "onion-app-image-kie" / ".env"
SIZE_RE = re.compile(r"^([1-9]\d*)x([1-9]\d*)$")
MAX_REFERENCE_IMAGES = 8
MAX_REFERENCE_BYTES = 10 * 1024 * 1024
DEFAULT_POLL_TIMEOUT = 900



class KieError(Exception):
    def __init__(self, message: str, exit_code: int = 3, *, uncertain_submit: bool = False):
        super().__init__(message)
        self.exit_code = exit_code
        self.uncertain_submit = uncertain_submit


def log(level: str, message: str) -> None:
    print(f"[{level}] {message}", file=sys.stderr)


def load_dotenv_if_exists(path: Path) -> bool:
    """Load KEY=VALUE lines without overriding existing environment values."""
    path = Path(path).expanduser()
    if not path.is_file():
        return False
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if not key or key in os.environ:
            continue
        lowered = value.lower()
        if "你的" in value or "占位" in value or lowered in {"sk-xxx", "sk-your-key", "your-key"}:
            continue
        os.environ[key] = value
    return True


def autoload_dotenv() -> None:
    load_dotenv_if_exists(ENV_FILE)


def find_project_root(start: Path) -> Path:
    return Path(os.environ.get("ONION_IMAGE_WORKSPACE", Path.cwd())).expanduser().resolve()


def resolve_reference_path(path: str | Path, project_root: Path, skill_dir: Path) -> Path:
    p = Path(path).expanduser()
    if p.is_absolute():
        return p.resolve()
    candidates = [(Path.cwd() / p).resolve(), (project_root / p).resolve(), (skill_dir / p).resolve()]
    path_text = str(path)
    if path_text.startswith("Skills/03_内容生成相关/onion-app-image/"):
        candidates.append((project_root / p).resolve())
    if path_text.startswith(".agents/skills/onion-app-image/"):
        candidates.append((project_root / p).resolve())
    if path_text.startswith("assets/"):
        candidates.append((skill_dir / p).resolve())
    if path_text.startswith("shared/assets/"):
        candidates.append((skill_dir / Path(path_text.removeprefix("shared/assets/"))).resolve())
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[-1]


def normalize_reference_item(item: object, index: int) -> dict[str, Any]:
    if isinstance(item, str):
        return {"path": item, "label": f"参考图{index}", "role": "参考图", "asset_id": None, "strict_label": False}
    if isinstance(item, dict):
        path = item.get("path") or item.get("file") or item.get("src")
        if not path or not str(path).strip():
            raise ValueError(f"reference_images[{index - 1}] must include path")
        label = str(item.get("label") or f"参考图{index}").strip()
        if not label:
            raise ValueError(f"reference_images[{index - 1}] label must not be empty")
        return {
            "path": str(path),
            "label": label,
            "role": str(item.get("role") or item.get("prompt_role") or "参考图").strip(),
            "asset_id": item.get("asset_id"),
            "strict_label": bool(item.get("label")),
        }
    raise ValueError(f"reference_images[{index - 1}] must be a string path or object")


def normalize_reference_items(items: list[object]) -> list[dict[str, Any]]:
    if len(items) > MAX_REFERENCE_IMAGES:
        raise ValueError(f"reference_images supports at most {MAX_REFERENCE_IMAGES} files")
    normalized = [normalize_reference_item(item, index) for index, item in enumerate(items, start=1)]
    labels = [item["label"] for item in normalized]
    duplicates = sorted({label for label in labels if labels.count(label) > 1})
    if duplicates:
        raise ValueError("duplicate reference labels: " + ", ".join(duplicates))
    return normalized


def validate_reference_labels(prompt: str, reference_items: list[dict[str, Any]]) -> None:
    missing = [item["label"] for item in reference_items if item.get("strict_label") and item["label"] not in prompt]
    if missing:
        raise ValueError("prompt must mention every explicitly labeled reference image: " + ", ".join(missing))


def validate_size_label(size: str) -> str:
    normalized = str(size or "").strip().lower()
    match = SIZE_RE.match(normalized)
    if not match:
        raise ValueError("size must be formatted as WIDTHxHEIGHT, for example 1568x672")
    return f"{int(match.group(1))}x{int(match.group(2))}"


def validate_legacy_quality(value: str | None) -> str | None:
    if value is None or not str(value).strip():
        return None
    quality = str(value).strip().lower()
    if quality not in LEGACY_QUALITY_CHOICES:
        raise ValueError(f"legacy quality must be one of {', '.join(sorted(LEGACY_QUALITY_CHOICES))}")
    return quality


def generation_geometry(explicit_size: str, requested_ratio: str) -> tuple[str, str]:
    if explicit_size:
        size_label = validate_size_label(explicit_size)
        width, height = (int(part) for part in size_label.split("x", 1))
        selected = nearest_aspect_ratio(width, height)
        if requested_ratio and requested_ratio != selected:
            raise ValueError(f"aspect_ratio conflicts with target size; expected {selected}")
        return size_label, selected
    if requested_ratio not in ASPECT_RATIOS:
        raise ValueError(
            f"aspect_ratio must be one of {', '.join(sorted(ASPECT_RATIOS))}, or pass --size WIDTHxHEIGHT"
        )
    # KIE returns the actual pixel dimensions; 1K is a tier, not exact dimensions.
    return "", requested_ratio


def json_request(url: str, api_key: str, payload: dict[str, Any] | None = None, *, method: str = "POST") -> urllib.request.Request:
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "User-Agent": "onion-ad-plugin/1.1 (+https://kie.ai)",
    }
    if data is not None:
        headers["Content-Type"] = "application/json"
    return urllib.request.Request(url, method=method, headers=headers, data=data)


def build_create_request(
    api_base: str,
    api_key: str,
    prompt: str,
    aspect_ratio: str,
    resolution: str,
    input_urls: list[str] | None = None,
) -> urllib.request.Request:
    normalize_resolution(resolution)
    if aspect_ratio not in ASPECT_RATIOS:
        raise ValueError("unsupported Flare 1K aspect_ratio")
    if not input_urls:
        raise ValueError("Flare image-to-image requires at least one reference image; no model fallback is allowed")
    task_input: dict[str, Any] = {"prompt": prompt, "aspect_ratio": aspect_ratio, "resolution": RESOLUTION, "background": "opaque", "input_urls": input_urls}
    return json_request(
        f"{api_base.rstrip('/')}/api/v1/jobs/createTask",
        api_key,
        {"model": MODEL, "input": task_input},
    )


def build_status_request(api_base: str, api_key: str, task_id: str) -> urllib.request.Request:
    query = urllib.parse.urlencode({"taskId": task_id})
    return json_request(f"{api_base.rstrip('/')}/api/v1/jobs/recordInfo?{query}", api_key, method="GET")


def build_upload_request(upload_base: str, api_key: str, path: Path) -> urllib.request.Request:
    mime_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    payload = {
        "base64Data": f"data:{mime_type};base64,{encoded}",
        "uploadPath": "onion-ad/references",
        "fileName": hashlib.sha256(path.read_bytes()).hexdigest() + path.suffix.lower(),
    }
    return json_request(f"{upload_base.rstrip('/')}/api/file-base64-upload", api_key, payload)


def _message_from_body(body: dict[str, Any]) -> str:
    return str(body.get("msg") or body.get("message") or body.get("error") or "unknown KIE error")


def _raise_for_api_code(body: dict[str, Any], operation: str) -> None:
    code = body.get("code")
    success = body.get("success")
    if (code in (None, 200)) and success is not False:
        return
    try:
        numeric = int(code)
    except (TypeError, ValueError):
        numeric = 500
    message = _message_from_body(body)
    if numeric == 401:
        raise KieError("KIE_API_KEY invalid or expired", 2)
    if numeric == 402:
        raise KieError("KIE account credits are insufficient", 3)
    if numeric in {400, 404, 422, 433, 501, 505}:
        raise KieError(f"{operation} rejected ({numeric}): {message}", 4)
    raise KieError(f"{operation} failed ({numeric}): {message}", 3)


def request_json(
    req: urllib.request.Request,
    retries: int = 3,
    *,
    operation: str = "KIE request",
    retry_network: bool = True,
) -> dict[str, Any]:
    waits = [1, 3, 9]
    for attempt in range(1, max(1, retries) + 1):
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            if not isinstance(body, dict):
                raise KieError(f"{operation} returned non-object JSON", 3)
            _raise_for_api_code(body, operation)
            return body
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            if exc.code == 401:
                raise KieError("KIE_API_KEY invalid or expired", 2)
            if exc.code == 402:
                raise KieError("KIE account credits are insufficient", 3)
            if exc.code in {400, 404, 422, 433}:
                raise KieError(f"{operation} rejected: HTTP {exc.code}: {raw[:500]}", 4)
            if (exc.code == 429 or 500 <= exc.code <= 599) and attempt < retries:
                wait = waits[min(attempt - 1, len(waits) - 1)]
                log("WARN", f"{operation} HTTP {exc.code}; retrying in {wait}s ({attempt}/{retries})")
                time.sleep(wait)
                continue
            raise KieError(f"{operation} failed: HTTP {exc.code}: {raw[:500]}", 3)
        except (urllib.error.URLError, TimeoutError) as exc:
            if retry_network and attempt < retries:
                wait = waits[min(attempt - 1, len(waits) - 1)]
                log("WARN", f"{operation} network error; retrying in {wait}s ({attempt}/{retries})")
                time.sleep(wait)
                continue
            raise KieError(
                f"{operation} network error: {exc}",
                3,
                uncertain_submit=not retry_network,
            )
        except json.JSONDecodeError as exc:
            raise KieError(f"{operation} returned invalid JSON: {exc}", 3)
    raise KieError(f"{operation} failed after {retries} attempts", 3)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def request_fingerprint(model: str, prompt: str, references: list[Path], aspect_ratio: str, resolution: str) -> str:
    payload = {
        "model": model,
        "prompt": prompt,
        "reference_sha256": [sha256_file(path) for path in references],
        "aspect_ratio": aspect_ratio,
        "resolution": resolution,
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def task_state_path(output: Path) -> Path:
    return output.with_suffix(output.suffix + ".kie-task.json")


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def load_task_state(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise KieError(f"invalid KIE task state {path}: {exc}", 1)
    if not isinstance(value, dict) or not value:
        raise KieError(f"invalid KIE task state {path}: expected a non-empty JSON object", 1)
    return value


def load_output_state(output: Path) -> dict[str, Any]:
    state = load_task_state(task_state_path(output))
    if output.exists() and not state:
        raise ValueError("existing output has no task state; use a new output path")
    if state and not state.get("task_id"):
        raise KieError(f"previous KIE task submission was uncertain; refusing to create a duplicate for {output}", 3)
    return state


UPLOAD_CACHE: dict[str, str] = {}


def upload_references(
    upload_base: str,
    api_key: str,
    paths: list[Path],
    retries: int,
    cache: dict[str, str] | None = None,
) -> list[str]:
    cache = cache if cache is not None else UPLOAD_CACHE
    urls: list[str] = []
    for path in paths:
        size = path.stat().st_size
        if size <= 0 or size > MAX_REFERENCE_BYTES:
            raise KieError(f"reference image must be between 1 byte and 10MB: {path}", 1)
        digest = sha256_file(path)
        if digest not in cache:
            body = request_json(
                build_upload_request(upload_base, api_key, path),
                retries,
                operation=f"upload reference {path.name}",
            )
            data = body.get("data") or {}
            url = data.get("downloadUrl") or data.get("fileUrl")
            if not url:
                raise KieError(f"upload reference {path.name} returned no download URL", 3)
            cache[digest] = str(url)
        urls.append(cache[digest])
    return urls


def parse_result_urls(value: Any) -> list[str]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise KieError(f"KIE task resultJson is invalid: {exc}", 3)
    if not isinstance(value, dict):
        return []
    urls = value.get("resultUrls") or []
    return [str(url) for url in urls if str(url).strip()] if isinstance(urls, list) else []


def poll_delay(elapsed: float) -> int:
    if elapsed < 30:
        return 3
    if elapsed < 120:
        return 8
    return 20


def poll_task(
    api_base: str,
    api_key: str,
    task_id: str,
    state_path: Path,
    state: dict[str, Any],
    retries: int,
    timeout_seconds: int,
) -> tuple[str, dict[str, Any]]:
    started = time.monotonic()
    while True:
        body = request_json(
            build_status_request(api_base, api_key, task_id),
            retries,
            operation=f"poll KIE task {task_id}",
        )
        data = body.get("data") or {}
        task_status = str(data.get("state") or "").lower()
        state.update({"status": task_status or "unknown", "task_id": task_id})
        if task_status == "success":
            urls = parse_result_urls(data.get("resultJson"))
            if not urls:
                raise KieError(f"KIE task {task_id} succeeded without resultUrls", 3)
            state["result_url"] = urls[0]
            atomic_write_json(state_path, state)
            return urls[0], data
        if task_status == "fail":
            state.update({"fail_code": data.get("failCode"), "fail_message": data.get("failMsg")})
            atomic_write_json(state_path, state)
            raise KieError(
                f"KIE task failed ({data.get('failCode') or 'unknown'}): {data.get('failMsg') or 'unknown error'}",
                4,
            )
        if task_status not in {"waiting", "queuing", "generating"}:
            atomic_write_json(state_path, state)
            raise KieError(f"KIE task {task_id} returned unknown state: {task_status or 'empty'}", 3)
        atomic_write_json(state_path, state)
        elapsed = time.monotonic() - started
        if elapsed >= timeout_seconds:
            state["status"] = "poll_timeout"
            atomic_write_json(state_path, state)
            raise KieError(f"KIE task {task_id} did not finish within {timeout_seconds}s; rerun to resume it", 3)
        time.sleep(min(poll_delay(elapsed), max(0.0, timeout_seconds - elapsed)))


def download_image(url: str, output_path: str | Path) -> Path:
    output = Path(output_path).expanduser()
    if not output.is_absolute():
        output = (Path.cwd() / output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "image/avif,image/webp,image/png,image/jpeg,*/*;q=0.8",
                "User-Agent": "onion-ad-plugin/1.1 (+https://kie.ai)",
            },
        )
        with urllib.request.urlopen(request, timeout=300) as resp:
            image_bytes = resp.read()
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
        raise KieError(f"download KIE result failed: {exc}", 3)
    if not image_bytes:
        raise KieError("download KIE result returned an empty file", 3)
    try:
        from PIL import Image

        with Image.open(io.BytesIO(image_bytes)) as image:
            image.load()
            normalized = image.convert("RGBA") if "A" in image.getbands() else image.convert("RGB")
            temp = output.with_suffix(output.suffix + ".tmp")
            normalized.save(temp, format="PNG")
            if temp.stat().st_size <= 0:
                raise OSError("converted PNG is empty")
            temp.replace(output)
    except Exception as exc:
        temp = output.with_suffix(output.suffix + ".tmp")
        temp.unlink(missing_ok=True)
        raise KieError(f"downloaded KIE result is not a valid image: {exc}", 3)
    return output


def load_input(args: argparse.Namespace) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if args.input_json:
        payload = json.loads(Path(args.input_json).read_text(encoding="utf-8"))
    if args.prompt:
        payload["prompt"] = args.prompt
    if args.aspect_ratio:
        payload["aspect_ratio"] = args.aspect_ratio
    if args.size:
        payload["size"] = args.size
    if args.resolution:
        payload["resolution"] = args.resolution
    if args.quality:
        payload["quality"] = args.quality
    references = list(payload.get("reference_images") or [])
    references.extend(args.reference or [])
    payload["reference_images"] = references
    return payload


def output_geometry(path: Path, target_size: str) -> dict[str, Any]:
    from PIL import Image
    with Image.open(path) as image:
        width, height = image.size
    result: dict[str, Any] = {"actual_width": width, "actual_height": height, "review_findings": []}
    if target_size:
        target_width, target_height = map(int, target_size.split("x"))
        crop_report = cover_crop_report(width, height, target_width, target_height)
        scale = max(target_width / width, target_height / height)
        result.update({"actual_crop_percent": crop_report["crop_percent"], "delivery_scale": round(scale, 3)})
        if crop_report["needs_safe_area"]:
            result["review_findings"].append(f"比例差距较大：交付预计裁切 {crop_report['crop_percent']:.1f}%，请确认生成后的构图、文字和 Logo 完整。")
        if scale >= 1.25:
            result["review_findings"].append(f"1K 原图交付时需放大约 {scale:.2f} 倍，请检查小字与边缘清晰度。")
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-json", help="JSON with prompt/reference_images/aspect_ratio or size/resolution")
    parser.add_argument("--prompt", help="Complete prompt text")
    parser.add_argument("--aspect-ratio", choices=sorted(ASPECT_RATIOS))
    parser.add_argument("--size", help="Target render size, e.g. 1568x672; mapped to the nearest KIE ratio")
    parser.add_argument("--resolution", choices=sorted(RESOLUTION_CHOICES), default=None)
    parser.add_argument("--quality", choices=sorted(LEGACY_QUALITY_CHOICES), default=None, help=argparse.SUPPRESS)
    parser.add_argument("--reference", action="append", default=[], help="Local reference image path; repeatable")
    parser.add_argument("--output", required=True, help="Output PNG path")
    parser.add_argument("--api-base", default=None, help=f"KIE task API base, default {DEFAULT_API_BASE}")
    parser.add_argument("--upload-base", default=None, help=f"KIE upload API base, default {DEFAULT_UPLOAD_BASE}")
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--poll-timeout", type=int, default=DEFAULT_POLL_TIMEOUT)
    parser.add_argument("--validate-only", action="store_true", help="Validate without calling KIE")
    parser.add_argument(
        "--approved-in-current-task",
        action="store_true",
        help="Required for a paid KIE task; current-task approval cannot come from a saved file",
    )
    return parser.parse_args()


@contextmanager
def output_lock(output):
    lock = Path(str(output) + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        lock.mkdir()
    except FileExistsError:
        raise KieError(f"output locked by another or interrupted run: {lock}", 3)
    try:
        (lock / "owner.json").write_text(json.dumps({"pid": os.getpid()}))
        yield
    finally:
        (lock / "owner.json").unlink(missing_ok=True)
        lock.rmdir()


def run(args) -> int:
    autoload_dotenv()
    try:
        payload = load_input(args)
        prompt = str(payload.get("prompt") or "").strip()
        if not prompt:
            raise ValueError("prompt is required")
        resolution = normalize_resolution(payload.get("resolution"))
        legacy_quality = validate_legacy_quality(payload.get("quality"))
        if legacy_quality:
            log("WARN", f"quality={legacy_quality} is deprecated and ignored; KIE resolution={resolution} is used")
        requested_ratio = str(payload.get("aspect_ratio") or "").strip()
        size_label, aspect_ratio = generation_geometry(str(payload.get("size") or "").strip(), requested_ratio)
        frame_layout_path = payload.get("frame_layout_path")
        if size_label and geometry_report(*map(int, size_label.split("x")))["needs_safe_area"] and not frame_layout_path:
            raise ValueError("预计裁切达到6%：缺少 frame_layout_path，先准备白底蓝框布局。")

        skill_dir = SCRIPT_DIR.parent
        project_root = find_project_root(SCRIPT_DIR)
        reference_items = normalize_reference_items(list(payload.get("reference_images", [])))
        if not reference_items:
            raise ValueError("Flare image-to-image requires at least one original Logo, IP, font or UI reference image")
        validate_reference_labels(prompt, reference_items)
        validate_asset_reference_bindings(reference_items)
        validate_logo_prompt_rule(prompt, reference_items)
        reference_paths = [
            resolve_reference_path(item["path"], project_root=project_root, skill_dir=skill_dir)
            for item in reference_items
        ]
        missing = [str(path) for path in reference_paths if not path.is_file()]
        if missing:
            raise ValueError("reference image not found: " + ", ".join(missing))
        oversized = [str(path) for path in reference_paths if path.stat().st_size <= 0 or path.stat().st_size > MAX_REFERENCE_BYTES]
        if oversized:
            raise ValueError("reference image must be between 1 byte and 10MB: " + ", ".join(oversized))
        if frame_layout_path:
            from blue_frame import validate_layout
            frame_layout_path = resolve_reference_path(frame_layout_path, project_root, skill_dir)
            validate_layout(frame_layout_path, size_label, reference_items, reference_paths, prompt,
                            inherited_base=payload.get("base_image_path"))

        output = Path(args.output).expanduser()
        if not output.is_absolute():
            output = (Path.cwd() / output).resolve()
        runtime_root = (
            project_root / "工作区" / "产物"
        ).resolve()
        if output != runtime_root and runtime_root not in output.parents:
            raise ValueError(f"output must stay under {runtime_root}")
        model = MODEL
        fingerprint = request_fingerprint(model, prompt, reference_paths, aspect_ratio, resolution)
        state_path = task_state_path(output)
        state = load_output_state(output)
        if state and state.get("fingerprint") != fingerprint:
            raise ValueError(f"existing KIE task state does not match this request; use a new output path: {state_path}")

        metadata: dict[str, Any] = {
            "valid": True,
            "filepath": str(output),
            "size_label": size_label,
            "size": size_label,
            "aspect_ratio": aspect_ratio,
            "requested_aspect_ratio": requested_ratio or "custom",
            "provider": "kie",
            "model": model,
            "resolution": resolution,
            "estimated_credits": ESTIMATED_CREDITS_PER_IMAGE,
            "pricing_basis": "user-account-region-screenshot; actual billing is provider-controlled",
            "geometry": geometry_report(*map(int, size_label.split("x")), aspect_ratio) if size_label else {"aspect_ratio": aspect_ratio, "resolution": resolution},
            "endpoint": "/api/v1/jobs/createTask",
            "reference_images": [item["path"] for item in reference_items],
            "reference_image_labels": [
                {"label": item["label"], "role": item["role"], "asset_id": item.get("asset_id"), "path": item["path"]}
                for item in reference_items
            ],
            "reference_images_resolved": [str(path) for path in reference_paths],
            "prompt_used": prompt,
            "task_state_path": str(state_path),
        }
        if frame_layout_path:
            metadata["frame_layout_path"] = str(frame_layout_path)
        if args.validate_only:
            print(json.dumps(metadata, ensure_ascii=False, indent=2))
            return 0

        if not args.approved_in_current_task:
            raise KieError(
                "paid KIE generation requires --approved-in-current-task",
                2,
            )

        api_key = str(os.environ.get("KIE_API_KEY") or "").strip()
        if not api_key:
            raise KieError("KIE_API_KEY is missing; configure ~/.config/onion-app-image-kie/.env", 2)
        api_base = args.api_base or os.environ.get("KIE_BASE_URL", DEFAULT_API_BASE)
        upload_base = args.upload_base or os.environ.get("KIE_UPLOAD_BASE_URL", DEFAULT_UPLOAD_BASE)

        if state.get("status") == "downloaded" and output.is_file():
            if state.get("sha256") == sha256_file(output):
                metadata.update({"task_id": state.get("task_id"), "sha256": state["sha256"], "byte_count": output.stat().st_size})
                metadata.update(output_geometry(output, size_label))
                if frame_layout_path:
                    from blue_frame import attach_result
                    attach_result(metadata, output, frame_layout_path)
                print(json.dumps(metadata, ensure_ascii=False))
                return 0
        result_url = str(state.get("result_url") or "")
        task_id = str(state.get("task_id") or "")
        if not task_id and state:
            raise KieError(
                f"previous KIE task submission was uncertain; refusing to create a duplicate for {output}",
                3,
            )
        if not task_id:
            input_urls = upload_references(upload_base, api_key, reference_paths, args.retries)
            state = {
                "provider": "kie",
                "fingerprint": fingerprint,
                "model": model,
                "aspect_ratio": aspect_ratio,
                "resolution": resolution,
                "status": "submitting",
            }
            atomic_write_json(state_path, state)
            try:
                created = request_json(
                    build_create_request(api_base, api_key, prompt, aspect_ratio, resolution, input_urls),
                    1,
                    operation="create KIE image task",
                    retry_network=False,
                )
            except KieError as exc:
                state["status"] = "submit_uncertain"
                atomic_write_json(state_path, state)
                raise
            task_id = str((created.get("data") or {}).get("taskId") or "")
            if not task_id:
                state["status"] = "submit_uncertain"
                atomic_write_json(state_path, state)
                raise KieError("create KIE image task returned no taskId", 3)
            state.update({"task_id": task_id, "status": "waiting"})
            atomic_write_json(state_path, state)

        if not result_url:
            result_url, task_data = poll_task(
                api_base,
                api_key,
                task_id,
                state_path,
                state,
                args.retries,
                max(1, args.poll_timeout),
            )
            metadata["credits_consumed"] = task_data.get("creditsConsumed")
        saved = download_image(result_url, output)
        state.update({"status": "downloaded", "task_id": task_id, "result_url": result_url, "sha256": sha256_file(saved)})
        atomic_write_json(state_path, state)
        metadata.update({"filepath": str(saved), "task_id": task_id, "valid": True, "sha256": sha256_file(saved), "byte_count": saved.stat().st_size})
        metadata.update(output_geometry(saved, size_label))
        if frame_layout_path:
            from blue_frame import attach_result
            attach_result(metadata, saved, frame_layout_path)
        print(json.dumps(metadata, ensure_ascii=False, indent=2))
        return 0
    except ValueError as exc:
        log("ERROR", str(exc))
        return 1
    except KieError as exc:
        log("ERROR", str(exc))
        return exc.exit_code


def main() -> int:
    args = parse_args()
    if args.validate_only:
        return run(args)
    try:
        with output_lock(Path(args.output).expanduser().resolve()):
            return run(args)
    except KieError as exc:
        log("ERROR", str(exc))
        return exc.exit_code


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
