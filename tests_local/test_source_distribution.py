"""Distribution checks exercise actual Git selection and generated archives."""
import importlib.util
from pathlib import Path
import subprocess
import tarfile
import zipfile
import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('source_bundle',ROOT/'scripts/build_workbench_bundle.py')
bundle=importlib.util.module_from_spec(spec);spec.loader.exec_module(bundle)

@pytest.fixture
def source_repo(tmp_path):
    root=tmp_path/'中文 Source Project';root.mkdir()
    subprocess.run(['git','init','-q',str(root)],check=True)
    (root/'run.py').write_text('print("source")\n')
    (root/'.env.example').write_text('KIE_API_KEY=""\nONION_PLANNING_API_KEY=""\n')
    subprocess.run(['git','add','run.py','.env.example'],cwd=root,check=True)
    return root

def test_source_archives_keep_runtime_assets_and_exclude_local_data(source_repo,tmp_path):
    root=source_repo
    private=['.env','.env.backup','.onion-local/index.sqlite3','uploads/reference.png',
             'backups/backup.json','output.sqlite3-wal','result.zip','.cache/task/raw.png',
             '工作区/产物/final.png','assets/logos/review/draft.png']
    for name in private:
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('private local content')
    asset=root/'assets/logos/registered.png';asset.parent.mkdir(parents=True,exist_ok=True);asset.write_bytes(b'registered-asset')
    zipped,tarred,count=bundle.build(tmp_path/'artifacts',root)
    expected={'onion-app-image-kie/run.py','onion-app-image-kie/.env.example','onion-app-image-kie/assets/logos/registered.png'}
    with zipfile.ZipFile(zipped) as archive:
        assert set(archive.namelist())==expected
        assert archive.read('onion-app-image-kie/assets/logos/registered.png')==b'registered-asset'
    with tarfile.open(tarred) as archive:assert set(archive.getnames())==expected
    assert count==3

def test_tracked_database_blocks_distribution(source_repo,tmp_path):
    (source_repo/'index.sqlite3').write_bytes(b'local-database')
    subprocess.run(['git','add','index.sqlite3'],cwd=source_repo,check=True)
    with pytest.raises(ValueError,match='Git索引'):bundle.build(tmp_path/'artifacts',source_repo)
    assert not (tmp_path/'artifacts').exists()

def test_local_key_in_source_blocks_export_and_keeps_previous_archive(source_repo,tmp_path):
    secret='local-test-key-for-distribution-only'
    (source_repo/'.env').write_text('KIE_API_KEY="'+secret+'"\n')
    (source_repo/'run.py').write_text(secret)
    destination=tmp_path/'artifacts';destination.mkdir();old=destination/'洋葱广告图工作台-本机版.zip';old.write_bytes(b'previous archive')
    with pytest.raises(ValueError,match='本机 Key'):bundle.build(destination,source_repo)
    assert old.read_bytes()==b'previous archive'

def test_example_credentials_must_be_blank(source_repo):
    (source_repo/'.env.example').write_text('ONION_PLANNING_API_KEY="example-key"\n')
    with pytest.raises(ValueError,match='必须留空'):bundle.check_sources(source_repo)
