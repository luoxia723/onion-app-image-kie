from concurrent.futures import CancelledError
import threading

import pytest

from local_app.config import UserError
from local_app.work_dispatch import FairImagePool


def test_owner_fifo_round_robin_while_one_worker_is_busy():
    release=threading.Event();started=threading.Event();order=[]
    pool=FairImagePool(max_workers=1)
    try:
        head=pool.submit_for('block',lambda:(started.set(),release.wait(5)))
        assert started.wait(3)
        first=[pool.submit_for('A',lambda value=value:order.append(value),) for value in ('A1','A2','A3')]
        second=[pool.submit_for('B',lambda value=value:order.append(value),) for value in ('B1','B2','B3')]
        assert all(not f.running() and not f.done() for f in first+second)
        release.set();head.result(3)
        for future in first+second:future.result(3)
        assert order==['A1','B1','A2','B2','A3','B3']
        assert pool.stats()=={'running':0,'queued':0,'limit':1,'owners':{}}
    finally:release.set();pool.shutdown(cancel_futures=True)


def test_global_worker_limit_and_stats_include_all_owners():
    release=threading.Event();started=[threading.Event() for _ in range(3)]
    pool=FairImagePool(max_workers=3)
    def work(index):started[index].set();release.wait(5);return index
    try:
        running=[pool.submit_for('A' if i<2 else 'B',work,i) for i in range(3)]
        assert all(event.wait(3) for event in started)
        waiting=pool.submit_for('C',lambda:4)
        assert waiting.running() is False
        stats=pool.stats()
        assert (stats['running'],stats['queued'],stats['limit'])==(3,1,3)
        assert stats['owners']=={'A':{'running':2,'queued':0},'B':{'running':1,'queued':0},'C':{'running':0,'queued':1}}
        release.set()
        assert [f.result(3) for f in running]==[0,1,2] and waiting.result(3)==4
    finally:release.set();pool.shutdown(cancel_futures=True)


def test_dynamic_limit_keeps_existing_jobs_but_waits_before_admitting_more():
    limit=[1];started=[threading.Event() for _ in range(3)];release=[threading.Event() for _ in range(3)]
    pool=FairImagePool(max_workers=3,limit_provider=lambda:limit[0])
    def work(index):started[index].set();release[index].wait(5);return index
    try:
        futures=[pool.submit_for(str(i),work,i) for i in range(3)]
        assert started[0].wait(3)
        assert pool.stats()['running']==1 and not futures[1].running() and not futures[2].running()
        limit[0]=3;assert pool.stats()['limit']==3
        assert started[1].wait(3) and started[2].wait(3)
        limit[0]=1;assert pool.stats()['limit']==1
        queued=pool.submit_for('later',lambda:'later')
        release[0].set();assert futures[0].result(3)==0
        assert not queued.running() and pool.stats()['running']==2
        release[1].set();assert futures[1].result(3)==1
        assert not queued.running() and pool.stats()['running']==1
        release[2].set();assert futures[2].result(3)==2
        assert queued.result(3)=='later'
    finally:
        for event in release:event.set()
        pool.shutdown(cancel_futures=True)


def test_cancelling_queued_work_frees_capacity_and_never_calls_it():
    started=threading.Event();release=threading.Event();called=[]
    pool=FairImagePool(max_workers=1,max_pending=1)
    try:
        running=pool.submit_for('running',lambda:(started.set(),release.wait(5)))
        assert started.wait(3)
        cancelled=pool.submit_for('pending',lambda:called.append('cancelled'))
        with pytest.raises(UserError) as error:pool.submit_for('overflow',lambda:None)
        assert error.value.status==429
        assert cancelled.cancel() and pool.stats()['queued']==0
        replacement=pool.submit_for('replacement',lambda:'replacement')
        release.set();running.result(3)
        assert replacement.result(3)=='replacement' and called==[]
        with pytest.raises(CancelledError):cancelled.result()
    finally:release.set();pool.shutdown(cancel_futures=True)


