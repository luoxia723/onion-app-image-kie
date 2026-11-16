"""Per-placement ordinary Logo defaults, stored in the existing backed-up index.

Learning-machine presence and templates remain in their own contract. Ordinary
rounds freeze this configuration once; edits never rewrite an existing round.
"""
from __future__ import annotations

import copy

from .config import UserError
from . import brand_logo

DOCUMENT = 'ordinary_logo_templates'


def _placements():
    from .planning import BY_ID
    return {pid:p for pid,p in BY_ID.items() if p.get('enabled') and p.get('category') in ('应用商店','信息流')}


def _template(placement, value):
    from .learning_logo import _validated_template
    proxy={**placement,'modules':{'logo':placement.get('logo_policy')!='forbidden'}}
    result=_validated_template(proxy,value)
    # Both export variants must fit the same frozen rectangle.
    for aid in brand_logo._records():
        _validated_template(proxy,{**result,'asset_id':aid})
    return result


def _resolved(engine):
    state=engine.document(DOCUMENT,{'revision':0,'templates':{}})
    if (type(state.get('revision')) is not int or state['revision']<0 or not isinstance(state.get('templates'),dict)):
        raise UserError('普通广告Logo配置不完整，请检查本机配置记录')
    placements=_placements();templates={}
    for pid,p in placements.items():
        if p.get('logo_policy')=='forbidden':continue
        value=state['templates'].get(pid)
        if value is None:
            value={**brand_logo.default_template(p),'asset_id':brand_logo.DEFAULT}
            value.pop('position',None)
        templates[pid]=_template(p,value)
    return state,placements,templates


def public_config(engine):
    from .learning_logo import _public_assets
    with engine.lock:
        state,placements,templates=_resolved(engine)
        rows=[]
        for pid,p in placements.items():
            row={k:copy.deepcopy(p[k]) for k in ('id','category','platform','name','image_form','target_width','target_height','image_count','logo_policy')}
            row.update(logo_required=p.get('logo_policy')!='forbidden',logo_template=copy.deepcopy(templates.get(pid)))
            rows.append(row)
        return {'revision':state['revision'],'placements':rows,'logo_assets':_public_assets()}


def save_templates(engine,data):
    if (not isinstance(data,dict) or set(data)-{'revision','templates'} or type(data.get('revision')) is not int
            or not isinstance(data.get('templates'),list)):
        raise UserError('请提交当前配置版本和Logo模板列表')
    with engine.lock:
        if engine.maintenance_active:raise UserError('正在进行本机数据维护，请稍后保存配置')
        state,placements,_=_resolved(engine)
        if data['revision']!=state['revision']:raise UserError('另一窗口已更新Logo模板，请重新读取后保存',409)
        if len(data['templates'])>len(placements):raise UserError('Logo模板数量不正确')
        updates={}
        for row in data['templates']:
            if not isinstance(row,dict) or set(row)-{'placement_id','asset_id','x','y','width'}:
                raise UserError('Logo模板字段不正确')
            pid=row.get('placement_id')
            if not isinstance(pid,str) or pid not in placements or pid in updates:raise UserError('Logo版位不存在或重复')
            updates[pid]=_template(placements[pid],{k:v for k,v in row.items() if k!='placement_id'})
        next_templates={**state['templates'],**updates}
        if next_templates!=state['templates']:
            engine.put_document(DOCUMENT,{'revision':state['revision']+1,'templates':next_templates})
        return public_config(engine)


def snapshot(engine):
    with engine.lock:
        state,_,templates=_resolved(engine)
        return {'revision':state['revision'],'templates':copy.deepcopy(templates)}
