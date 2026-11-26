"""Verify a missing KIE receipt before allowing query or an explicit replacement."""

import json
from pathlib import Path
import re
import time

import render

from .config import UserError
from .instance import InstanceLock


BLOCKED_RECEIPT_MESSAGE='本机 KIE 回执缺失或无法读取。请核对 KIE 任务记录，或恢复包含回执的备份。'


def receipt_recovery_action(path, *, expected=False):
    try:
        state=render.load_task_state(path) if path else {}
    except render.KieError:
        return 'blocked'
    if render.submission_unverified(state):return 'reconcile'
    if render.confirmed_unaccepted(state):return 'retry'
    status=state.get('status')
    if status in ('fail','rejected','rate_limited'):return None
    if isinstance(state.get('task_id'),str) and state['task_id'].strip():return 'resume'
    return 'blocked' if state or expected else None


def pending_receipt(path):
    try:
        state=render.load_task_state(path)
    except render.KieError:
        return {}
    return state if render.submission_unverified(state) else {}


def _object(value):
    try:
        if isinstance(value,str):value=json.loads(value)
    except ValueError:
        return {}
    return value if isinstance(value,dict) else {}


def verify_task(settings, task_id, receipt, prompt):
    if not isinstance(task_id,str) or not re.fullmatch(r'[A-Za-z0-9._:-]{1,200}',task_id):
        raise UserError('请填写 KIE 记录中的任务号')
    if not settings.key:
        raise UserError('请先在设置中填写 KIE Key')
    try:
        request=render.build_status_request(settings.base,settings.key,task_id)
        data=_object(render.request_json(request,1,operation='verify KIE receipt',request_timeout=15).get('data'))
    except render.KieError:
        raise UserError('无法读取这个 KIE 任务，请核对任务号和当前 KIE 账号',409) from None
    param=_object(data.get('param'))
    inputs=_object(param.get('input'))
    model=param.get('model') or data.get('model')
    created,submitted=data.get('createTime'),receipt.get('submitted_at')
    time_matches=(type(created) in (int,float) and type(submitted) in (int,float)
                  and -30<=created/1000-submitted<=180)
    if receipt.get('submission_signature'):
        matches=render.submission_signature(model,inputs)==receipt['submission_signature']
        if created is not None:matches=matches and time_matches
    else:
        prompts=(prompt,) if isinstance(prompt,str) else prompt
        matches=(time_matches and bool(prompts) and inputs.get('prompt') in prompts and model==receipt.get('model')
                 and inputs.get('aspect_ratio')==receipt.get('aspect_ratio')
                 and inputs.get('resolution')==receipt.get('resolution'))
    if (data.get('taskId')!=task_id or data.get('state') not in ('waiting','queuing','generating','success','fail')
            or not matches):
        raise UserError('任务号与本图冻结的生图请求不一致，请重新核对',409)
    return task_id


def claim_receipt(engine, output, path, expected, task_id):
    """Commit the checked receipt under the engine lock and image execution lock."""
    lock=InstanceLock(Path(output).with_suffix(Path(output).suffix+'.execution.lock'))
    try:
        if pending_receipt(path)!=expected:
            raise UserError('图片回执已更新，请刷新后再操作',409)
        now=time.time()
        if task_id:
            key='kie-reconciled:'+task_id
            owner=str(path.resolve())
            existing=engine.document(key)
            if existing and existing!=owner:
                raise UserError('这个 KIE 任务号已接回另一张图片',409)
            engine.put_document(key,owner)
            state={**expected,'task_id':task_id,'status':'waiting','reconciliation':{'attached_at':now}}
        else:
            state={**expected,'status':'confirmed_unaccepted','reconciliation':{'confirmed_unaccepted_at':now}}
        render.atomic_write_json(path,state)
    finally:
        lock.close()
