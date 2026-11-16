"""Final natural bases survive Logo changes and ordinary single-image rerolls."""
import json
import zipfile
from io import BytesIO

from PIL import Image

from local_app import learning_logo
from tests_local.test_learning_runtime import runtime,settled
from tests_local.test_learning_background_runtime import legacy_source


def test_background_crop_is_not_reapplied_when_exporting_or_refreshing_logo(runtime):
    service,executor,engine=runtime
    yes='learning-youxuepai-logo-1400x340';no='learning-bbg-no-logo-banner-1280x362'
    source=legacy_source(service,[yes,no]);rid=source['id']
    service.repair_backgrounds(rid,'natural-then-logo-layers');done=settled(service,rid)
    assert done['status']=='completed',done.get('error')
    calls=len(executor.jobs)
    natural=next(o for o in service.runs[rid]['outputs'] if o['placement_id']==yes)
    source_sha=natural['raw_sha256']
    black=service.package(rid,logo_asset_id='learning.logo.black')
    white=service.package(rid,logo_asset_id='learning.logo.white-app')
    with zipfile.ZipFile(service.package_file(rid,black['id'])) as b,zipfile.ZipFile(service.package_file(rid,white['id'])) as w:
        bp={row['placement_id']:row['path'] for row in json.loads(b.read('交付清单.json'))['images']}
        wp={row['placement_id']:row['path'] for row in json.loads(w.read('交付清单.json'))['images']}
        assert b.read(bp[no])==w.read(wp[no])
        assert b.read(bp[yes])!=w.read(wp[yes])
        for archive in (b,w):
            for item in json.loads(archive.read('交付清单.json'))['images']:
                with Image.open(BytesIO(archive.read(item['path']))) as im:
                    assert im.size==(item['width'],item['height'])
    cfg=learning_logo.config(engine.settings)
    learning_logo.save_templates(engine.settings,{'revision':cfg['revision'],'templates':[
        {'placement_id':yes,'asset_id':'learning.logo.black','x':.04,'y':.05,'width':.13}]})
    service.refresh_logos(rid,'refresh-natural-logo',[yes]);again=settled(service,rid)
    assert again['status']=='completed' and len(executor.jobs)==calls
    stored=next(o for o in service.runs[rid]['outputs'] if o['placement_id']==yes)
    assert stored['raw_sha256']==source_sha and stored['export_crop_box']==[0,0,1,1]
    assert stored['processing']['method']=='ai_background_expansion_then_exact_export'
    assert stored['processing']['padding_percent']==0
    service.regenerate_output(rid,yes+'::1','reroll-keeps-natural-policy')
    rerolled=settled(service,rid)
    assert rerolled['status']=='completed',rerolled.get('error')
    # The local simulator can render identical new mother pixels. In that
    # case the already-completed natural background must be reused.
    new_jobs=executor.jobs[calls:]
    assert new_jobs[0]['kind']=='single' and len(new_jobs) in (1,2)
    if len(new_jobs)==2:assert new_jobs[1]['kind']=='background_expansion'
    result=next(o for o in rerolled['outputs'] if o['placement_id']==yes)
    assert result['processing']['padding_percent']==0
    assert result['processing']['method']=='ai_background_expansion_then_exact_export'
