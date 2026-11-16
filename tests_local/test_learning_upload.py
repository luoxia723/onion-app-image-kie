"""The former upload entry is closed; owned historical sources remain readable."""
import hashlib
from io import BytesIO
from pathlib import Path
import pytest
from PIL import Image
from local_app.config import UserError
from local_app.planning import make_round,validate
from local_app import learning_source,learning_pipeline
from tests_local.test_workbench import engine
from tests_local.test_learning_workflow import params,ROOT,SMALL,WIDE,WIDE_SMALL
from tests_local.test_reference_points import api_call,settings
from tests_local.learning_history import frozen_placements,install_history


def source(folder):
    folder.mkdir(parents=True,exist_ok=True)
    data=BytesIO();Image.new('RGB',(984,438),'#556677').save(data,'PNG');data=data.getvalue();sha=hashlib.sha256(data).hexdigest()
    path=folder/(sha+'.png');path.write_bytes(data)
    return dict(id=sha,sha256=sha,path=str(path),name='原广告.png',width=984,height=438)


def uploaded_params(folder,*pids):return {**params(*(pids or (ROOT,SMALL,WIDE,WIDE_SMALL))),'learning_mode':'upload','learning_source':source(folder)}


def test_new_upload_task_is_rejected_before_planning(tmp_path):
    pr=uploaded_params(tmp_path/'uploads')
    with pytest.raises(UserError,match='先生成基准图'):validate(pr,tmp_path)
    with pytest.raises(UserError,match='先生成基准图'):learning_pipeline.preview(pr)


def test_upload_engine_cannot_start_the_retired_path(engine,monkeypatch):
    import local_app.engine as module
    def forbidden(*args,**kwargs):raise AssertionError('Retired upload must not plan or start a worker')
    monkeypatch.setattr(engine.planner,'plan',forbidden)
    monkeypatch.setattr(module.subprocess,'Popen',forbidden)
    pr=uploaded_params(engine.settings.state_dir/'uploads')
    with pytest.raises(UserError):engine.create(pr,'retired-upload-entry')
    assert not engine.tasks


@pytest.mark.history
def test_historical_registered_source_and_frozen_copy_remain_intact(settings):
    original=source(settings.state_dir/'uploads');before=Path(original['path']).read_bytes()
    pr={'learning_mode':'upload','learning_source':original}
    learning_source.registered(pr,settings)
    frozen=learning_source.freeze(pr,settings.output/'historical-cache')
    assert Path(frozen['learning_source']['path']).is_file()
    assert frozen['learning_source']['path']!=original['path']
    assert learning_source.check(frozen['learning_source']).read_bytes()==before
    assert Path(original['path']).read_bytes()==before
    assert learning_source.uploaded(frozen) is True


@pytest.mark.history
def test_historical_registration_rejects_arbitrary_local_file(settings,tmp_path):
    pr=uploaded_params(tmp_path/'outside')
    with pytest.raises(UserError,match='登记'):learning_source.registered(pr,settings)


@pytest.mark.history
def test_historical_sample_registration_keeps_its_original_layout_identity(settings):
    from local_app.config import ROOT as PROJECT_ROOT
    from local_app.planning import BY_ID
    path=PROJECT_ROOT/BY_ID[ROOT]['sample_reference']['path'];data=path.read_bytes();sha=hashlib.sha256(data).hexdigest()
    uploads=settings.state_dir/'uploads';uploads.mkdir(exist_ok=True);(uploads/(sha+'.png')).write_bytes(data)
    pr={'learning_mode':'upload','learning_source':{'id':sha}}
    learning_source.registered(pr,settings)
    assert pr['learning_source']['known_sample'] and pr['learning_source']['layout_id']==ROOT


@pytest.mark.history
def test_legacy_make_round_retains_its_frozen_upload_reference(tmp_path):
    # Read/restore compatibility only: current submission does not call this constructor.
    pr=uploaded_params(tmp_path/'uploads',ROOT)
    r=make_round(pr,'historical-upload',tmp_path/'cache',1,True,defer_planning=True,
                 placements_override=frozen_placements(pr['pids']))
    assert r['planning_status']=='done' and not r['planning_targets']
    assert r['params']['learning_source']['id']==pr['learning_source']['id']
    assert any(ref.get('purpose')=='uploaded_master' for ref in r['slots'][0]['refs'])


@pytest.mark.parametrize('path',['/api/learning-source/copy','/api/learning-source/plan'])
def test_retired_source_api_never_calls_planning_provider(settings,monkeypatch,path):
    from local_app.scene_planner import ApiScenePlanner
    def forbidden(*args):raise AssertionError('Retired route must not call provider')
    monkeypatch.setattr(ApiScenePlanner,'_request',forbidden)
    with pytest.raises(UserError):api_call(settings,path,{'id':source(settings.state_dir/'uploads')['id']})


@pytest.mark.history
def test_historical_upload_backup_restores_readable_frozen_source(engine,tmp_path):
    from local_app.config import Settings
    from local_app.engine import Engine
    from tests_local.fakes import FixturePlanner
    pr=uploaded_params(engine.settings.state_dir/'uploads',ROOT,SMALL)
    task=install_history(engine,pr);tid=task['id'];backup=engine.create_backup()
    folder=tmp_path/'other';folder.mkdir()
    other_settings=Settings(folder/'state',folder/'test.env');other_settings.update({'output_dir':str(folder),'simulation':True})
    other=Engine(other_settings,start=False,planner=FixturePlanner())
    try:
        preview=other.restore_preview(backup['path']);other.restore_backup(backup['path'],preview['token'])
        restored=other.task(tid)['rounds'][0]['params']
        path=learning_source.check(restored['learning_source'])
        assert (folder/'.restored') in path.parents
        assert path.read_bytes()==Path(task['rounds'][0]['params']['learning_source']['path']).read_bytes()
        # Restoration is readable history, not permission to reopen the retired entry.
        with pytest.raises(UserError):other.create(restored,'retired-restored-upload')
    finally:other.close()
