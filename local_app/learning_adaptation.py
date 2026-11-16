"""One authoritative adaptation plan for preview and execution.

Geometry alone never proves an uploaded ad can be reused. Direct pixel reuse
also needs a confirmed source layout, unchanged visible copy/modules, enough
pixels, and an identity or a previously reviewed resize relationship.
"""

COVERS=('learning-bbg-cover-400x480','learning-bbg-cover-300x360','learning-bbg-cover-216x260')

def signature(pr,p,*,original=None):
    modules=p['learning_rule']['modules'];copy=original if original is not None else pr
    fields={key:copy.get(key,'') if modules[module] else '' for key,module in
            [('feature_label','feature_label'),('t1','main_copy'),('t2','main_copy'),('extra_heading','extra_heading'),('extra_description','extra_description')]}
    cta=copy.get('cta','')
    if original is None:
        override=pr.get('cta_overrides',{}).get(p['id'],{})
        cta=override.get('text','') if override.get('mode')=='custom' else '' if override.get('mode')=='none' or pr.get('cta_enabled') is False else cta
    fields['cta']=cta if modules['cta'] else ''
    return (modules,fields,(copy.get('original_logo_asset_id') if original is not None else pr.get('logo_asset_id')) or 'logo.onion.standard.001' if modules['logo'] else '')

def reachable(source_pid,target_pid,placements):
    if source_pid==target_pid:return True
    if source_pid in COVERS and target_pid in COVERS:return COVERS.index(source_pid)<COVERS.index(target_pid)
    target=placements[target_pid]['learning_rule']
    return target['model_call_for_this_derivative'] is False and target['default_parent']==source_pid

def direct_reason(pr,p,placements):
    source=pr.get('learning_source') or {};pid=source.get('layout_id');layout=placements.get(pid)
    if source.get('layout_confirmed') is not True or not layout or not layout.get('learning_rule') or layout.get('enabled') is False:
        return False,'原图版式未确认，按目标样图进行 AI 适配'
    width=source.get('width',0);height=source.get('height',0)
    if not width or not height or abs(width/height/(layout['target_width']/layout['target_height'])-1)>.015:
        return False,'原图比例与确认版式不符，需要 AI 调整构图'
    if not reachable(pid,p['id'],placements):return False,'与原图不属于已验证的共用组，需要 AI 调整构图或模块'
    if width<p['target_width'] or height<p['target_height']:return False,'原图像素不足以直接导出此尺寸，需要 AI 适配'
    baseline=source.get('copy_snapshot')
    visible=layout['learning_rule']['modules']
    required=[key for key,module in [('feature_label','feature_label'),('t1','main_copy'),('t2','main_copy'),('cta','cta'),('extra_heading','extra_heading'),('extra_description','extra_description')] if visible[module]]
    if required and (not isinstance(baseline,dict) or any(not baseline.get(key,'').strip() for key in required)):
        return False,'原图文案尚未完整核对，需要 AI 按确认稿适配'
    baseline={**(baseline or {}),'original_logo_asset_id':source.get('original_logo_asset_id','logo.onion.standard.001')}
    if signature(pr,p)!=signature(pr,layout,original=baseline):return False,'文案、按钮或 Logo 与原图不同，需要 AI 编辑'
    return True,'原图版式与内容已确认；仅处理尺寸、圆角和交付规格'

def plan(pr,placements):
    selected=[placements[pid] for pid in pr.get('pids',[]) if pid in placements and placements[pid].get('learning_rule')]
    ids={p['id'] for p in selected};parents={}
    for p in selected:
        rule=p['learning_rule'];parent=rule['default_parent']
        if not rule['model_call_for_this_derivative'] and parent in ids:parents[p['id']]=parent
    covers=[pid for pid in COVERS if pid in ids]
    if covers:
        for child in covers[1:]:parents[child]=covers[0]
    rows=[]
    for p in selected:
        pid=p['id'];direct,reason=direct_reason(pr,p,placements)
        method='source_resize' if direct else 'ai_edit';parent=None
        if not direct and pid in parents and signature(pr,p)==signature(pr,placements[parents[pid]]):
            method='local_resize';parent=parents[pid];reason='与组内母版的文案和模块一致；母版完成后在本机缩放或处理圆角'
        elif not direct and pid in parents:reason='与组内母版的文案或按钮不同，需要单独 AI 编辑'
        if method=='ai_edit' and p['learning_rule']['production_action']=='模块变体':
            parent=p['learning_rule']['default_parent'] if p['learning_rule']['default_parent'] in ids else None
        rows.append({'pid':pid,'platform':p['platform'],'name':p['name'],'size':p['target_size'],'method':method,'parent_pid':parent,'reason':reason})
    direct=sum(r['method']=='source_resize' for r in rows);local=sum(r['method']=='local_resize' for r in rows)
    return {'rows':rows,'total':len(rows),'source_outputs':direct,'derived_outputs':local,'model_tasks':len(rows)-direct-local,'local_outputs':direct+local}
