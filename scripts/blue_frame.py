"""Reusable white-frame layout and OpenCV crop/stretch adapter."""
from pathlib import Path
import argparse
import hashlib
import math
import json
import cv2
import numpy as np
from kie_model import geometry_report, nearest_aspect_ratio, CROP_REVIEW_THRESHOLD_PERCENT


def legacy_prompt_rule(label):
    return (f'{label}是白底蓝框布局模板。只在蓝框内部生成完整广告，广告背景也只铺满蓝框内部；'
            '完整Logo、文案、人物和道具都放在框内，文字笔画、描边和阴影不得越框。'
            '蓝框外全部保持纯白，不画背景延伸、文字、人物、装饰或阴影。保持蓝框原有位置、形状和大小，'
            '蓝框作为制作辅助线保留在原位置，后续由代码连同框外白边一起裁掉。')


def prompt_rule(label):
    return (f'{label}为白底蓝框布局参考，完整广告的背景、文案、主体和道具均位于蓝框内，'
            '文字笔画、描边与阴影完整收在框内；框外为纯白，蓝框位置、形状和大小与参考一致。')


def has_prompt_rule(prompt, label):
    return any(rule(label) in prompt for rule in (prompt_rule, legacy_prompt_rule))


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare_layout(width, height, directory, label='参考图2'):
    from PIL import Image, ImageDraw
    report = geometry_report(width, height)
    if not report['needs_safe_area']:
        return {'enabled': False, 'geometry': report}
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    ratio = nearest_aspect_ratio(width, height)
    a, b = map(int, ratio.split(':'))
    multiple = math.ceil(900 / min(a, b))
    canvas_w, canvas_h = a * multiple, b * multiple
    stroke = 6
    margin = round(min(canvas_w, canvas_h) * 0.02) + stroke
    scale = min((canvas_w - 2 * margin) / width, (canvas_h - 2 * margin) / height)
    content_w, content_h = round(width * scale), round(height * scale)
    left, top = (canvas_w - content_w) // 2, (canvas_h - content_h) // 2
    box = [left, top, left + content_w, top + content_h]
    frame = [left - stroke, top - stroke, box[2] + stroke - 1, box[3] + stroke - 1]
    guide = directory / 'blue-frame-guide.png'
    spec_path = directory / 'frame-layout.json'
    image = Image.new('RGB', (canvas_w, canvas_h), 'white')
    ImageDraw.Draw(image).rectangle(frame, outline='#1663d6', width=stroke)
    import io
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    content = buffer.getvalue()
    spec = {'schema_version': 'blue_frame_v1', 'enabled': True, 'aspect_ratio': ratio,
            'guide_canvas': [canvas_w, canvas_h], 'target_size': [width, height],
            'content_box_xyxy': box, 'frame_outer_xyxy_inclusive': frame,
            'guide_path': str(guide), 'guide_sha256': hashlib.sha256(content).hexdigest(),
            'reference_label': label, 'inset_pixels': 2, 'resize_mode': 'stretch',
            'trigger_cover_crop_percent': report['crop_percent']}
    if spec_path.exists() and json.loads(spec_path.read_text()) != spec:
        raise ValueError('已有蓝框配置不同，请使用新版本或新目录。')
    if guide.exists() and guide.read_bytes() != content:
        raise ValueError('已有蓝框参考图不同，请使用新版本或新目录。')
    guide.write_bytes(content)
    spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2))
    return {'enabled': True, 'frame_layout_path': str(spec_path),
            'reference': {'label': label, 'role': '白底蓝框构图模板', 'path': str(guide)},
            'prompt_rule': prompt_rule(label), 'geometry': report}


