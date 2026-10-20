"""Freeze complete scene concepts; retain legacy direction plans for recovery."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
from art_direction import IP_RULE, NO_IP_RULE, art_direction_layers, concise_ip_note, screen_rule

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
    for key in ("visual_candidates", "visual_diversity_mode", "visual_concepts", "visual_style_mode", "art_direction_required", "screen_ui_mode"):
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


def assign_styles(config, seed=None):
    """Choose only the main style; the agent designs each complete scene afterward."""
    copies = config.get("copy_refs") or [{} for _ in range(int(config.get("copy_count") or 1))]
    sets = int(config.get("sets") or 1)
    if not 1 <= sets <= 50 or len(copies) * sets > 100:
        raise ValueError("visual planning exceeds configured group limits")
    styles = load_catalog()["styles"]
    has_ip = bool(config.get("ip_random") or config.get("ip_asset_id") or config.get("ip") == "随机")
    if has_ip:
        styles = [style for style in styles if style.get("supports_ip", False)]
    fixed = config.get("visual_direction") or {}
    if fixed.get("style_prompt"):
        styles = [{"id": "user_fixed_style", "name": "用户指定画风", "prompt": fixed["style_prompt"]}]
    elif fixed.get("style_id"):
        styles = [style for style in styles if fixed["style_id"] == style["id"] or fixed["style_id"] in style.get("alias_ids", [])]
    if not styles:
        raise ValueError("no compatible main styles for the saved configuration")
    rng = random.Random(str(seed if seed is not None else config.get("request_id", "")) + ":main-styles")
    selected = balanced(styles, len(copies) * sets, rng)
    return {"schema_version": "onion_style_assignments_v1", "request_id": config.get("request_id"),
            "directions": [{"set_id": f"copy-{i // sets + 1:03d}-placement-001-set-{i % sets + 1:02d}",
                            "style_id": style["id"], "style_name": style["name"],
                            "style_prompt": style["prompt"] if has_ip else style.get("no_ip_prompt", style["prompt"]),
                            "ip_adaptation": style.get("ip_adaptation", "") if has_ip else "",
                            "style_source_ids": style.get("source_ids", [])} for i, style in enumerate(selected)]}


def plan_content_concepts(config, seed=None):
    copies = config.get("copy_refs") or [{} for _ in range(int(config.get("copy_count") or 1))]
    sets = int(config.get("sets") or 1)
    if not 1 <= sets <= 50 or not copies or len(copies) * sets > 100:
        raise ValueError("visual planning exceeds configured group limits")
    concepts = config.get("visual_concepts")
    if not isinstance(concepts, list) or len(concepts) != len(copies) * sets:
        raise ValueError("content_first requires one complete visual_concepts entry per copy/set")
    style_mode = config.get("visual_style_mode", "random")
    if style_mode not in {"random", "coordinated"}:
        raise ValueError("visual_style_mode must be random or coordinated")
    random_batch = style_mode == "random" and len(concepts) > 1
    assigned = assign_styles(config, seed)["directions"] if random_batch else []
    placement = config["placements"][0]
    image_count = int(placement.get("image_count") or {"双图": 2, "三图": 3}.get(config.get("image_form"), 1))
    assets = json.loads((SKILL_DIR / "assets/asset-manifest.json").read_text())["assets"]
    ips = {a["asset_id"]: a for a in assets if a["kind"] == "ip"}
    fixed_ip = config.get("ip_asset_id") or ""
    random_ip = bool(config.get("ip_random") or fixed_ip == "__random_ip__" or config.get("ip") == "随机")
    if fixed_ip and not random_ip and fixed_ip not in ips:
        raise ValueError("unknown selected IP asset")
    fonts = sorted((SKILL_DIR / "assets/font-references").glob("*.png"))
    rng = random.Random(str(seed if seed is not None else config.get("request_id", "")))
    fixed_rules = []
    fixed_style_prompt = ""
    fixed = config.get("visual_direction") or {}
    for kind in ("style", "layout"):
        if fixed.get(kind + "_prompt"):
            if kind == "style":
                fixed_style_prompt = fixed[kind + "_prompt"]
            else:
                fixed_rules.append(fixed[kind + "_prompt"])
        elif fixed.get(kind + "_id"):
            match = next((v for v in load_catalog()[kind + "s"] if fixed[kind + "_id"] == v["id"] or fixed[kind + "_id"] in v.get("alias_ids", [])), None)
            if match is None:
                raise ValueError("unknown visual direction: " + kind)
            selected_prompt = match["prompt"] if fixed_ip or random_ip else match.get("no_ip_prompt", match["prompt"])
            if kind == "style":
                fixed_style_prompt = selected_prompt
            else:
                fixed_rules.append(selected_prompt)
    directions = []
    for index, concept in enumerate(concepts):
        if not isinstance(concept, dict) or any(not isinstance(concept.get(k), str) or not concept[k].strip() for k in ("name", "prompt")):
            raise ValueError("each visual concept needs a name and a complete scene prompt")
        style = assigned[index] if random_batch else None
        if style is None and concept.get("style_id"):
            single_style_config = config if fixed.get("style_id") or fixed.get("style_prompt") else {
                **config, "visual_direction": {**fixed, "style_id": concept["style_id"]}}
            style = assign_styles(single_style_config, seed)["directions"][index]
        if style:
            acknowledged = concept.get("style_id") or (style["style_id"] if fixed.get("style_id") or fixed.get("style_prompt") else "")
            if acknowledged != style["style_id"]:
                raise ValueError("run --assign-styles first, then design each concept with its assigned style_id")
        actions = concept.get("slot_actions")
        if not isinstance(actions, list) or len(actions) != image_count or any(not isinstance(a, str) or not a.strip() for a in actions):
            raise ValueError("visual concept slot_actions must cover each image in the saved form")
        art_layers = art_direction_layers(concept, config.get("art_direction_required", False))
        if config.get("art_direction_required") and not (style or fixed_style_prompt):
            raise ValueError("art direction requires a selected main style before world and scene")
        screen_mode, screen_text, ui_rule = screen_rule(config, concept)
        selected_ip = concept.get("ip_asset_id") or (rng.choice(list(ips)) if random_ip else fixed_ip)
        if selected_ip and (selected_ip not in ips or (not random_ip and selected_ip != fixed_ip)):
            raise ValueError("concept IP conflicts with the saved IP selection")
        ip = ips.get(selected_ip)
        font = ""
        if config.get("font_reference_enabled", True):
            if not fonts:
                raise ValueError("font reference library is empty")
            font = concept.get("font_reference_path") or str(rng.choice(fonts))
            if Path(font).resolve() not in {p.resolve() for p in fonts}:
                raise ValueError("concept font must use an original font reference")
            font = str(Path(font).resolve())
        copy_index, set_index = index // sets + 1, index % sets + 1
        direction_id = f"visual-{index + 1:03d}"
        slot_rules = {str(i): f"本张动作与情绪[{direction_id}/图{i}]：{action}" for i, action in enumerate(actions, 1)}
        style_rule = (f"画风定调：{style['style_name']}；{style['style_prompt']}\n" if style else
                      f"画风定调（用户指定）：{fixed_style_prompt}\n" if fixed_style_prompt else "")
        base_rule = (style_rule
                     + f"场景与故事：{concept['prompt']}\n" + slot_rules["1"] + "\n"
                     + ("用户指定的视觉要求优先：" + "；".join(fixed_rules) + "。" if fixed_rules else "")
                     + "主体、道具、光线与文字统一设计，标题可读并为故事和场景关系保留空间。")
        base_rule += (IP_RULE if ip else NO_IP_RULE) + ui_rule
        if ip and style:
            medium_note = concise_ip_note(style["ip_adaptation"])
            if medium_note:
                base_rule += "IP画风适配：" + medium_note
        directions.append({
            "direction_id": direction_id, "set_id": f"copy-{copy_index:03d}-placement-001-set-{set_index:02d}",
            "copy_draft_id": copies[copy_index - 1].get("copyDraftId", f"draft-{copy_index}"),
            "concept_name": concept["name"], "concept_prompt": concept["prompt"],
            "art_direction": art_layers, "screen_ui_mode": screen_mode, "screen_text": screen_text,
            "style_source_ids": style["style_source_ids"] if style else concept.get("style_source_ids", []),
            **({"style_id": style["style_id"], "style_name": style["style_name"]} if style else {}),
            "style_description_origin": "task_authored", "style_verification_status": "task_authored",
            "style_image_validated": False,
            "slot_prompt_rules": slot_rules, "ip_asset_id": selected_ip,
            "ip_reference_path": ip["path"] if ip else "", "font_reference_path": font,
            "subject_mode": "selected_ip" if ip else "approved_action_without_ip",
            "base_prompt_rule": base_rule,
            "branch_prompt_rule": f"同套画面继承[{direction_id}]：从本套首张PNG继承{'IP身份与本套服饰、' if ip else '选定主体、'}视觉体系、场景连续性、字体与Logo；按当前短句和动作推进故事，调整必要形态、视线或道具关系，使每张承担对应的叙事内容。" + ui_rule,
        })
    return {"schema_version": "onion_visual_plan_v1", "request_id": config.get("request_id"),
            "config_fingerprint": config_fingerprint(config), "mode": "content_first",
            "style_mode": style_mode, "directions": directions}


def plan_directions(config, seed=None):
    if len(config.get("placements", [])) != 1:
        raise ValueError("visual planning requires one saved placement")
    if config.get("visual_diversity_mode", "content_first") == "content_first":
        return plan_content_concepts(config, seed)
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
    else:
        styles = [dict(style, prompt=style.get("no_ip_prompt", style["prompt"])) for style in styles]
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
            base_rule += IP_RULE
            if style.get("ip_adaptation"):
                base_rule += "本主风格的IP适配：" + style["ip_adaptation"]
        else:
            base_rule += NO_IP_RULE
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
    if plan.get("style_mode") == "random":
        prompts = ["".join(job["prompt"].split()) for job in manifest["jobs"]]
        if len(set(prompts)) != len(prompts):
            raise ValueError("each image must have its own distinct complete prompt")
    copy_count = len(config.get("copy_refs") or []) or int(config.get("copy_count") or 1)
    expected = copy_count * int(config.get("sets") or 1)
    if len(directions) != expected or len(directions) != len(plan["directions"]) or len({d["direction_id"] for d in directions.values()}) != expected or set(directions) != {job["set_id"] for job in manifest["jobs"]}:
        raise ValueError("visual plan must cover exactly the manifest sets")
    for job in manifest["jobs"]:
        direction = directions[job["set_id"]]
        key = "base_prompt_rule" if int(job.get("slot") or 1) == 1 else "branch_prompt_rule"
        if job.get("visual_direction_id") != direction["direction_id"] or direction[key] not in job["prompt"]:
            raise ValueError("visual direction must be used in every base and inherited by its branches")
        if plan.get("mode") == "content_first":
            action = direction.get("slot_prompt_rules", {}).get(str(int(job.get("slot") or 1)))
            if not action or action not in job["prompt"]:
                raise ValueError("each content-first job must use its planned scene action")
            if "screen_text" in direction and job.get("ui_text", []) != direction["screen_text"]:
                raise ValueError("job ui_text differs from the planned screen_text whitelist")
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
    parser.add_argument("--assign-styles", action="store_true", help="Assign one main style per set before authoring complete scenes")
    parser.add_argument("--query", default="", help="Filter Chinese/English names, aliases or visual descriptions")
    parser.add_argument("--detail", action="store_true", help="Include IP adaptation and source metadata")
    args = parser.parse_args()
    if args.list_styles:
        styles = load_catalog()["styles"]
        query = args.query.casefold().strip()
        matches = [style for style in styles if not query or query in json.dumps(style, ensure_ascii=False).casefold()]
        keys = ("id", "name", "name_en", "family", "prompt", "no_ip_prompt", "source_ids", "verification_status", "image_validated")
        rows = matches if args.detail else [{key: style.get(key) for key in keys} for style in matches]
        print(json.dumps({"library_count": len(styles), "matched_count": len(rows), "styles": rows}, ensure_ascii=False, indent=2))
        return
    if not args.config or not args.output:
        parser.error("planning requires --config and --output")
    config = json.loads(args.config.read_text())
    result = assign_styles(config, args.seed) if args.assign_styles else plan_directions(config, args.seed)
    if args.output.exists():
        raise ValueError("visual plan exists; use a new task version or output path")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"ok": True, "output": str(args.output.resolve()), "set_count": len(result["directions"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
