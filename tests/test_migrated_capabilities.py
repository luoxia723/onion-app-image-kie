from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

import pytest
from PIL import Image


SKILL_DIR = Path(__file__).parents[1]
SCRIPTS = SKILL_DIR / "scripts"
REPO_ROOT = Path.cwd()
RUNTIME_ROOT = REPO_ROOT / "工作区" / "产物" / "tests" / "app-image"


def load_module(name: str):
    path = SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"app_image_{name}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


interactive_server = load_module("interactive_server")
batch_render = load_module("batch_render")
package_images = load_module("package_accepted_images")
image_compress = load_module("image_compress")
build_selection_page = load_module("build_selection_page")
prepare_deliveries = load_module("prepare_accepted_deliveries")


def test_interactive_server_accepts_formal_role_output_directory(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(interactive_server, "repository_root", lambda: tmp_path)
    formal = tmp_path / "工作区" / "产物" / "2026-08-28" / "APP图片" / "业务任务" / "v001" / "02_过程"
    resolved = interactive_server.resolve_output_dir(str(formal), "request-test")
    assert resolved == formal.resolve()
    with pytest.raises(ValueError):
        interactive_server.resolve_output_dir(str(tmp_path.parent / "outside"), "request-test")


def test_assets_and_placement_rules_are_complete() -> None:
    manifest = json.loads(
        (SKILL_DIR / "assets" / "asset-manifest.json").read_text(encoding="utf-8")
    )
    for asset in manifest["assets"]:
        assert (SKILL_DIR / asset["path"]).is_file(), asset["path"]

    slots = interactive_server.load_platform_slots()
    assert len(slots) == 102
    assert {slot["image_form"] for slot in slots} >= {"单图", "双图", "三图"}


def test_current_copy_fields_feed_single_double_and_triple_config() -> None:
    for image_form, copy_fields in (
        ("单图", {"mainTitle": "第一题就卡住", "subtitle": "拍一下，分步骤看懂"}),
        ("双图", {"short1": "上课听懂了", "short2": "回家第一题不会"}),
        (
            "三图",
            {"short1": "刚学完新公式", "short2": "第一步就卡住", "short3": "拍一下继续往下写"},
        ),
    ):
        context = {
            "channel": "应用商店",
            "image_form": image_form,
            "copy_drafts": [
                {"copyDraftId": f"copy-{image_form}", "imageForm": image_form, **copy_fields}
            ],
        }
        payload = interactive_server.build_config_payload("request-test", context)
        assert payload["desiredImageForm"] == image_form
        assert payload["copyRefs"][0]["imageForm"] == image_form
        assert any(
            slot["enabled"] and slot["image_form"] == image_form
            for slot in payload["slots"]
        )


def test_config_saves_exactly_one_placement() -> None:
    context = {"channel": "应用商店", "image_form": "单图"}
    slot_map = interactive_server.slots_by_id(context=context)
    enabled_ids = [
        slot_id
        for slot_id, slot in slot_map.items()
        if slot.get("enabled") and slot.get("image_form") == "单图"
    ]
    assert len(enabled_ids) >= 2

    body = {
        "request_id": "request-single-placement",
        "delivery_name": "单版位测试",
        "placement_ids": [enabled_ids[0]],
        "sets": 2,
        "copy_count": 1,
        "font_reference_enabled": False,
    }
    result = interactive_server.normalize_config_result(body, slot_map)
    assert result["placement_ids"] == [enabled_ids[0]]
    assert len(result["placements"]) == 1
    assert result["estimated_group_count"] == 2

    with pytest.raises(ValueError, match="exactly one"):
        interactive_server.normalize_config_result(
            {**body, "placement_ids": enabled_ids[:2]},
            slot_map,
        )


def test_render_validate_only_needs_no_key_or_paid_approval() -> None:
    output = RUNTIME_ROOT / "validate-only.png"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "render.py"),
            "--prompt",
            "竖版教育广告海报，主标题：第一题就卡住？副标题：拍一下，分步骤看懂。",
            "--aspect-ratio",
            "9:16",
            "--output",
            str(output),
            "--validate-only",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["valid"] is True
    assert payload["provider"] == "kie"
    assert payload["model"] == "gpt-image-2-text-to-image"