def validate_layout(path, target_size, reference_items, reference_paths, prompt, inherited_base=None):
    spec = json.loads(Path(path).read_text())
    if spec.get('schema_version') != 'blue_frame_v1' or spec.get('resize_mode') != 'stretch':
        raise ValueError('无效的白底蓝框配置。')
    if list(map(int, target_size.split('x'))) != spec['target_size']:
        raise ValueError('蓝框目标尺寸与版位不符。')
    if spec['aspect_ratio'] != nearest_aspect_ratio(*spec['target_size']):
        raise ValueError('蓝框画布比例与生成比例不符。')
    guide = Path(spec['guide_path']).resolve()
    if sha256(guide) != spec['guide_sha256']:
        raise ValueError('蓝框参考图哈希不符。')
    inherits_frame = bool(inherited_base) and len(reference_paths) == 1 and reference_paths[0].resolve() == Path(inherited_base).resolve()
    if inherits_frame:
        from render import load_task_state, task_state_path, sha256_file
        state = load_task_state(task_state_path(Path(inherited_base)))
        if state.get('status') != 'downloaded' or state.get('sha256') != sha256_file(Path(inherited_base)):
            raise ValueError('继承蓝框的首张PNG与生成回执不符。')
    if not inherits_frame and not any(item['label'] == spec['reference_label'] and file.resolve() == guide
               for item, file in zip(reference_items, reference_paths)):
        raise ValueError('参考图编号或文件与蓝框配置不符。')
    label = reference_items[0]['label'] if inherits_frame else spec['reference_label']
    if not has_prompt_rule(prompt, label):
        raise ValueError('Prompt缺少本轮蓝框生成范围规则。')
    return spec


def process_candidate(source, spec_path):
    """Keep the raw image; failed detection remains a reviewable raw candidate."""
    source, spec_path = Path(source), Path(spec_path)
    spec = json.loads(spec_path.read_text())
    image = cv2.imread(str(source))
    if image is None:
        raise ValueError('原图无法解码。')
    output, record = detect_and_resize(image, spec, spec.get('inset_pixels', 2))
    candidate_root = next((parent for parent in source.parents if parent.name == '03_候选'), source.parent)
    target = candidate_root / '框内预览'
    target.mkdir(exist_ok=True)
    token = hashlib.sha256((sha256(source) + sha256(spec_path)).encode()).hexdigest()[:12]
    path = target / f'{source.stem}_{token}_frame.png'
    record_path = path.with_suffix('.crop.json')
    record.update(source=str(source.resolve()), source_sha256=sha256(source),
                  frame_layout_sha256=sha256(spec_path), candidate_filepath=str(path.resolve()))
    height, width = image.shape[:2]
    x1, y1, x2, y2 = spec['content_box_xyxy']
    cw, ch = spec['guide_canvas']
    expected = [x1 * width / cw, y1 * height / ch, x2 * width / cw, y2 * height / ch]
    actual = record['crop_xyxy']
    intersection = max(0, min(expected[2], actual[2]) - max(expected[0], actual[0])) * max(0, min(expected[3], actual[3]) - max(expected[1], actual[1]))
    additional = max(0, 1 - intersection / ((expected[2] - expected[0]) * (expected[3] - expected[1]))) * 100
    record['additional_template_area_removed_percent'] = round(additional, 4)
    record['needs_crop_review'] = additional >= CROP_REVIEW_THRESHOLD_PERCENT
    if not cv2.imwrite(str(path), output):
        raise OSError('无法保存去框结果。')
    record['candidate_sha256'] = sha256(path)
    record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2))
    return record


def attach_result(metadata, source, spec_path):
    metadata['frame_layout_path'] = str(spec_path)
    metadata['default_cover_crop_percent'] = metadata.pop('actual_crop_percent', None)
    metadata['review_findings'] = ['白底蓝框生成，OpenCV按实际框线去框后拉伸至目标尺寸；请确认文字、Logo和人物完整。']
    try:
        record = process_candidate(source, spec_path)
        metadata.update(frame_status='processed', frame_processing=record, candidate_filepath=record['candidate_filepath'])
        if record['needs_crop_review']:
            metadata['review_findings'].append('框内新增裁切达到6%，请重点查看实际裁切范围。')
        if max(record['scale_x'], record['scale_y']) >= 1.25:
            metadata['review_findings'].append('框内图像放大至少1.25倍，请检查小字与边缘清晰度。')
    except (ValueError, OSError, cv2.error) as exc:
        metadata.update(frame_status='needs_review', frame_error=str(exc), candidate_filepath=str(source))
        metadata['review_findings'].append('蓝框无法可靠自动去除：' + str(exc) + ' 原图已保留，等待人工复核，不自动付费重做。')
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--label', default='参考图2')
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    placements = config.get('placements', [])
    if len(placements) != 1:
        parser.error('配置必须只有一个版位。')
    placement = placements[0]
    print(json.dumps(prepare_layout(placement['target_width'], placement['target_height'], args.output_dir, args.label), ensure_ascii=False))


def blue_mask(image):
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    return cv2.inRange(hsv, np.array([92, 90, 90]), np.array([132, 255, 255]))


