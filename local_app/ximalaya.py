"""One approved ad adapted to the selected Ximalaya delivery sizes."""
from pathlib import Path

from .config import UserError


BASE = 'ximalaya-current-single-1000x1000'
PLACEMENTS = (
    BASE, 'ximalaya-current-single-1280x720', 'ximalaya-current-single-1200x480',
    'ximalaya-current-single-720x1280', 'ximalaya-current-single-720x1559',
)


def placements(params):
    return tuple(pid for pid in PLACEMENTS if pid in params.get('pids', ())) if params.get('ximalaya_suite') else ()


def is_grouped(round_, pid):
    return pid in placements(round_['params'])


def only(params):
    return bool(placements(params)) and all(pid in PLACEMENTS for pid in params['pids'])


def validate(params):
    if type(params.get('ximalaya_suite', False)) is not bool:
        raise UserError('喜马拉雅套图类型不正确')
    if not params.get('ximalaya_suite'):
        return
    selected = placements(params)
    if not selected or params.get('learning_mode') == 'upload':
        raise UserError('请选择至少一个喜马拉雅套图尺寸')
    overrides=params.get('cta_overrides', {})
    counts=params.get('variants_by_placement', {})
    if (isinstance(overrides,dict) and any(pid in overrides for pid in selected)
            or len({counts.get(pid,params['sets']) for pid in selected})>1):
        raise UserError('喜马拉雅套图共用同一份按钮文案和套数')
    if params.get('cta_enabled', True) and not str(params.get('cta', '')).strip():
        raise UserError('请填写整套按钮文字，或关闭添加按钮')


def selection_pid(round_, pid):
    selected=placements(round_['params'])
    return selected[0] if pid in selected else pid


def complete(slots, simulation, selected=PLACEMENTS):
    if not selected or len(slots) != len(selected) or {slot['pid'] for slot in slots} != set(selected):
        return False
    root = next(slot for slot in slots if slot['pid'] == selected[0])
    proof = root.get('ximalaya_review', {})
    if (proof.get('status') != ('simulated' if simulation else 'approved') or proof.get('att') != root['att']
            or not proof.get('raw_sha256') or not proof.get('sha256')
            or proof.get('raw_sha256') != root.get('raw_sha256') or proof.get('sha256') != root.get('sha256')):
        return False
    for slot in slots:
        if slot is root:
            continue
        source = slot.get('source_versions', {}).get(root['id'], {})
        if slot.get('ximalaya_source')!=root['id'] or source.get('att')!=root['att'] or source.get('sha256')!=proof['raw_sha256']:
            return False
    return True


def bind(round_):
    """Bind selected sizes to the audited artwork in their own set."""
    selected = placements(round_['params'])
    if not selected:
        return
    root_pid, *branches = selected
    roots = {slot['set']: slot for slot in round_['slots'] if slot['pid'] == root_pid}
    for slot in round_['slots']:
        if slot['pid'] not in branches or slot.get('ximalaya_source'):
            continue
        root = roots[slot['set']]
        slot.update(ximalaya_source=root['id'], first_id=root['id'], dependency_ids=[root['id']], refs=[{
            'label': '参考图1', 'path': root['output'],
            'role': '本套审核通过的首图，沿用人物、动作、场景、配色和字形。',
        }])
    round_['planning_targets'] = [key for key in round_['planning_targets'] if key.split('::')[0] not in branches]


def review(settings, slot, copy, stopped):
    from . import learning_visual

    path = Path(slot['logo_base']['path'])
    first = learning_visual.inspect(settings, path, copy, False, None, stopped, check_lettering=False)
    if learning_visual.clean(first) or first['verdict'] == 'unavailable':
        return first
    second = learning_visual.inspect(settings, path, copy, True, None, stopped, check_lettering=False)
    if second['verdict'] == 'unavailable':
        return second
    if learning_visual.clean(second):
        return {'verdict': 'review', 'issues': first['issues']}
    readings_agree = all(learning_visual.normalized(first[key]) == learning_visual.normalized(second[key])
                         for key in ('body', 'subtitle', 'cta'))
    confirmed = first['verdict'] == second['verdict'] == 'repair' or readings_agree and not learning_visual.text_matches(first, copy)
    return {'verdict': 'repair' if confirmed else 'review', 'issues': first['issues'] or second['issues']}


def repair_prompt(slot):
    issues = {entry['kind'] for entry in slot['ximalaya_review'].get('issues', [])}
    instruction = '以清晰完整的笔画和干净的填色逐字呈现主标题、副标题及已配置的按钮。'
    if issues & {'crop', 'overlap', 'composition'}:
        instruction += '拉远镜头并拉开元素间距，保全人物头部、手、道具和全部文字，让它们离四边有余量。'
    return slot['orig'] + '\n\n首图重出要求：\n' + instruction