def test_shutdown_cancel_futures_keeps_running_job_and_callbacks_run_without_pool_lock():
    started=threading.Event();release=threading.Event();observed=[]
    pool=FairImagePool(max_workers=1)
    try:
        running=pool.submit(lambda:(started.set(),release.wait(5),'finished')[-1])
        assert started.wait(3)
        pending=pool.submit(lambda:pytest.fail('cancelled shutdown job executed'))
        def callback(future):
            inspected=threading.Event()
            thread=threading.Thread(target=lambda:(pool.stats(),inspected.set()))
            thread.start();observed.append(inspected.wait(3));thread.join(3)
        pending.add_done_callback(callback)
        pool.shutdown(wait=False,cancel_futures=True)
        assert pending.cancelled() and observed==[True]
        assert running.running() and not running.cancelled()
        with pytest.raises(RuntimeError,match='shutdown'):pool.submit(lambda:None)
        release.set();assert running.result(3)=='finished'
    finally:release.set();pool.shutdown(cancel_futures=True)


def test_shutdown_without_cancel_drains_queued_work_and_refuses_new_work():
    started=threading.Event();release=threading.Event();order=[]
    pool=FairImagePool(max_workers=1)
    try:
        head=pool.submit(lambda:(started.set(),release.wait(5)))
        assert started.wait(3)
        tail=pool.submit_for('tail',lambda:order.append('tail'))
        pool.shutdown(wait=False)
        with pytest.raises(RuntimeError):pool.submit_for('late',lambda:None)
        assert not tail.running()
        release.set();head.result(3);tail.result(3)
        assert order==['tail']
    finally:release.set();pool.shutdown()


def test_user_functions_and_completion_callbacks_can_read_pool_and_enqueue_more():
    pool=FairImagePool(max_workers=1);observed=[];callback_done=threading.Event();next_job=[]
    def work():
        inspected=threading.Event()
        thread=threading.Thread(target=lambda:(pool.stats(),inspected.set()))
        thread.start();result=inspected.wait(3);thread.join(3)
        return result
    def callback(future):
        observed.append(pool.stats()['running'])
        next_job.append(pool.submit_for('followup',lambda:'followup'))
        callback_done.set()
    try:
        first=pool.submit(work);first.add_done_callback(callback)
        assert first.result(3) is True and callback_done.wait(3)
        assert next_job[0].result(3)=='followup' and observed==[0]
        failure=pool.submit(lambda:(_ for _ in ()).throw(ValueError('worker failure')))
        with pytest.raises(ValueError,match='worker failure'):failure.result(3)
        assert pool.submit(lambda:'healthy').result(3)=='healthy'
    finally:pool.shutdown(cancel_futures=True)


def test_default_owner_inference_and_zero_limit_pause():
    limit=[0];pool=FairImagePool(max_workers=2,limit_provider=lambda:limit[0])
    try:
        first=pool.submit(lambda task:task['id'],{'id':'task-one'})
        second=pool.submit(lambda:'generic')
        assert not first.running() and not second.running()
        assert pool.stats()['owners']=={'generic:task-one':{'running':0,'queued':1},'generic':{'running':0,'queued':1}}
        limit[0]=2;assert pool.stats()['limit']==2
        assert first.result(3)=='task-one' and second.result(3)=='generic'
    finally:pool.shutdown(cancel_futures=True)


def test_limit_provider_does_not_hold_pool_condition_while_waiting_for_engine_lock():
    engine_lock=threading.Lock();entered=threading.Event();submitted=threading.Event();futures=[]
    engine_lock.acquire()
    def limit():
        entered.set()
        with engine_lock:return 1
    pool=FairImagePool(max_workers=1,limit_provider=limit)
    thread=None
    try:
        assert entered.wait(3)
        thread=threading.Thread(target=lambda:(futures.append(pool.submit(lambda:'done')),submitted.set()))
        thread.start()
        assert submitted.wait(3),'submit blocked behind limit_provider while caller owns Engine lock'
    finally:
        engine_lock.release()
        if thread:thread.join(3)
        pool.shutdown(cancel_futures=True)
    assert futures and (futures[0].cancelled() or futures[0].result(3)=='done')
