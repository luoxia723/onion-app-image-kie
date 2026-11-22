#!/usr/bin/env python3
"""Validate, submit and resume APP image tasks directly through KIE API."""

from __future__ import annotations

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
DEFAULT_POLL_TIMEOUT = 240



class KieError(Exception):
    def __init__(self, message: str, exit_code: int = 3, *, uncertain_submit: bool = False,
                 http_status: int | None = None, provider_code: int | None = None,
                 provider_task_id: str | None = None):
        super().__init__(message)
        self.exit_code = exit_code
        self.uncertain_submit = uncertain_submit
        self.http_status = http_status
        self.provider_code = provider_code
        self.provider_task_id = provider_task_id


class GenerationTimeout(KieError):
    """The provider confirmed this task is still pending at its deadline."""


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
    model: str = MODEL,
) -> urllib.request.Request:
    normalize_resolution(resolution)
    from kie_model import provider_aspect_ratios, GPT_IMAGE_2, NANO_BANANA_REPAIR
    if aspect_ratio not in provider_aspect_ratios(model):
        raise ValueError("unsupported model 1K aspect_ratio")
    if not input_urls:
        raise ValueError("image-to-image requires at least one reference image; no model fallback is allowed")
    task_input: dict[str, Any] = {"prompt": prompt, "aspect_ratio": aspect_ratio, "resolution": RESOLUTION, "background": "opaque", "input_urls": input_urls}
    if model == NANO_BANANA_REPAIR:
        if len(input_urls) != 1:
            raise ValueError("typography repair requires one source image")
        task_input = dict(prompt=prompt, aspect_ratio=aspect_ratio, resolution=RESOLUTION, image_input=input_urls, output_format="png")
    if model==GPT_IMAGE_2: task_input.pop("background")
    # Flare defaults to PNG. Explicit output_format=png can trigger KIE's SVG validation.
    return json_request(
        f"{api_base.rstrip('/')}/api/v1/jobs/createTask",
        api_key,
        {"model": model, "input": task_input},
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


def _error_task_id(body):
    value=(body.get('data') or {}).get('taskId') if isinstance(body,dict) and isinstance(body.get('data'),dict) else None
    return value if isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9._:-]{1,200}',value) else None


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
    metadata=dict(provider_code=numeric,provider_task_id=_error_task_id(body))
    if numeric == 401:
        raise KieError("KIE_API_KEY invalid or expired", 2, **metadata)
    if numeric == 402:
        raise KieError("KIE account credits are insufficient", 3, **metadata)
    if numeric in {400, 404, 422, 433, 501, 505}:
        raise KieError(f"{operation} rejected ({numeric}): {message}", 4, **metadata)
    raise KieError(f"{operation} failed ({numeric}): {message}", 3, **metadata)


def request_json(
    req: urllib.request.Request,
    retries: int = 3,
    *,
    operation: str = "KIE request",
    retry_network: bool = True,
    request_timeout: float = 300,
    retry_deadline: float | None = None,
) -> dict[str, Any]:
    waits = [1, 3, 9]
    for attempt in range(1, max(1, retries) + 1):
        try:
            remaining = retry_deadline - time.monotonic() if retry_deadline is not None else request_timeout
            if remaining <= 0:
                raise KieError(f"{operation} exceeded its query time budget", 3)
            with urllib.request.urlopen(req, timeout=min(request_timeout, remaining)) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            if not isinstance(body, dict):
                raise KieError(f"{operation} returned non-object JSON", 3)
            _raise_for_api_code(body, operation)
            return body
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:error_body=json.loads(raw)
            except (ValueError,TypeError):error_body={}
            metadata=dict(http_status=exc.code,provider_task_id=_error_task_id(error_body))
            if exc.code == 401:
                raise KieError("KIE_API_KEY invalid or expired", 2, **metadata)
            if exc.code == 402:
                raise KieError("KIE account credits are insufficient", 3, **metadata)
            if exc.code in {400, 404, 422, 433}:
                raise KieError(f"{operation} rejected: HTTP {exc.code}: {raw[:500]}", 4, **metadata)
            if (exc.code == 429 or 500 <= exc.code <= 599) and attempt < retries:
                wait = waits[min(attempt - 1, len(waits) - 1)]
                log("WARN", f"{operation} HTTP {exc.code}; retrying in {wait}s ({attempt}/{retries})")
                time.sleep(min(wait, max(0, retry_deadline - time.monotonic())) if retry_deadline is not None else wait)
                continue
            raise KieError(f"{operation} failed: HTTP {exc.code}: {raw[:500]}", 3, **metadata)
        except (urllib.error.URLError, TimeoutError) as exc:
            if retry_network and attempt < retries:
                wait = waits[min(attempt - 1, len(waits) - 1)]
                log("WARN", f"{operation} network error; retrying in {wait}s ({attempt}/{retries})")
                time.sleep(min(wait, max(0, retry_deadline - time.monotonic())) if retry_deadline is not None else wait)
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
    if state:
        history, count = state.get("attempt_history", []), state.get("timeout_restarts", 0)
        if (type(count) is not int or count not in (0, 1) or not isinstance(history, list) or len(history) != count
                or any(not isinstance(old, dict) or not old.get("task_id") or not old.get("timeout_confirmed")
                       or old.get("fingerprint") != state.get("fingerprint") for old in history)):
            raise KieError("invalid timeout restart journal; refusing a new task", 1)
    if state and state.get("status") == "restart_ready":
        if count != 1:
            raise KieError("invalid timeout restart journal; refusing a new task", 1)
    elif state and state.get("status") == "rate_limited" and not state.get("task_id"):
        return {}
    elif state and not state.get("task_id"):
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
    *, request_fn=None,
) -> tuple[str, dict[str, Any]]:
    request=request_fn or request_json
    started = state.get("submitted_at", time.time())
    while True:
        remaining = started + timeout_seconds - time.time()
        confirming = remaining <= 0
        # A final bounded status query distinguishes a slow task from a lost connection.
        query_budget = 10 if confirming else min(30, remaining)
        body = request(
            build_status_request(api_base, api_key, task_id),
            1 if confirming else retries,
            operation=f"poll KIE task {task_id}",
            request_timeout=query_budget,
            retry_deadline=time.monotonic() + query_budget,
        )
        data = body.get("data") or {}
        task_status = str(data.get("state") or "").lower()
        state.update({"status": task_status or "unknown", "task_id": task_id})
        if type(data.get("createTime")) in (int, float) and data["createTime"] > 0:
            started = min(started, data["createTime"] / 1000)
            state["submitted_at"] = started
        else:
            state.setdefault("submitted_at", started)
        if task_status == "success":
            urls = parse_result_urls(data.get("resultJson"))
            if not urls:
                raise KieError(f"KIE task {task_id} succeeded without resultUrls", 3)
            state["result_url"] = urls[0]
            state["credits_consumed"] = data.get("creditsConsumed")
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
        elapsed = time.time() - started
        if elapsed >= timeout_seconds:
            state["status"] = "poll_timeout"
            state["timeout_confirmed"] = True
            state["provider_state_at_timeout"] = task_status
            atomic_write_json(state_path, state)
            raise GenerationTimeout(f"KIE task {task_id} is still {task_status} after {timeout_seconds}s", 3)
        time.sleep(min(poll_delay(elapsed), max(0.0, timeout_seconds - elapsed)))


