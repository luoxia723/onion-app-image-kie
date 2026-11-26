import json
import sys
import time
import pytest
from pathlib import Path
from PIL import Image
from local_app import worker


@pytest.mark.parametrize("query_only",[False,True])
def test_worker_manual_prose_passes_without_system_wording(tmp_path,monkeypatch,query_only):
    root=Path(__file__).parents[1]
    ref=next((root/'assets/font-references').glob('*.png'))
    prompt='自由编辑标题："自定文字"\n允许换行。'
    output=tmp_path/'new.png';job_path=tmp_path/'image.job.json'
    job={'simulation':False,'slot':{'idx':1,'refs':[{'label':'参考图1','path':str(ref),'role':'标题字体参考'}],
         'output':str(output),'prompt':prompt,'prompt_origin':'manual'},'placement':{'target_width':960,'target_height':540},
         'base':'https://example.invalid','upload':'https://example.invalid','stop_marker':str(tmp_path/'STOP'),'upload_cache':str(tmp_path/'cache.json')}
    job['query_only']=query_only
    if query_only:
        worker.render.task_state_path(output).write_text(json.dumps({'task_id':'same-paid-task','status':'waiting','submitted_at':time.time()-400,'fingerprint':'test-fingerprint'}))
        monkeypatch.setattr(worker.render,'request_fingerprint',lambda *a:'test-fingerprint')
    job_path.write_text(json.dumps(job));monkeypatch.setattr(sys,'argv',['worker',str(job_path)])
    monkeypatch.setenv('KIE_API_KEY','test-only')
    def forbidden(*a,**kw): raise AssertionError('manual prompt hit system wording validator')
    monkeypatch.setattr(worker.render,'validate_reference_labels',forbidden)
    monkeypatch.setattr(worker.render,'validate_logo_prompt_rule',forbidden)
    calls=[]
    def obtain(args,base,upload,key,text,paths,*rest,**kw):
        calls.append((text,paths,args.poll_timeout))
        return 'fake-result',{'task_id':'same-paid-task','status':'success'}
    monkeypatch.setattr(worker.render,'obtain_result',obtain)
    monkeypatch.setattr(worker.render,'download_image',lambda url,p:Image.new('RGB',(960,540)).save(p))
    assert worker.main()==0
    assert calls[0][:2]==(prompt,[ref.resolve()])
    assert calls[0][2]>=640 if query_only else calls[0][2]==240
    assert json.loads(job_path.with_suffix('.result.json').read_text())['ok']
