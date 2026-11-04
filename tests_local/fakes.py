"""Test-only planning adapter; never imported by the running application."""
class FixturePlanner:
    def status(self): return {'available':True,'provider':'test_fixture'}
    def plan(self,r,validate_result,stop_event=None):
        rows=[]
        for entry in r['configs']:
            if entry['pid']+'::'+str(entry['set']) not in r['planning_targets']: continue
            cfg=entry['config'];copy=cfg['copy_refs'][0];count=cfg['placements'][0]['image_count']
            texts=[copy.get('mainTitle','')] if count==1 else [copy.get('short'+str(i),'') for i in range(1,count+1)]
            concept={'name':'测试画面-'+str(entry['set']),'style_id':cfg['visual_direction']['style_id'],
                'prompt':'测试学习者围绕“'+texts[0]+'”翻开对应学习资料，侧面镜头能看见人物与纸面。',
                'slot_actions':['学习者在当前画面呈现“'+text+'”，双手和资料保持清楚接触。' for text in texts],
                'art_direction':{'world':'测试学习空间','scene':'测试资料旁','story':texts[0],'composition':'标题与人物分区','lighting_materials':'柔和自然光'},
                'learner_story':{'protagonist':'原创初中生','pain_point':texts[0],'product_action':copy.get('subtitle') or copy.get('short2') or '呈现已确认文案对应的学习动作','visible_change':'学习者看清当前任务'},
                'screen_text':[]}
            if cfg.get('prompt_context_version')=='per_image_v1':
                concept['common_visual']='测试学习空间以统一的光色和材质呈现。'+r['params'].get('feature_note','')
                concept['slot_actions']=[action+r['params'].get('feature_note','') for action in concept['slot_actions']]
            rows.append({'placement_id':entry['pid'],'set_number':entry['set'],'concept':concept})
        result={'plans':rows,'_provenance':{'provider':'test_fixture'}}
        validate_result(result)
        return result
