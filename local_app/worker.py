"""One image per process; the repository owns KIE submission/recovery semantics."""
from __future__ import annotations
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import render
from PIL import Image, ImageDraw, ImageFont


def simulate(job, output):
    time.sleep(float(os.environ.get('ONION_SIM_SECONDS', '1.4')))
    p, slot, pr = job['placement'], job['slot'], job['params']
    w, h = p['target_width'], p['target_height']
    palettes = [('#e9f0ff','#254ab0','#9fb6f4'),('#e9f4ee','#176749','#a5d1b8'),('#fff0e2','#a64d23','#e7b88b'),('#f0eafa','#7043a0','#c6b2df')]
    bg, ink, accent = palettes[(slot['set']-1)%len(palettes)]
    im = Image.new('RGB',(w,h),bg)
    dr = ImageDraw.Draw(im)
    u = min(w,h)
    dr.ellipse((w*.56,h*.24,w*1.10,h*1.05),fill=accent)
    dr.rounded_rectangle((w*.6,h*.39,w*.89,h*.76),radius=max(2,int(u*.025)),fill='#ffffff')
    font_path = next((p for p in ['/System/Library/Fonts/PingFang.ttc','/System/Library/Fonts/Hiragino Sans GB.ttc','/System/Library/Fonts/Supplemental/Arial Unicode.ttf','C:/Windows/Fonts/msyh.ttc','/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'] if Path(p).exists()),None)
    def font(size): return ImageFont.truetype(font_path, max(10,int(size))) if font_path else ImageFont.load_default()
    title = pr.get('t1','') if p['image_count']==1 else pr.get('s'+str(slot['idx']),'')
    fs = min(u*.09,w*.78/max(5,min(len(title),12)))
    chars=max(4,int(w*.78/fs))
    lines=[title[i:i+chars] for i in range(0,len(title),chars)][:4]
    y=h*.20
    for line in lines:
        dr.text((w*.08,y),line,font=font(fs),fill=ink)
        y+=fs*1.4
    if p['image_count']==1:
        sub=pr.get('t2','')
        dr.text((w*.08,min(h*.63,y+u*.045)),sub[:24],font=font(u*.038),fill=ink)
    if pr.get('cta'):
        dr.rounded_rectangle((w*.08,h*.78,w*.43,h*.90),radius=max(3,int(u*.03)),fill=ink)
        dr.text((w*.10,h*.80),pr['cta'],font=font(u*.044),fill='white')
    dr.text((w*.04,h*.04),'模拟预览',font=font(u*.032),fill=ink)
    im.save(output,'PNG')


def main():
    job = json.loads(Path(sys.argv[1]).read_text())
    output = Path(job['slot']['output'])
    output.parent.mkdir(parents=True,exist_ok=True)
    result_file=Path(sys.argv[1]).with_suffix('.result.json')
    def progress(stage):render.atomic_write_json(output.with_suffix('.progress.json'),{'stage':stage,'at':time.time()})
    failed_references=[]
    if job['simulation']:progress('generating')
    try:
        if job['simulation']:
            simulate(job, output)
            result={'ok':True,'source':str(output)}
        else:
            from local_app.kie_client import generate
            result=generate(job,os.environ['KIE_API_KEY'],failed_references,progress)
        render.atomic_write_json(result_file,result)
    except Exception as exc:
        state_path=render.task_state_path(output)
        state=json.loads(state_path.read_text()) if state_path.exists() else {}
        unknown=(bool(state.get('task_id')) and state.get('status')!='fail' and not isinstance(exc,render.GenerationTimeout)) or state.get('status') in ('submitting','submit_uncertain') or (isinstance(exc,render.KieError) and getattr(exc,'uncertain_submit',False))
        rate_limited=('HTTP 429' in str(exc) or 'failed (429)' in str(exc)) and not state.get('task_id')
        if rate_limited:
            state['status']='rate_limited'
            render.atomic_write_json(state_path,state)
        from local_app.kie_client import ImageExecutionBusy
        reason='busy' if isinstance(exc,ImageExecutionBusy) else 'disk_full' if getattr(exc,'status',None)==507 else 'stopped' if str(exc)=='onion_stopped' else 'rate_limited' if rate_limited else 'unknown' if unknown else 'timeout' if isinstance(exc,render.GenerationTimeout) else 'no_image'
        if isinstance(exc,ValueError) and 'prompt' in str(exc).lower(): reason='prompt_rejected'
        # Provider response bodies are deliberately never forwarded or logged.
        render.atomic_write_json(result_file,{'ok':False,'reason':reason,'state':state,'failed_references':failed_references})
        return 1
    return 0

if __name__=='__main__': sys.exit(main())
