"""One durable queue shared by every browser, with fair task admission."""
import time
from pathlib import Path

STAGES={'uploading':'正在上传参考图','generating':'正在生成','downloading':'正在下载','processing':'正在处理尺寸'}

class SchedulerMixin:
    def queue_status(self):
        with self.lock:
            queued=waiting=running=paused=planning=0
            for t in self.tasks.values():
                if t.get('deleted_at'): continue
                for r in t['rounds']:
                    planning+=r.get('planning_status')=='running'
                    for s in r['slots']:
                        if s['state']=='generating': running+=1
                        elif s['state']=='queued':
                            if r.get('paused'): paused+=1
                            elif not r.get('stopped'):
                                head=next((x for x in r['slots'] if x['id']==s['first_id']),s)
                                if not s.get('plan_ready',True) or s['idx']>1 and head['state']!='done': waiting+=1
                                else: queued+=1
            return dict(running=running,queued=queued,waiting=waiting,paused=paused,planning=planning,
                        limit=min(self.throttle,self.settings.concurrency),blocked_reason=(self.last_scheduler_error or {}).get('message'),maintenance=self.maintenance_active)

    def dispatch_tick(self):
        with self.lock:
            if self.maintenance_active:return
            from .safety import require_space
            try:require_space(self.settings.output,self.settings.concurrency*16*1024*1024)
            except Exception as exc:
                self.last_scheduler_error={'message':getattr(exc,'message','磁盘检查未完成'),'at':time.time()};return
            if self.last_scheduler_error and self.last_scheduler_error.get('kind')!='scheduler':self.last_scheduler_error=None
            if self.throttle<20 and time.time()>=self.next_throttle_recovery:
                self.throttle+=1;self.next_throttle_recovery=time.time()+30
            queues={}
            tasks=list(self.tasks.values())
            ids=[t["id"] for t in tasks]
            if self.last_planned in ids:
                i=ids.index(self.last_planned)+1;tasks=tasks[i:]+tasks[:i]
            for t in tasks:
                if t.get('deleted_at'): continue
                for r in t['rounds']:
                    pkey=(t['id'],r['id'])
                    if not self.planning_running and r.get('planning_status')=='queued' and not r.get('stopped') and not r.get('paused'):
                        r['planning_status']='running';self.last_planned=t['id'];self.planning_running.add(pkey);self.persist(t)
                        self.planning_pool.submit(self.plan_round,t,r,pkey)
                    changed=False
                    for s in r['slots']:
                        if s['state']=='generating': self.sync_provider_ids(t,s)
                        if time.time()<s.get('retry_after',0):continue
                        if s['state']!='queued' or not s.get('plan_ready',True) or r.get('paused') or r.get('stopped'): continue
                        head=next((x for x in r['slots'] if x['id']==s['first_id']),s)
                        if s['idx']>1 and head['state'] in ('failed','blocked_first_failed','stopped'):
                            s.update(state='blocked_first_failed',reason_code='first_failed',msg='图 1 还没完成，请先处理图 1');changed=True;continue
                        if s['idx']>1 and head['state']!='done': continue
                        queues.setdefault(t['id'],[]).append((t,r,s))
                    if changed:self.persist(t)
            for jobs in queues.values():jobs.sort(key=lambda x:(x[2]['idx']==1,x[2].get('t0',0)))
            order=list(queues)
            if self.last_dispatched in order:
                i=order.index(self.last_dispatched)+1;order=order[i:]+order[:i]
            limit=min(self.throttle,self.settings.concurrency)
            while order and len(self.running)<limit and time.time()>=self.next_submit:
                tid=order.pop(0);t,r,s=queues[tid].pop(0)
                s.update(state='generating',stage='uploading',t0=time.time()*1000)
                if s['idx']>1:
                    head=next(x for x in r['slots'] if x['id']==s['first_id'])
                    s['head_version']=head['att']
                key=(t['id'],r['id'],s['id']);self.running.add(key);self.last_dispatched=tid
                try:self.persist(t)
                except Exception:
                    self.running.discard(key);s.update(state='queued',stage='queued');raise
                self.pool.submit(self.generate,t,r,s,key)
                if queues[tid]:order.append(tid)

    def loop(self):
        last_cleanup=0
        while not self.closed.wait(.2):
            try:
                if time.time()-last_cleanup>30:self.cleanup();last_cleanup=time.time()
                self.dispatch_tick()
            except Exception:
                self.last_scheduler_error={'kind':'scheduler','message':'后台遇到本机读写异常，任务保留，正在重试；可查看数据维护','at':time.time()}
                self.closed.wait(1)