def line_band(mask, axis, expected, span, radius):
    size = mask.shape[0 if axis == 'y' else 1]
    start, stop = max(0, round(expected - radius)), min(size, round(expected + radius) + 1)
    a, b = span
    roi = mask[start:stop, a:b] if axis == 'y' else mask[a:b, start:stop]
    length = max(20, round((b - a) * 0.65))
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (length, 1) if axis == 'y' else (1, length))
    long_lines = cv2.morphologyEx(roi, cv2.MORPH_OPEN, kernel)
    scores = np.mean(long_lines > 0, axis=1 if axis == 'y' else 0)
    candidates = np.flatnonzero(scores >= 0.78) + start
    if not len(candidates):
        raise ValueError(f'未找到可靠的{axis}方向长框线，停止自动裁切。')
    groups = np.split(candidates, np.flatnonzero(np.diff(candidates) > 1) + 1)
    if len(groups) > 1:
        raise ValueError('出现多个相近候选框线，停止自动裁切。')
    group = groups[0]
    lo, hi = int(group[0]), int(group[-1])
    if hi - lo + 1 > 16:
        raise ValueError('候选边框过厚，停止自动裁切。')
    return {'start': lo, 'end_inclusive': hi, 'coverage': round(float(np.mean(scores[group - start])), 4)}


def detect_and_resize(image, spec, inset=2):
    height, width = image.shape[:2]
    canvas_w, canvas_h = spec['guide_canvas']
    if abs((width / height) / (canvas_w / canvas_h) - 1) > 0.02:
        raise ValueError('原图画布比例不符。')
    fx1, fy1, fx2, fy2 = spec['frame_outer_xyxy_inclusive']
    mask = blue_mask(image)
    sx, sy = width / canvas_w, height / canvas_h
    iw, ih = (fx2 - fx1) * sx, (fy2 - fy1) * sy
    horizontal_span = (round(fx1 * sx + iw * 0.18), round(fx2 * sx - iw * 0.18))
    vertical_span = (round(fy1 * sy + ih * 0.04), round(fy1 * sy + ih * 0.30))
    edges = {
        'left': line_band(mask, 'x', fx1 * width / canvas_w, vertical_span, width * 0.035),
        'right': line_band(mask, 'x', fx2 * width / canvas_w, vertical_span, width * 0.035),
        'top': line_band(mask, 'y', fy1 * height / canvas_h, horizontal_span, height * 0.025),
        'bottom': line_band(mask, 'y', fy2 * height / canvas_h, horizontal_span, height * 0.025),
    }
    interior = [edges['left']['end_inclusive'] + 1, edges['top']['end_inclusive'] + 1,
                edges['right']['start'], edges['bottom']['start']]
    x1, y1, x2, y2 = interior
    target_w, target_h = spec['target_size']
    if x2 <= x1 or y2 <= y1 or abs(((x2 - x1) / (y2 - y1)) / (target_w / target_h) - 1) > 0.04:
        raise ValueError('检测框的大小或比例异常，停止自动裁切。')
    if inset < 0 or inset > 8:
        raise ValueError('本次试裁仅允许0–8像素内缩。')
    box = [x1 + inset, y1 + inset, x2 - inset, y2 - inset]
    x1, y1, x2, y2 = box
    cropped = image[y1:y2, x1:x2].copy()
    interpolation = cv2.INTER_AREA if target_w <= cropped.shape[1] and target_h <= cropped.shape[0] else cv2.INTER_CUBIC
    # Explicitly permit a small aspect change, as requested. No second ratio crop.
    output = cv2.resize(cropped, (target_w, target_h), interpolation=interpolation)
    scale_x, scale_y = target_w / cropped.shape[1], target_h / cropped.shape[0]
    return output, {'source_size': [width, height], 'detected_frame_edges': edges,
                    'detected_interior_xyxy': interior, 'extra_inset_per_side_pixels': inset,
                    'crop_xyxy': box, 'cropped_size': [cropped.shape[1], cropped.shape[0]],
                    'output_size': [target_w, target_h], 'scale_x': round(scale_x, 7),
                    'scale_y': round(scale_y, 7), 'relative_horizontal_stretch_percent': round((scale_x / scale_y - 1) * 100, 4),
                    'interpolation': 'INTER_AREA' if interpolation == cv2.INTER_AREA else 'INTER_CUBIC'}


if __name__ == '__main__':
    main()