def test_paid_render_and_batch_require_current_approval(tmp_path: Path) -> None:
    output = RUNTIME_ROOT / "paid-gate.png"
    direct = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "render.py"),
            "--prompt",
            "教育广告海报测试",
            "--aspect-ratio",
            "1:1",
            "--output",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert direct.returncode == 2
    assert "--approved-in-current-task" in direct.stderr

    manifest_path = tmp_path / "image-render-manifest.json"
    config_path = tmp_path / "image-config-result.json"
    manifest_path.write_text(
        json.dumps(
            {
                "request_id": "request-test",
                "jobs": [
                    {
                        "job_id": "job-1",
                        "set_id": "set-1",
                        "slot": 1,
                        "prompt": "教育广告海报测试",
                        "resolution": "2K",
                        "aspect_ratio": "1:1",
                        "references": [],
                        "output": str(RUNTIME_ROOT / "batch-gate.png"),
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    config_path.write_text(
        json.dumps({"request_id": "request-test", "logo": "不用"}, ensure_ascii=False),
        encoding="utf-8",
    )
    assert batch_render.main(
        ["--manifest", str(manifest_path), "--config", str(config_path)]
    ) == 2


def test_local_compression_and_package_use_delivery_jpegs(tmp_path: Path) -> None:
    source = SKILL_DIR / "assets" / "logos" / "onion-logo-standard-001.png"
    task_root = tmp_path / "APP_测试_APP图片_120000"
    version_root = task_root / "v001"
    delivery_dir = version_root / "04_交付"
    quality_dir = version_root / "05_质检"
    package_dir = version_root / "06_打包"
    for directory in (delivery_dir, quality_dir, package_dir):
        directory.mkdir(parents=True)
    (task_root / "任务索引.json").write_text(
        json.dumps({"task_id": "AIMG-PACKAGE", "file_stem": "APP_测试_APP图片"}),
        encoding="utf-8",
    )

    compressed = delivery_dir / "APP_测试_APP图片_方案001_图01_v001.jpg"
    image_compress.compress(
        str(source),
        str(compressed),
        target_kb=100,
        target_width=320,
        target_height=180,
    )
    assert compressed.is_file()
    with Image.open(compressed) as image:
        assert image.format == "JPEG"
        assert image.size == (320, 180)
    assert compressed.stat().st_size <= 100 * 1024
    delivery_result = quality_dir / "APP_测试_APP图片_交付规格质检_v001.json"
    delivery_result.write_text(
        json.dumps(
            {
                "schema_version": "onion_app_image_local_delivery_v1",
                "task_id": "AIMG-PACKAGE",
                "version": "v001",
                "files": [
                    {
                        "delivery": str(compressed),
                        "byte_count": compressed.stat().st_size,
                        "sha256": prepare_deliveries.file_sha256(compressed),
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = package_images.package_accepted_images(delivery_result)
    assert result["delivery_file_count"] == 1
    with zipfile.ZipFile(result["zip"]) as archive:
        assert len(archive.namelist()) == 2
        manifest_name = next(name for name in archive.namelist() if name.endswith("/交付清单.json"))
        portable = json.loads(archive.read(manifest_name))
        assert portable["schema_version"] == "onion_delivery_package_v1"
        assert portable["files"][0]["sha256"]
        assert portable["files"][0]["path"].endswith(".jpg")


def test_prepare_accepted_deliveries_only_processes_accepted_images(tmp_path: Path) -> None:
    task_root = tmp_path / "APP_测试_APP图片_120000"
    version_root = task_root / "v001"
    for phase in ("02_过程", "03_候选", "04_交付", "05_质检"):
        (version_root / phase).mkdir(parents=True)
    candidate_dir = version_root / "03_候选" / "候选图片"
    candidate_dir.mkdir()
    source = candidate_dir / "candidate-1.png"
    shutil.copy2(SKILL_DIR / "assets" / "logos" / "onion-logo-standard-001.png", source)

    (task_root / "任务索引.json").write_text(
        json.dumps(
            {
                "schema_version": "onion_artifact_task_index_v1",
                "task_id": "AIMG-TEST-LOCAL",
                "file_stem": "APP_测试_APP图片",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    selection = version_root / "03_候选" / "image-selection-result.json"
    selection.write_text(
        json.dumps(
            {
                "request_id": "AIMG-TEST-LOCAL",
                "accepted_schemes": [
                    {"set_id": "candidate-1", "thumb": ["候选图片/candidate-1.png"]}
                ],
                "rejected_schemes": [
                    {"set_id": "candidate-2", "thumb": ["候选图片/candidate-2.png"]}
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    config = version_root / "02_过程" / "image-config-result.json"
    config.write_text(
        json.dumps(
            {
                "request_id": "AIMG-TEST-LOCAL",
                "placements": [
                    {
                        "id": "placement-1",
                        "platform": "测试平台",
                        "placement": "单图",
                        "target_width": 320,
                        "target_height": 180,
                        "max_file_size_kb": 100,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    manifest = version_root / "02_过程" / "image-render-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "request_id": "AIMG-TEST-LOCAL",
                "jobs": [
                    {
                        "job_id": "candidate-1-slot-01",
                        "set_id": "candidate-1",
                        "slot": 1,
                        "placement_id": "placement-1",
                        "target_width": 320,
                        "target_height": 180,
                        "target_kb": 100,
                        "output": str(source),
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = prepare_deliveries.prepare_accepted_deliveries(selection)

    assert result["processor"] == "local-pillow"
    assert result["accepted_scheme_count"] == 1
    assert result["delivery_file_count"] == 1
    assert len(list((version_root / "04_交付").glob("*.jpg"))) == 1
    delivery = Path(result["files"][0]["delivery"])
    with Image.open(delivery) as image:
        assert image.format == "JPEG"
        assert image.size == (320, 180)
    assert delivery.stat().st_size <= 100 * 1024
    assert Path(result["quality_result"]).is_file()

    resumed = prepare_deliveries.prepare_accepted_deliveries(selection)
    assert resumed["files"][0]["reused_existing"] is True

    selection.write_text(
        json.dumps({"request_id": "AIMG-TEST-LOCAL", "accepted_schemes": []}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="selection changed"):
        prepare_deliveries.prepare_accepted_deliveries(selection)


def test_prepare_accepted_deliveries_all_rejected_is_success(tmp_path: Path) -> None:
    task_root = tmp_path / "APP_全拒绝_APP图片_120000"
    version_root = task_root / "v001"
    for phase in ("02_过程", "03_候选", "04_交付", "05_质检"):
        (version_root / phase).mkdir(parents=True)
    (task_root / "任务索引.json").write_text(
        json.dumps({"task_id": "AIMG-ALL-REJECTED", "file_stem": "APP_全拒绝_APP图片"}),
        encoding="utf-8",
    )
    selection = version_root / "03_候选" / "image-selection-result.json"
    selection.write_text(
        json.dumps({"request_id": "AIMG-ALL-REJECTED", "accepted_schemes": []}),
        encoding="utf-8",
    )
    (version_root / "02_过程" / "image-config-result.json").write_text(
        json.dumps({"placements": [{"id": "placement-1"}]}),
        encoding="utf-8",
    )
    (version_root / "02_过程" / "image-render-manifest.json").write_text(
        json.dumps({"jobs": []}),
        encoding="utf-8",
    )

    result = prepare_deliveries.prepare_accepted_deliveries(selection)

    assert result["accepted_scheme_count"] == 0
    assert result["delivery_file_count"] == 0
    assert not list((version_root / "04_交付").iterdir())


def test_selection_page_keeps_technically_successful_candidates_with_content_findings(
    tmp_path: Path,
) -> None:
    source = SKILL_DIR / "assets" / "logos" / "onion-logo-standard-001.png"
    data = {
        "request_id": "request-review-findings",
        "sets": [
            {
                "set_id": "set-1",
                "status": "completed",
                "images": [{"path": str(source)}],
                "review_findings": [
                    "出现辅助小字",
                    "Logo颜色随背景适配",
                ],
            }
        ],
    }

    request_id, sets = build_selection_page.normalize_sets(data, tmp_path)

    assert request_id == "request-review-findings"
    assert len(sets) == 1
    assert sets[0]["set_id"] == "set-1"
    assert len(sets[0]["thumb"]) == 1
    assert sets[0]["meta"]["review_findings"] == [
        "出现辅助小字",
        "Logo颜色随背景适配",
    ]

    html = build_selection_page.build_html(
        (SKILL_DIR / "templates" / "image-selection.html").read_text(encoding="utf-8"),
        request_id,
        sets,
    )
    assert "候选提示（仅供选择参考，不代表淘汰）" in html
    assert "出现辅助小字" in html
    assert "fixedRuleFeedback" not in html
    assert "subjectiveFeedback" not in html
    assert "不采纳时请填写" not in html
    assert "function reject() { decide('rejected'); }" in html
    assert "upload_to_feishu" not in html
