"""Readable GPT Image briefs, using frozen visual plans and ordered assets."""
from positive_prompt import approved_copy, task_rule, font_rule, inherited_font_rule, branch_title_rule, readability_rule, CONTENT_RULE, is_font_reference


def validate_text(prompt):
    if not isinstance(prompt,str) or not prompt.strip():
        raise ValueError('提示词不能为空')
    if len(prompt)>30000:
        raise ValueError('提示词最多30000字')


def compose(config,direction,slot,references):
    from logo_reference import logo_position,logo_prompt_rule
    from cta_rules import prompt_rule as cta_rule
    count=int(config['placements'][0].get('image_count',1))
    source=next((x for x in config['copy_refs'] if x.get('copyDraftId')==direction.get('copy_draft_id')),None)
    if source is None and len(config['copy_refs'])==1: source=config['copy_refs'][0]
    if source is None: raise ValueError('approved copy missing')
    texts=approved_copy(source,slot,count)
    scene=direction['base_prompt_rule'] if slot==1 else direction['slot_prompt_rules'][str(slot)]
    action=(direction.get('learner_story') or {}).get('product_action','')
    if count==1 and action and action not in scene: scene+='。'+action
    if config.get('ximalaya_variant'):
        scene=('沿用参考图中同一广告的角色、场景、主要动作、道具、画风、配色和字形。'
               '按目标画幅重新安排人物与文字，可调整机位、断行、字号与位置。留足边距，背景自然延伸到四边。'
               '完整保留主标题、副标题和已列出的按钮文案，避免背景或人物盖住文字。')
    sections=[('任务',task_rule(config)),('画面描述',scene)]
    copy=[]
    learning=config.get('learning_copy')
    if learning is not None:
        if learning.get('feature_label'):copy.append('功能名："'+learning['feature_label']+'"。逐字呈现，仅出现一次。')
        lines=[learning[k] for k in ('t1','t2') if learning.get(k)]
        if lines:copy.append('主文案：'+ ' / '.join('"'+line+'"' for line in lines)+'。作为同一层级的一组文案逐字呈现，两行保持相同的阅读重要性；按当前版位调整断行与间距。')
        for key,label in [('extra_heading','底部标题'),('extra_description','底部说明')]:
            if learning.get(key):copy.append(label+'："'+learning[key]+'"。逐字呈现，仅出现一次。')
        if not any(learning.values()):copy.append('本版位只呈现场景与人物，不添加功能名、主文案或其他营销文字。')
    elif texts[0]:
        copy.append('主标题："'+texts[0]+'"。逐字呈现，仅出现一次，作为第一文字层级完整排布；引号本身不画入图片。')
        if slot>1: copy.append(branch_title_rule(texts[0]))
    if learning is None and len(texts)>1 and texts[1]:
        copy.append('副标题："'+texts[1]+'"。逐字呈现，仅出现一次，字号小于主标题，形成清楚的第二文字层级。')
    if config.get('cta'): copy.append(cta_rule(config['cta']))
    elif learning is not None:copy.append('本版位没有按钮，不绘制按钮文字、空按钮框或下载标识。')
    copy.append('本张未列出的副标题、按钮和其他广告文案不添加。'+('品牌 Logo 原有标准字按品牌参考保留。' if config.get('logo')!='不用' else '画面不出现品牌 Logo 或品牌标识。'))
    sections.append(('画面文字','\n'.join(copy)))
    roles=[]
    if slot==1:
        for ref in references:
            label=ref['label'];asset=ref.get('asset_id','');role=ref.get('role','')
            if asset.startswith('logo.'): text=logo_prompt_rule(label,logo_position(config))
            elif asset.startswith('ip.'): text=label+'：角色身份参考，保留识别特征与服装核心配色；人物的画法和材质服从本张画风。'
            elif is_font_reference(ref): text=font_rule(label)+'样张旧字句及附带贴纸、吉祥物不作为本张画面内容。'
            elif ref.get('purpose')=='layout_sample':text=label+'：'+role
            elif ref.get('purpose')=='ui' or direction.get('screen_ui_mode')=='reference' and ('UI' in role or '截图' in role):
                text=label+'：真实界面截图，用于画面中的产品屏幕；保留原有布局与已提供的界面内容，不编造新功能、界面文字或数字。'+role
            else: text=label+'：'+role
            roles.append(text)
    else:
        roles.append(references[0]['label']+'：本套本版位当前首图原始PNG，是本张实际使用的图像参考。')
    sections.append(('参考图用途','\n'.join(roles)))
    if config.get('learning_production_mode')=='template_extension':
        sections.append(('首模板扩展','本张使用参考图中本套首模板的角色身份、动作、场景、画风、配色和字体体系。仅为目标尺寸调整构图、留白和已列出的文案模块；不另创主题或换人。首模板里本张未列出的文字、按钮和Logo应完整移除，保留连续自然的场景背景。'))
    if slot>1:
        keep=[direction['branch_prompt_rule']]
        if config.get('font_reference_enabled',True): keep.append(inherited_font_rule())
        keep.append('保持角色身份、画风与材质'+('、品牌标识' if config.get('logo')!='不用' else '')+'和字体体系；动作、机位与标题留白按本张画面任务调整。')
        if direction.get('screen_ui_mode')=='reference':keep.append('若本张出现产品屏幕，沿用首图中的真实界面内容，不凭空替换页面或增加界面功能。')
        sections.append(('保持与变化','\n'.join(keep)))
    rules=[readability_rule(),CONTENT_RULE]
    if config.get('brand_logo_layer'):
        from local_app.brand_logo import prompt_rule as brand_rule
        rules.append(brand_rule(config['brand_logo_layer']))
    if config['placements'][0].get('generation_rule'):rules.append(config['placements'][0]['generation_rule'])
    if config.get('natural_canvas_plan'):
        from local_app.natural_canvas import prompt_rule as canvas_rule
        rules.append(canvas_rule(config['natural_canvas_plan']))
    sections.append(('画面约束','\n'.join(rules)))
    prompt='\n\n'.join(name+'：\n'+text for name,text in sections)
    validate_text(prompt)
    from positive_prompt import validate_visual_contract
    validate_visual_contract(config,prompt,references,slot,texts[0])
    return prompt
