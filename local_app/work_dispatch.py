"""Bounded, owner-fair image admission over a shared thread pool.

FIFO is the admission order within each owner; concurrent work may finish in
any order. Provider limits and user functions/callbacks run outside our condition.
"""
from __future__ import annotations

from collections import deque
from concurrent.futures import Future,ThreadPoolExecutor
from dataclasses import dataclass
import threading
import weakref

from .config import UserError


@dataclass
class _Job:
    owner:str
    fn:object
    args:tuple
    kwargs:dict
    future:Future
    state:str='queued'


class FairImagePool:
    def __init__(self,max_workers=20,limit_provider=None,max_pending=512):
        if type(max_workers) is not int or max_workers<1:raise ValueError('max_workers must be positive')
        if type(max_pending) is not int or max_pending<1:raise ValueError('max_pending must be positive')
        if limit_provider is not None and not callable(limit_provider):raise TypeError('limit_provider must be callable')
        self._max_workers=max_workers;self._max_pending=max_pending
        self._limit_provider=limit_provider or (lambda:max_workers)
        self._condition=threading.Condition()
        self._queues={};self._owners=deque();self._jobs={};self._counts={}
        self._active=0;self._running=0;self._queued=0;self._revision=0;self._last_limit=0
        self._closing=False;self._cancel_pending=False
        self._workers=ThreadPoolExecutor(max_workers=max_workers,thread_name_prefix='onion-image')
        self._dispatcher=threading.Thread(target=self._dispatch,name='onion-image-dispatch',daemon=True)
        self._dispatcher.start()

    def _read_limit(self):
        try:value=self._limit_provider()
        except Exception:return 0
        return min(self._max_workers,max(0,value)) if type(value) is int else 0

    def _changed(self):
        self._revision+=1;self._condition.notify_all()

    def _adjust(self,owner,*,queued=0,running=0):
        values=self._counts.setdefault(owner,{'running':0,'queued':0})
        values['running']+=running;values['queued']+=queued
        if not values['running'] and not values['queued']:self._counts.pop(owner,None)

    def submit(self,fn,/,*args,**kwargs):
        task=args[0] if args and isinstance(args[0],dict) else {}
        owner='generic:'+str(task['id']) if task.get('id') else 'generic'
        return self.submit_for(owner,fn,*args,**kwargs)

    def submit_for(self,owner,fn,/,*args,**kwargs):
        if not isinstance(owner,str) or not owner or len(owner)>256:raise ValueError('owner must be a short nonempty string')
        if not callable(fn):raise TypeError('fn must be callable')
        future=Future();job=_Job(owner,fn,args,kwargs,future)
        pool_ref=weakref.ref(self)
        def cancelled(done):
            pool=pool_ref()
            if pool is not None and done.cancelled():pool._cancelled(done)
        future.add_done_callback(cancelled)
        with self._condition:
            if self._closing:raise RuntimeError('cannot schedule new futures after shutdown')
            if self._queued>=self._max_pending:raise UserError('图片等待队列已满，请稍后重试',429)
            queue=self._queues.get(owner)
            if queue is None:
                queue=self._queues[owner]=deque();self._owners.append(owner)
            queue.append(job);self._jobs[future]=job;self._queued+=1
            self._adjust(owner,queued=1);self._changed()
        return future

    def _cancelled(self,future):
        with self._condition:
            job=self._jobs.get(future)
            if job is None:return
            if job.state=='queued':
                queue=self._queues[job.owner];queue.remove(job)
                if not queue:
                    self._queues.pop(job.owner);self._owners.remove(job.owner)
                self._jobs.pop(future);job.state='cancelled'
            elif job.state=='dispatched':job.state='cancelled_dispatched'
            else:return
            self._queued-=1;self._adjust(job.owner,queued=-1);self._changed()

    def _take(self):
        owner=self._owners.popleft();queue=self._queues[owner];job=queue.popleft()
        if queue:self._owners.append(owner)
        else:self._queues.pop(owner)
        job.state='dispatched';self._active+=1;self._changed()
        return job

    def _finish_unstarted(self,job):
        with self._condition:
            if job.state=='dispatched':
                self._queued-=1;self._adjust(job.owner,queued=-1)
            self._active-=1;job.state='done';self._jobs.pop(job.future,None);self._changed()

    def _invoke(self,job):
        if not job.future.set_running_or_notify_cancel():
            self._finish_unstarted(job);return
        with self._condition:
            job.state='running';self._queued-=1;self._running+=1
            self._adjust(job.owner,queued=-1,running=1);self._changed()
        result=None;error=None
        try:result=job.fn(*job.args,**job.kwargs)
        except BaseException as exc:error=exc
        finally:
            with self._condition:
                self._active-=1;self._running-=1;job.state='done';self._jobs.pop(job.future,None)
                self._adjust(job.owner,running=-1);self._changed()
        # Standard Future invokes user callbacks here; never under our lock.
        if error is None:job.future.set_result(result)
        else:job.future.set_exception(error)

    def _dispatch(self):
        try:
            while True:
                with self._condition:
                    if self._closing and (self._cancel_pending or not self._owners):break
                    revision=self._revision
                limit=self._read_limit()
                with self._condition:
                    if revision!=self._revision:continue
                    self._last_limit=limit
                    if self._closing and (self._cancel_pending or not self._owners):break
                    if not self._owners or self._active>=limit:
                        self._condition.wait(.05);continue
                    job=self._take()
                try:self._workers.submit(self._invoke,job)
                except BaseException as exc:
                    active=job.future.set_running_or_notify_cancel()
                    self._finish_unstarted(job)
                    if active:job.future.set_exception(exc)
        finally:
            # On wait=False our dispatcher must drain pending work before the
            # underlying executor closes admission. Its wrappers stay bounded.
            self._workers.shutdown(wait=False)

    def stats(self):
        limit=self._read_limit()
        with self._condition:
            if limit!=self._last_limit:self._last_limit=limit;self._changed()
            return {'running':self._running,'queued':self._queued,'limit':limit,
                    'owners':{owner:dict(values) for owner,values in self._counts.items()}}

    def shutdown(self,wait=True,*,cancel_futures=False):
        with self._condition:
            self._closing=True
            if cancel_futures:self._cancel_pending=True
            futures=[job.future for job in self._jobs.values() if job.state in ('queued','dispatched')] if cancel_futures else []
            self._changed()
        for future in futures:future.cancel()
        if wait:
            self._dispatcher.join()
            self._workers.shutdown(wait=True)
