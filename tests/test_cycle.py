import datetime as dt,sys,tempfile,unittest,time
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import pipeline as p
import cycle as c

class CycleTests(unittest.TestCase):
    def test_active_local_text_batch_defers_remote_work_without_new_cycle(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as temp,patch.object(p,'ROOT',Path(temp)),patch.object(p,'catalog',return_value=[]),patch.object(c,'read',return_value={'text_batches':{'local':{'status':'running'}}}),patch.object(c,'plan') as plan,patch.object(c,'collect') as collect,patch.object(c,'submit') as submit:
            (Path(temp)/'state').mkdir()
            c.run(SimpleNamespace(slide_limit=5,article_limit=5,wait_minutes=150,plan_only=False,text_only=False))
        plan.assert_not_called();collect.assert_not_called();submit.assert_not_called()

    def test_cycle_boundary_is_five_hours_and_does_not_reset_at_midnight(self):
        anchor=dt.datetime.fromisoformat('2026-10-12T23:00:00+08:00')
        with patch.dict(p.CONFIG,{'cycle_anchor_at':anchor.isoformat(),'cycle_interval_hours':5}):
            self.assertEqual(c.cycle_key(anchor),c.cycle_key(anchor+dt.timedelta(hours=4,minutes=59)))
            self.assertNotEqual(c.cycle_key(anchor),c.cycle_key(anchor+dt.timedelta(hours=5)))

    def test_same_window_reuses_targets_and_attempts(self):
        saved={'key':'slot','slide_ids':['a'],'attempted_slide_ids':['a'],'slide_limit':5}
        self.assertEqual(c.plan({'cycles':{'slot':saved}},[],'slot',5,5),saved)
        self.assertFalse(c.can_submit(saved,'a'))

    def test_shared_budget_prevents_sixth_submission(self):
        state={'slide_ids':['a','b','c','d','e','f'],'attempted_slide_ids':['a','b','c','d','e'],'slide_limit':5}
        self.assertFalse(c.can_submit(state,'f'))

    def test_accounts_share_five_targets_and_keep_series_order(self):
        main={'episodes':{k:{} for k in ['a','b','c','x','y']}}
        es=[{'id':k} for k in ['a','y','b','x','c']]
        with patch.object(c.b,'IDS',['x','y']),patch.object(c.b,'SERIES_IDS',['x','y']),patch.object(c.b,'SUPPLEMENT_IDS',[]):
            self.assertEqual(c.balanced(es,main,5),['a','x','b','y','c'])

    def test_collect_and_submit_share_one_fresh_notebook_check(self):
        ep={'id':'a'};job={'episodes':{'a':{'notebook_id':'nb','source_id':'src'}},'notebooks':{}}
        state={'key':'slot','slide_ids':['a'],'attempted_slide_ids':[],'submitted_slide_ids':[],'slide_limit':5}
        with tempfile.TemporaryDirectory() as d,patch.object(p,'ROOT',Path(d)),patch.object(c,'configure',return_value=job),patch.object(c,'read',return_value={'episodes':{'a':{}}}),patch.object(c.b,'IDS',[]),patch.object(p,'generation_gate'),patch.object(p,'prepare_source'),patch.object(p,'notebook_check_due',return_value=True),patch.object(p,'get_artifacts') as remote,patch.object(p,'start_slides') as start,patch.object(c,'save_cycle'),patch.object(c,'sync'):
            c.submit('default',[ep],state,{('default','nb')},{('default','nb'):([],time.monotonic())},time.monotonic()+10)
        remote.assert_not_called();start.assert_called_once()
        self.assertEqual(state['attempted_slide_ids'],['a'])

    def test_polling_does_not_recheck_old_failed_notebooks(self):
        job={'episodes':{'old':{'status':'pending','notebook_id':'old-nb','slide_status':'failed'}}}
        with patch.object(p,'get_artifacts') as remote:
            self.assertEqual(c.status_cache(job,'account-b',set(),full=False),{})
        remote.assert_not_called()

    def test_source_failure_is_not_retried_inside_the_same_cycle(self):
        cycle={'attempted_source_ids':['a']};job={'episodes':{'a':{}}}
        with patch.object(p,'prepare_source') as source:
            with self.assertRaises(p.GenerationDeferred):c.prepare_cycle_source(job,{'id':'a'},cycle)
        source.assert_not_called()

    def test_daily_failure_cap_does_not_block_other_stages(self):
        ep={'id':'a'};main={'episodes':{'a':{'attempts':{'article':3},'attempts_date':dt.datetime.now(p.TZ).date().isoformat()}}}
        with patch.object(c.b,'IDS',[]):
            self.assertFalse(c.stage_eligible(ep,main,['article']))
            self.assertTrue(c.stage_eligible(ep,main,['slides']))
            main['episodes']['a']['attempts_date']='2026-01-01'
            self.assertTrue(c.stage_eligible(ep,main,['article']))

    def test_reservation_survives_pipeline_snapshot_writes(self):
        job={'episodes':{}};cycle={'key':'slot','attempted_slide_ids':['a']}
        with patch.object(p,'STATE_FILE',c.MAIN),patch.object(c,'save_cycle'):
            c.checkpoint(cycle,job)
        self.assertEqual(job['cycles']['slot']['attempted_slide_ids'],['a'])
        cycle['attempted_slide_ids'].append('b')
        self.assertEqual(job['cycles']['slot']['attempted_slide_ids'],['a'])

    def test_ambiguous_delivery_recovers_a_failed_remote_id_without_resubmitting(self):
        record={'status':'pending','slide_status':'submitting','notebook_id':'nb'}
        job={'episodes':{'a':record}};cycle={'key':'slot','recovered_ids':[]}
        remote=[{'id':'remote-id','status':'failed','custom_instructions':'marker a'}]
        with patch.object(c,'configure',return_value=job),patch.object(c,'status_cache',return_value={'nb':remote}),patch.object(p,'collect_slides',return_value=False) as collect,patch.object(p,'start_slides') as submit,patch.object(c,'sync'),patch.object(c,'save_cycle'):
            c.collect('default',[{'id':'a'}],cycle,set(),{})
        self.assertEqual(record['artifact_id'],'remote-id')
        collect.assert_called_once();submit.assert_not_called()

    def test_finished_failure_does_not_wait_another_150_minutes(self):
        cycle={'slide_ids':['a'],'attempted_slide_ids':['a'],'slide_limit':5}
        main={'episodes':{'a':{'slide_status':'failed'}}}
        with patch.object(c.b,'IDS',[]):
            self.assertFalse(c.can_continue(cycle,main,{'episodes':{}},time.monotonic()+9000))
        main['episodes']['a']['slide_status']='submitting'
        with patch.object(c.b,'IDS',[]):
            self.assertTrue(c.can_continue(cycle,main,{'episodes':{}},time.monotonic()+9000))

    def test_text_and_slides_share_one_run_window(self):
        start=dt.datetime.now(p.TZ);cycle={'started_at':start.isoformat()}
        self.assertEqual(c.remaining_window(cycle,150,start+dt.timedelta(minutes=25)),125*60)
        self.assertEqual(c.remaining_window(cycle,150,start+dt.timedelta(minutes=151)),0)

    def test_unknown_remote_delivery_is_reserved_before_mutation(self):
        ep={'id':'a'};job={'episodes':{'a':{'notebook_id':'nb','source_id':'src'}},'notebooks':{}}
        state={'key':'slot','slide_ids':['a'],'attempted_slide_ids':[],'submitted_slide_ids':[],'slide_limit':5}
        def timeout(*args):
            self.assertEqual(state['attempted_slide_ids'],['a'])
            raise TimeoutError('ambiguous delivery')
        with tempfile.TemporaryDirectory() as d,patch.object(p,'ROOT',Path(d)),patch.object(c,'configure',return_value=job),patch.object(c,'read',return_value={'episodes':{'a':{}}}),patch.object(c.b,'IDS',[]),patch.object(p,'generation_gate'),patch.object(p,'prepare_source'),patch.object(p,'notebook_check_due',return_value=True),patch.object(p,'get_artifacts',return_value=[]),patch.object(p,'start_slides',side_effect=timeout),patch.object(p,'mark_error'),patch.object(c,'save_cycle'),patch.object(c,'sync'):
            c.submit('default',[ep],state,set(),{},time.monotonic()+10)
        self.assertFalse(c.can_submit(state,'a'))
