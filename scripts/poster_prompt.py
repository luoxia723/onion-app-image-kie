"""Readable GPT Image briefs, using frozen visual plans and ordered assets."""
from positive_prompt import approved_copy, task_rule, font_rule, inherited_font_rule, branch_title_rule, readability_rule, CONTENT_RULE, is_font_reference


def validate_text(prompt):
    if not isinstance(prompt,str) or not prompt.strip():
        raise ValueError('提示词不能为空')
    if len(prompt)>30000:
        raise ValueError('提示词最多30000字')


def compose(config,direction,slot,references,frame_label):
    from logo_reference import logo_position,logo_prompt_rule
    from cta_rules import prompt_rule as cta_rule
    from blue_frame import prompt_rule as frame_rule
    count=int(config['placements'][0].get('image_count',1))
    source=next((x for x in config['copy_refs'] if x.get('copyDraftId')==direction.get('copy_draft_id')),None)
    if source is None and len(config['copy_refs'])==1: source=config['copy_refs'][0]
    if source is None: raise ValueError('approved copy missing')
    texts=approved_copy(source,slot,count)
    scene=direction['base_prompt_rule'] if slot==1 else direction['slot_prompt_rules'][str(slot)]
    action=(direction.get('learner_story') or {}).get('product_action','')
    if count==1 and action and action not in scene: scene+='。'+action
    sections=[('任务',task_rule(config)),('画面描述',scene)]
    copy=[]
    if texts[0]:
        copy.append('主标题："'+texts[0]+'"。逐字呈现，仅出现一次，作为第一文字层级完整排布；引号本身不画入图片。')
        if slot>1: copy.append(branch_title_rule(texts[0]))
    if len(texts)>1 and texts[1]:
        copy.append('副标题："'+texts[1]+'"。逐字呈现，仅出现一次，字号小于主标题，形成清楚的第二文字层级。')
    if config.get('cta'): copy.append(cta_rule(config['cta']))
    copy.append('本张未列出的副标题、按钮和其他广告文案不添加；品牌Logo原有标准字按品牌参考保留。')
    sections.append(('画面文字','\n'.join(copy)))
    roles=[]
    if slot==1:
        for ref in references:
            label=ref['label'];asset=ref.get('asset_id','');role=ref.get('role','')
            if asset.startswith('logo.'): text=logo_prompt_rule(label,logo_position(config))
            elif asset.startswith('ip.'): text=label+'：角色身份参考，保留识别特征与服装核心配色；人物的画法和材质服从本张画风。'
            elif is_font_reference(ref): text=font_rule(label)+'样张旧字句及附带贴纸、吉祥物不作为本张画面内容。'
            elif frame_label==label: text=label+'：本版位蓝框布局与安全范围参考。'
            elif ref.get('purpose')=='ui' or direction.get('screen_ui_mode')=='reference' and ('UI' in role or '截图' in role):
                text=label+'：真实界面截图，用于画面中的产品屏幕；保留原有布局与已提供的界面内容，不编造新功能、界面文字或数字。'+role
            else: text=label+'：'+role
            roles.append(text)
    else:
        roles.append(references[0]['label']+'：本套本版位当前首图原始PNG，是本张实际使用的图像参考。')
    sections.append(('参考图用途','\n'.join(roles)))
    if slot>1:
        keep=[direction['branch_prompt_rule']]
        if config.get('font_reference_enabled',True): keep.append(inherited_font_rule())
        keep.append('保持角色身份、画风与材质、品牌标识和字体体系；动作、机位与标题留白按本张画面任务调整。')
        if direction.get('screen_ui_mode')=='reference':keep.append('若本张出现产品屏幕，沿用首图中的真实界面内容，不凭空替换页面或增加界面功能。')
        sections.append(('保持与变化','\n'.join(keep)))
    rules=[readability_rule(),CONTENT_RULE]
    if frame_label: rules.append(frame_rule(frame_label))
    sections.append(('画面约束','\n'.join(rules)))
    prompt='\n\n'.join(name+'：\n'+text for name,text in sections)
    validate_text(prompt)
    from positive_prompt import validate_visual_contract
    validate_visual_contract(config,prompt,references,slot,texts[0])
    return prompt
