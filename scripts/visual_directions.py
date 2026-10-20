"""Plan distinct set-level visual directions; no image API calls."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random

SKILL_DIR = Path(__file__).resolve().parent.parent
CATALOG = SKILL_DIR / "config/visual-directions.json"


def load_catalog():
    catalog = json.loads(CATALOG.read_text())
    styles = catalog.get("styles", [])
    if not styles or len({style["id"] for style in styles}) != len(styles):
        raise ValueError("style catalog must contain unique primary directions")
    if catalog.get("style_sources_path"):
        registry = json.loads((CATALOG.parent / catalog["style_sources_path"]).read_text())
        source_ids = {source["id"] for source in registry["sources"]}
        for style in styles:
            if not style.get("source_ids") or not set(style["source_ids"]) <= source_ids:
                raise ValueError("style source is missing or unverified: " + style["id"])
            if "negative_prompt" in style or "{prompt}" in style["prompt"]:
                raise ValueError("raw external templates must not be used as project style descriptions")
    return catalog


def config_fingerprint(config):
    fields = ("request_id", "placements", "sets", "copy_refs", "copy_count", "logo", "logo_asset_id",
              "logo_reference_path", "cta", "ip", "ip_asset_id",
              "ip_random", "font_reference_enabled", "visual_direction")
    payload = {key: config.get(key) for key in fields}
    for key in ("visual_candidates", "visual_diversity_mode"):
        if config.get(key) is not None:
            payload[key] = config[key]
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def balanced(items, count, rng):
    result = []
    while len(result) < count:
        block = rng.sample(items, len(items))
        if result and len(block) > 1 and block[0]["id"] == result[-1]["id"]:
            block[0], block[1] = block[1], block[0]
        result.extend(block)
    return result[:count]


def open_options(presets, candidates, kind, framing_ids):
    """Task-authored descriptions expand the vocabulary without a fixed enum."""
    if not isinstance(candidates, list):
        raise ValueError("visual candidate " + kind + " must be a list")
    authored, seen_ids, seen_prompts = [], set(), set()
    for candidate in candidates:
        if not isinstance(candidate, dict) or not isinstance(candidate.get("id"), str):
            raise ValueError("visual candidates require id, name and a concrete prompt")
        reference = next((item for item in presets if candidate["id"] == item["id"] or candidate["id"] in item.get("alias_ids", [])), None)
        item = {**(reference or {}), **candidate, "origin": "task_authored"}
        if reference:
            item["id"] = reference["id"]
            if candidate.get("prompt", reference["prompt"]) != reference["prompt"]:
                item["description_origin"] = "task_authored_adaptation"
                item["verification_status"] = "task_authored"
        if any(not isinstance(item.get(key), str) or not item[key].strip() for key in ("id", "name", "prompt")):
            raise ValueError("visual candidates require id, name and a concrete prompt")
        normalized_prompt = "".join(item["prompt"].split())
        if item["id"] in seen_ids or normalized_prompt in seen_prompts:
            raise ValueError("duplicate task visual candidate or renamed identical description")
        seen_ids.add(item["id"])
        seen_prompts.add(normalized_prompt)
        components = item.get("components", {})
        if not isinstance(components, dict) or any(not isinstance(value, str) or not value.strip() for value in components.values()):
            raise ValueError("visual components must contain concrete text descriptions")
        if kind == "layouts":
            item.setdefault("framing_ids", ["layout_defined"])
            if not isinstance(item["framing_ids"], list) or not item["framing_ids"] or any(value not in framing_ids for value in item["framing_ids"]):
                raise ValueError("layout uses an unknown framing")
        authored.append(item)
    return authored + [dict(item, origin="preset") for item in presets if item["id"] not in seen_ids]


def prioritized_styles(items, count, rng):
    result, remaining = [], []
    while len(result) < count:
        if not remaining:
            remaining = list(items)
        preferred = [item for item in remaining if item.get("origin") == "task_authored"] or remaining
        if result:
            preferred = [item for item in preferred if item["id"] != result[-1]["id"]] or preferred
        chosen = rng.choice(preferred)
        result.append(chosen)
        remaining = [item for item in remaining if item["id"] != chosen["id"]]
    return result


def varied_layouts(styles, layouts, rng):
    usage, used_pairs, result = Counter(), set(), []
    for style in styles:
        choices = [item for item in layouts if (style["id"], item["id"]) not in used_pairs] or layouts
        if result:
            alternatives = [item for item in choices if item["id"] != result[-1]["id"]]
            choices = alternatives or choices
        def rank(item):
            return usage[item["id"]], item.get("origin") != "task_authored"
        least = min(rank(item) for item in choices)
        choice = rng.choice([item for item in choices if rank(item) == least])
        result.append(choice)
        usage[choice["id"]] += 1
        used_pairs.add((style["id"], choice["id"]))
    return result


def plan_directions(config, seed=None):
    if len(config.get("placements", [])) != 1:
        raise ValueError("visual planning requires one saved placement")
    catalog = load_catalog()
    rng = random.Random(str(seed if seed is not None else config.get("request_id", "")))
    copies = config.get("copy_refs") or [{} for _ in range(int(config.get("copy_count") or 1))]
    sets = int(config.get("sets") or 1)
    if not 1 <= sets <= 50 or len(copies) * sets > 100:
        raise ValueError("visual planning exceeds configured group limits")
    count = len(copies) * sets
    fixed = config.get("visual_direction") or {}
    candidates = config.get("visual_candidates") or {}
    if not isinstance(candidates, dict):
        raise ValueError("visual_candidates must contain task-authored styles/layouts")
    mode = config.get("visual_diversity_mode", "preset")
    if mode not in {"open", "preset"}:
        raise ValueError("visual_diversity_mode must be open or preset")
    if mode == "open" and not (fixed.get("style_id") or fixed.get("style_prompt")) and not candidates.get("styles"):
        raise ValueError("open visual planning requires task-authored style candidates")
    framings = catalog["framings"] + [{"id": "layout_defined", "prompt": "镜头遵循本轮明确编写的布局，人物识别、关键动作和完整文字均清楚可见。"}]
    framing_ids = {item["id"] for item in framings}
    styles = open_options(catalog["styles"], candidates.get("styles", []), "styles", framing_ids)
    layouts = open_options(catalog["layouts"], candidates.get("layouts", []), "layouts", framing_ids)
    has_ip = bool(config.get("ip_random") or config.get("ip_asset_id") or config.get("ip") == "随机")
    if has_ip:
        styles = [style for style in styles if style.get("supports_ip", False)]
        if candidates.get("styles") and not any(style.get("origin") == "task_authored" for style in styles):
            raise ValueError("task-authored styles must explicitly support the selected IP")
    for key, options in (("style", styles), ("layout", layouts)):
        if fixed.get(key + "_prompt"):
            options[:] = [{"id": "custom_" + key, "name": "本轮指定" + key,
                           "prompt": fixed[key + "_prompt"], "origin": "user_fixed", "framing_ids": ["layout_defined"]}]
        elif fixed.get(key + "_id"):
            options[:] = [value for value in options if value["id"] == fixed[key + "_id"] or fixed[key + "_id"] in value.get("alias_ids", [])]
            if not options:
                raise ValueError("unknown visual direction: " + key)
    selected_styles = prioritized_styles(styles, count, rng)
    selected_layouts = varied_layouts(selected_styles, layouts, rng)
    selected_palettes = balanced(catalog["palettes"], count, rng)
    assets = json.loads((SKILL_DIR / "assets/asset-manifest.json").read_text())["assets"]
    ips = [asset for asset in assets if asset["kind"] == "ip"]
    selected_ip = config.get("ip_asset_id") or ""
    random_ip = bool(config.get("ip_random") or selected_ip == "__random_ip__" or config.get("ip") == "随机")
    if selected_ip and not random_ip:
        ips = [asset for asset in ips if asset["asset_id"] == selected_ip]
        if not ips:
            raise ValueError("unknown selected IP asset")
    elif not random_ip:
        ips = []
    fonts = sorted((SKILL_DIR / "assets/font-references").glob("*.png"))
    placement = config["placements"][0]
    width, height = int(placement["target_width"]), int(placement["target_height"])
    small = min(width, height) <= 400
    directions = []
    for index in range(count):
        style, layout, palette = selected_styles[index], selected_layouts[index], selected_palettes[index]
        framing_id = rng.choice(layout["framing_ids"])
        framing = next(value for value in framings if value["id"] == framing_id)
        scenes = [value for value in catalog["scenes"] if layout["id"] != "tabletop_overview" or value["id"] != "abstract_learning_stage"]
        scene = rng.choice(scenes)
        ip = rng.choice(ips) if ips else None
        font = str(rng.choice(fonts)) if config.get("font_reference_enabled", True) else ""
        copy_index, set_index = index // sets + 1, index % sets + 1
        direction_id = f"visual-{index + 1:03d}"
        base_rule = (f"本套视觉方向[{direction_id}]：{style['name']}；{style['prompt']}"
                     f"布局：{layout['name']}，{layout['prompt']}镜头：{framing['prompt']}"
                     f"场景：{scene['prompt']}配色：{palette['prompt']}"
                     "所选Logo保持原版图形、标准字、颜色与位置，不应用画风、纹理或字体参考；"
                     "风格只改变人物与场景的表现，所选字体骨架、文案和产品事实保持原要求。")
        if style.get("components"):
            base_rule += "风格表现细节（仅用于表现，不作为画面文案）：" + "；".join(style["components"].values()) + "。"
        if ip:
            base_rule += "IP保持原版脸型、发型、体型、服装和关键标识，只改变动作表情与表现材质，不改身份或年龄，不把Logo图形放大成替代角色。"
            if style.get("ip_adaptation"):
                base_rule += "本主风格的IP适配：" + style["ip_adaptation"]
        else:
            base_rule += "本套未选IP，以已确认动作与必要道具构成主视觉，不新增吉祥物。"
        if small:
            base_rule += "小幅广告：主文案优先、字大且完整，只呈现一个主要动作；减少背景纹理和装饰，不分漫画格、不堆叠微小卡片。"
        branch_rule = (f"同套视觉继承[{direction_id}]：只从本套首张PNG继承画风、布局、镜头、配色、IP身份、字体和Logo；"
                       "仅按本slot确认文案更换主文案与动作状态，不重新抽取视觉方向或素材。")
        directions.append({"direction_id": direction_id,
                           "set_id": f"copy-{copy_index:03d}-placement-001-set-{set_index:02d}",
                           "copy_draft_id": copies[copy_index - 1].get("copyDraftId", f"draft-{copy_index}"),
                           "style_id": style["id"], "style_name": style["name"],
                           "style_origin": style.get("origin", "preset"),
                           "style_components": style.get("components", {}),
                           "style_source_ids": style.get("source_ids", []),
                           "style_description_origin": style.get("description_origin", "task_authored"),
                           "style_verification_status": style.get("verification_status", "task_authored"),
                           "style_image_validated": style.get("image_validated", False),
                           "layout_id": layout["id"], "layout_name": layout["name"],
                           "layout_origin": layout.get("origin", "preset"),
                           "framing_id": framing_id, "scene_id": scene["id"], "palette_id": palette["id"],
                           "ip_asset_id": ip["asset_id"] if ip else "",
                           "ip_reference_path": ip["path"] if ip else "",
                           "font_reference_path": font, "small_canvas": small,
                           "subject_mode": "selected_ip" if ip else "approved_action_without_ip",
                           "base_prompt_rule": base_rule, "branch_prompt_rule": branch_rule})
    return {"schema_version": "onion_visual_plan_v1", "request_id": config.get("request_id"),
            "catalog_sha256": hashlib.sha256(CATALOG.read_bytes()).hexdigest(),
            "config_fingerprint": config_fingerprint(config), "mode": "fixed" if fixed else "diverse",
            "directions": directions}


def validate_visual_plan(manifest, config):
    path = manifest.get("visual_plan_path")
    if not path:
        if config.get("visual_diversity_enabled"):
            raise ValueError("new configuration requires a saved visual_plan_path")
        return
    plan = json.loads(Path(path).read_text())
    if plan.get("schema_version") != "onion_visual_plan_v1" or plan.get("request_id") != config.get("request_id") or plan.get("config_fingerprint") != config_fingerprint(config):
        raise ValueError("visual plan is stale or belongs to another configuration")
    directions = {value["set_id"]: value for value in plan["directions"]}
    copy_count = len(config.get("copy_refs") or []) or int(config.get("copy_count") or 1)
    expected = copy_count * int(config.get("sets") or 1)
    if len(directions) != expected or len(directions) != len(plan["directions"]) or len({d["direction_id"] for d in directions.values()}) != expected or set(directions) != {job["set_id"] for job in manifest["jobs"]}:
        raise ValueError("visual plan must cover exactly the manifest sets")
    for job in manifest["jobs"]:
        direction = directions[job["set_id"]]
        key = "base_prompt_rule" if int(job.get("slot") or 1) == 1 else "branch_prompt_rule"
        if job.get("visual_direction_id") != direction["direction_id"] or direction[key] not in job["prompt"]:
            raise ValueError("visual direction must be used in every base and inherited by its branches")
        if int(job.get("slot") or 1) == 1:
            from logo_reference import normalize_job_references
            refs = normalize_job_references(job)
            ip_refs = [ref for ref in refs if str(ref.get("asset_id") or "").startswith("ip.")]
            if direction["ip_asset_id"]:
                if len(ip_refs) != 1 or ip_refs[0]["asset_id"] != direction["ip_asset_id"] or Path(ip_refs[0]["path"]).resolve() != (SKILL_DIR / direction["ip_reference_path"]).resolve():
                    raise ValueError("base IP reference differs from its planned identity")
            elif ip_refs:
                raise ValueError("no-IP visual direction must not introduce an IP asset")
            if direction["font_reference_path"] and not any(Path(ref["path"]).resolve() == Path(direction["font_reference_path"]).resolve() for ref in refs):
                raise ValueError("base font reference differs from its planned per-set font")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--seed")
    parser.add_argument("--list-styles", action="store_true", help="Read the local source-backed descriptor library without generating images")
    parser.add_argument("--query", default="", help="Filter Chinese/English names, aliases or visual descriptions")
    parser.add_argument("--detail", action="store_true", help="Include IP adaptation and source metadata")
    args = parser.parse_args()
    if args.list_styles:
        styles = load_catalog()["styles"]
        query = args.query.casefold().strip()
        matches = [style for style in styles if not query or query in json.dumps(style, ensure_ascii=False).casefold()]
        keys = ("id", "name", "name_en", "family", "prompt", "source_ids", "verification_status", "image_validated")
        rows = matches if args.detail else [{key: style.get(key) for key in keys} for style in matches]
        print(json.dumps({"library_count": len(styles), "matched_count": len(rows), "styles": rows}, ensure_ascii=False, indent=2))
        return
    if not args.config or not args.output:
        parser.error("planning requires --config and --output")
    result = plan_directions(json.loads(args.config.read_text()), args.seed)
    if args.output.exists():
        raise ValueError("visual plan exists; use a new task version or output path")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"ok": True, "output": str(args.output.resolve()), "set_count": len(result["directions"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
