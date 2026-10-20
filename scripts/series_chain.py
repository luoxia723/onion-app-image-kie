"""Validate same-set base/branch topology before any paid submission."""
import json
from pathlib import Path
import re

from logo_reference import normalize_job_references


def text_rule(text, logo="洋葱学园", cta=""):
    allowed = [value for value in (text, logo, cta) if value]
    return "画面文字白名单：" + json.dumps(allowed, ensure_ascii=False)


def validate_series(manifest, config):
    jobs = manifest["jobs"]
    placement = config["placements"][0]
    expected = int(placement.get("image_count") or {"双图": 2, "三图": 3}.get(config.get("image_form"), 1))
    groups = {}
    for job in jobs:
        groups.setdefault(job["set_id"], []).append(job)
    branches = {}
    for group in groups.values():
        count = expected if expected > 1 else max(int(j.get("slot") or 1) for j in group)
        if sorted(int(j.get("slot") or 1) for j in group) != list(range(1, count + 1)):
            raise ValueError("same-set slots must be complete and unique")
        base = next(j for j in group if int(j.get("slot") or 1) == 1)
        if base.get("base_job_id") or (count > 1 and base.get("depends_on")):
            raise ValueError("the base must not depend on a branch")
        for job in group:
            slot = int(job.get("slot") or 1)
            copies = config.get("copy_refs") or []
            if copies and count > 1:
                copy_id = job.get("copy_draft_id")
                source = copies[0] if len(copies) == 1 else next(
                    (c for c in copies if c.get("copyDraftId") == copy_id), None)
                if not source:
                    raise ValueError("job must identify its approved copy")
                text = source.get(f"short{slot}")
                if text:
                    if job.get("copy_text") != text or text_rule(text, config.get("logo", ""), config.get("cta", "")) not in job["prompt"]:
                        raise ValueError("copy_text and text whitelist must match the approved slot")
                    allowed = [text, config.get("logo", ""), config.get("cta", "")]
                    for match in re.finditer(r'(?:保留|写出|呈现|显示)[“\"]([^”\"]+)[”\"]', job["prompt"]):
                        prefix = job["prompt"][max(0, match.start() - 4):match.start()]
                        if any(word in prefix for word in ("不", "禁止")):
                            continue
                        if not any(match.group(1) in value for value in allowed if value):
                            raise ValueError("prompt requests text outside its approved whitelist")
            if slot == 1:
                continue
            if job.get("base_job_id") != base["job_id"] or job.get("depends_on") != [base["job_id"]]:
                raise ValueError("every branch must depend on its own slot-1 base")
            refs = normalize_job_references(job)
            if len(refs) != 1 or refs[0].get("label") != "参考图1" or refs[0].get("asset_id") or Path(refs[0]["path"]).resolve() != Path(base["output"]).resolve():
                raise ValueError("branch references must contain only the same-set base PNG")
            if job.get("frame_layout_path") != base.get("frame_layout_path"):
                raise ValueError("branch must inherit the base frame layout")
            branches[job["job_id"]] = base
    return branches
