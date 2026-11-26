"""KIE adapter with per-request dependencies and crash-safe upload cache locks."""
import json
import time
from contextlib import contextmanager, nullcontext
from pathlib import Path
from types import SimpleNamespace
from .config import ROOT,UserError
from .instance import InstanceLock
import render
from kie_model import normalize_model

@contextmanager
def file_lock(path):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);deadline=time.monotonic()+120
    while True:
        try: lock=InstanceLock(path);break
        except UserError:
            if time.monotonic()>deadline:raise ValueError('upload busy')
            time.sleep(.1)
    try:yield
    finally:lock.close()


class ImageExecutionBusy(Exception):pass


def generate(job,key,failed_references,progress):
    output=Path(job['slot']['output']);output.parent.mkdir(parents=True,exist_ok=True)
    try:lock=InstanceLock(output.with_suffix(output.suffix+'.execution.lock'))
    except UserError:raise ImageExecutionBusy('该图片版本仍有执行器占用') from None
    try:
        from .safety import require_space
        require_space(output)
        return _generate(job,key,failed_references,progress)
    finally:lock.close()


def _generate(job,key,failed_references,progress):
    if job['slot'].get('production_mode')=='local_resize':raise UserError('本机缩放任务不能提交图片模型')
    from .learning_delivery import require_confirmed_sample
    if not job.get('query_only'):require_confirmed_sample(job['placement'])
    slot=job['slot'];output=Path(slot['output']);refs=slot['refs']
    if slot.get('frame'):raise UserError('此制作流程已停用，请重新提交配置制作')
    paths=[(Path(r['path']) if Path(r['path']).is_absolute() else ROOT/r['path']).resolve() for r in refs]
    from poster_prompt import validate_text
    validate_text(slot['prompt'])
    if slot.get('brand_logo_layer'):
        from .brand_logo import validate_prompt
        validate_prompt(slot['prompt'],slot['brand_logo_layer'])
    if slot.get('natural_canvas_plan'):
        from .natural_canvas import validate_prompt as validate_canvas_prompt
        validate_canvas_prompt(slot['prompt'],slot['natural_canvas_plan'])
    if slot.get('prompt_origin')!='manual':
        render.validate_reference_labels(slot['prompt'],refs);render.validate_logo_prompt_rule(slot['prompt'],refs)
    render.validate_asset_reference_bindings(refs)
    model=normalize_model(job.get('image_model',render.MODEL))
    ratio=render.nearest_aspect_ratio(job['placement']['target_width'],job['placement']['target_height'],model)
    if slot.get('natural_canvas_plan'):
        from .natural_canvas import aspect_ratio
        ratio=aspect_ratio(slot['natural_canvas_plan'])
    fingerprint=render.request_fingerprint(model,slot['prompt'],paths,ratio,render.RESOLUTION)
    state_path=render.task_state_path(output);state=render.load_output_state(output)
    if state.get('status')=='rate_limited':state={}
    if state and state.get('fingerprint')!=fingerprint:raise ValueError('fingerprint')
    if job.get('query_only') and not state.get('task_id'):raise ValueError('unknown')
    timeout=240;submitted=state.get('submitted_at')
    if job.get('query_only') and type(submitted) in (int,float):timeout+=max(0,int(time.time()-submitted))
    args=SimpleNamespace(image_model=model,retries=3,poll_timeout=timeout)
    cache_path=Path(job['upload_cache']);guard=cache_path.with_suffix('.guard')
    def read_cache():
        try:return json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
        except (OSError,ValueError):return {}
    def upload(upload_base,api_key,images,retries,cache=None):
        progress('uploading');urls=[]
        for path in images:
            digest=render.sha256_file(path)
            with file_lock(cache_path.parent/'reference-locks'/(digest+'.guard')):
                with file_lock(guard):saved=read_cache().get(digest)
                if saved and time.time()-saved['at']<20*3600:urls.append(saved['url']);continue
                fresh={}
                try:url=render.upload_references(upload_base,api_key,[path],retries,cache=fresh)[0]
                except Exception:
                    failed_references.extend(i for i,p in enumerate(paths) if p==path);raise
                with file_lock(guard):
                    saved=read_cache();saved[digest]={'url':url,'at':time.time()};render.atomic_write_json(cache_path,saved)
                urls.append(url)
        return urls
    def request(req,*a,**kw):
        creating='/jobs/createTask' in req.full_url
        if creating:
            if Path(job['stop_marker']).exists():raise RuntimeError('onion_stopped')
            progress('submitting')
        result=render.request_json(req,*a,**kw)
        if creating:progress('generating')
        return result
    @contextmanager
    def submission_guard():
        source=slot.get('ximalaya_source')
        if source:progress('awaiting_submit')
        # Keep the lock until the receipt is saved, then allow polling in parallel.
        with file_lock(output.parent/(source+'-create.guard')) if source else nullcontext():
            if Path(job['stop_marker']).exists():raise RuntimeError('onion_stopped')
            yield
    if not (state.get('status')=='downloaded' and output.exists() and render.sha256_file(output)==state.get('sha256')):
        progress('generating' if state.get('task_id') else 'uploading')
        url,state=render.obtain_result(args,job['base'],job['upload'],key,slot['prompt'],paths,fingerprint,state_path,state,ratio,render.RESOLUTION,
                                       request_fn=request,upload_fn=upload,submission_guard=submission_guard)
        progress('downloading')
        render.download_kie_result(url,output,job['base'],key,state['task_id'])
        state.update(status='downloaded',sha256=render.sha256_file(output));render.atomic_write_json(state_path,state)
    result={'ok':True,'source':str(output),'state':state}
    progress('processing')
    return result