def obtain_result(args, api_base, upload_base, api_key, prompt, reference_paths, fingerprint, state_path, state, aspect_ratio, resolution, *, request_fn=None, upload_fn=None):
    """Resume one active task, replacing only a confirmed timeout within its saved cap."""
    request=request_fn or request_json
    upload=upload_fn or upload_references
    from kie_model import provider_aspect_ratios
    model=getattr(args,"image_model",MODEL)
    if aspect_ratio not in provider_aspect_ratios(model):
        raise ValueError("unsupported model 1K aspect_ratio")
    limit = getattr(args, "max_timeout_restarts", 0)
    if type(limit) is not int or limit not in (0, 1):
        raise ValueError("max_timeout_restarts must be 0 or 1")
    while True:
        task_id = str(state.get("task_id") or "")
        if not task_id:
            if state and (state.get("status") != "restart_ready" or limit < state.get("timeout_restarts", 0)):
                raise KieError("submission or restart is not authorized; retain the task state", 3)
            cache_path = getattr(args, "upload_cache", None)
            cache = json.loads(Path(cache_path).read_text()) if cache_path and Path(cache_path).is_file() else None
            urls = (upload(upload_base, api_key, reference_paths, args.retries, cache=cache)
                    if cache is not None else upload(upload_base, api_key, reference_paths, args.retries))
            state = {"provider": "kie", "fingerprint": fingerprint, "model": model,
                     "aspect_ratio": aspect_ratio, "resolution": resolution, "status": "submitting",
                     "submitted_at": time.time(), "attempt_history": state.get("attempt_history", []),
                     "timeout_restarts": state.get("timeout_restarts", 0)}
            atomic_write_json(state_path, state)
            try:
                created = request(build_create_request(api_base, api_key, prompt, aspect_ratio, resolution, urls, **({"model":model} if model!=MODEL else {})),
                                       1, operation="create KIE image task", retry_network=False,
                                       request_timeout=min(30, max(1, args.poll_timeout)))
                task_id = str((created.get("data") or {}).get("taskId") or "")
                if not task_id:
                    raise KieError("create KIE image task returned no taskId", 3)
            except KieError:
                state["status"] = "submit_uncertain"
                atomic_write_json(state_path, state)
                raise
            state.update(task_id=task_id, status="waiting")
            atomic_write_json(state_path, state)
        if state.get("result_url"):
            return state["result_url"], state
        try:
            url, _ = poll_task(api_base, api_key, task_id, state_path, state, args.retries, max(1, args.poll_timeout), **({"request_fn":request_fn} if request_fn else {}))
            return url, state
        except GenerationTimeout:
            count = state.get("timeout_restarts", 0)
            if count >= limit or not state.get("timeout_confirmed"):
                raise
            previous = {key: value for key, value in state.items() if key != "attempt_history"}
            previous.update(abandoned_at=time.time(), cancellation_confirmed=False)
            state = {"provider": "kie", "fingerprint": fingerprint, "model": model,
                     "aspect_ratio": aspect_ratio, "resolution": resolution, "status": "restart_ready",
                     "attempt_history": [*state.get("attempt_history", []), previous], "timeout_restarts": count + 1}
            atomic_write_json(state_path, state)
            log("WARN", f"Task {task_id} timed out; starting its one authorized replacement. The old task may still complete and be billed.")


class ResultLinkExpired(KieError):pass


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
    except urllib.error.HTTPError as exc:
        if exc.code in (403,404,410):raise ResultLinkExpired("结果链接已过期，需要重新查询") from None
        raise KieError("图片下载失败，请恢复查询",3) from None
    except (urllib.error.URLError, TimeoutError) as exc:
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
