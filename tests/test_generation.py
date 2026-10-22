import datetime as dt
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import pipeline as p

class GenerationTests(unittest.TestCase):
    def test_shared_request_pacing_waits_only_remaining_interval(self):
        with patch.object(p,'_LAST_REQUEST',100),patch.object(p.time,'monotonic',side_effect=[106,115]),patch.object(p,'paced_sleep') as sleep:
            p.pace_request()
            sleep.assert_called_once_with(9)
            self.assertEqual(p._LAST_REQUEST,115)

    def test_account_is_pinned_without_switching_saved_default(self):
        with patch.dict(p.os.environ,{'NLM_PROFILE':'account-b','HTTPS_PROXY':'http://localhost:7897'}):
            self.assertEqual(p.network_env()['NLM_PROFILE'],p.CONFIG['notebooklm_profile'])

    def test_pending_job_prevents_new_generation(self):
        # Concurrency allows up to 10 in-flight tasks; 10 or more blocks
        p.generation_gate({'episodes':{f'ep_{i}':{'slide_status':'queued'} for i in range(9)}})
        with self.assertRaises(p.GenerationDeferred):
            p.generation_gate({'episodes':{f'ep_{i}':{'slide_status':'queued'} for i in range(10)}})

    def test_diagnostic_task_blocks_other_submission(self):
        with self.assertRaises(p.GenerationDeferred):
            p.generation_gate({'episodes':{},'diagnostic_inflight':{'status':'queued'}})

    def test_manual_retry_is_not_duplicated_before_reconciliation(self):
        past=(dt.datetime.now(p.TZ)-dt.timedelta(minutes=1)).isoformat()
        with self.assertRaises(p.GenerationDeferred):
            p.generation_gate({'episodes':{},'manual_retry_watch':{'check_not_before':past}})

    def test_manual_retry_notebook_wait_is_honored(self):
        future=(dt.datetime.now(p.TZ)+dt.timedelta(minutes=20)).isoformat()
        s={'episodes':{},'manual_retry_watch':{'notebook_id':'nb','check_not_before':future}}
        self.assertFalse(p.notebook_check_due(s,'nb'))
        self.assertTrue(p.notebook_check_due(s,'other'))

    def test_other_account_does_not_redelegate_an_episode_completed_manually(self):
        import json
        import supplement_account as b
        main={'episodes':{'e':{'status':'complete','profile':'default','artifact_id':'manual-success'}},'batches':{}}
        with patch.object(b.PRIMARY.__class__,'read_text',return_value=json.dumps(main)),patch.object(p,'write_json') as write:
            b.sync_primary({'episodes':{'e':{'status':'superseded','artifact_id':'old-failure'}}},'account-b')
        merged=write.call_args.args[1]['episodes']['e']
        self.assertEqual(merged['artifact_id'],'manual-success')
        self.assertNotIn('delegated_profile',merged)
        self.assertEqual(merged['alternate_runs']['account-b']['artifact_id'],'old-failure')

    def test_second_account_queue_is_already_assigned_for_daily_selection(self):
        with patch.dict(p.CONFIG,{'account_b_series_ids':['apple','manga']}):
            assigned=p.assigned_episode_ids({'batches':{'day':{'ids':['internet']}}})
        self.assertEqual(assigned,{'internet','apple','manga'})

    def test_short_cooldown_does_not_end_a_run_with_enough_time(self):
        until=(dt.datetime.now(p.TZ)+dt.timedelta(minutes=10)).isoformat()
        self.assertFalse(p.cooldown_outlasts_budget({'generation_cooldown_until':until},p.time.monotonic()+900))

    def test_long_cooldown_stops_without_waiting_outside_run_budget(self):
        until=(dt.datetime.now(p.TZ)+dt.timedelta(hours=5)).isoformat()
        self.assertTrue(p.cooldown_outlasts_budget({'generation_cooldown_until':until},p.time.monotonic()+900))

    def test_diagnostic_deck_is_not_reused_as_a_production_result(self):
        s={'episodes':{'e':{'notebook_id':'nb','source_id':'src','slide_status':'retry_pending'}},'diagnostic_artifact_ids':['diag']}
        with patch.object(p,'write_json'),patch.object(p,'cli',return_value={'artifact_id':'production'}) as cli:
            p.start_slides(s,{'id':'e','title':'test'},[{'id':'diag','status':'completed','title':'e'}])
        self.assertEqual(s['episodes']['e']['artifact_id'],'production')
        cli.assert_called_once()

    def test_diagnostic_deck_is_not_downloaded_as_a_production_result(self):
        s={'episodes':{'e':{'notebook_id':'nb','source_id':'src'}},'diagnostic_artifact_ids':['diag']}
        with patch.object(p,'cli') as cli:
            self.assertFalse(p.collect_slides(s,{'id':'e'},[{'id':'diag','status':'completed','title':'e'}]))
        cli.assert_not_called()

    def test_diagnostic_generation_wait_prevents_early_notebook_poll(self):
        s={'episodes':{},'diagnostic_inflight':{'notebook_id':'nb','submitted_at':p.now()}}
        self.assertFalse(p.notebook_check_due(s,'nb'))

    def test_unknown_failure_backoff_counts_time_already_waited(self):
        submitted=(dt.datetime.now(p.TZ)-dt.timedelta(minutes=20)).isoformat()
        s={'episodes':{'e':{'notebook_id':'nb','artifact_id':'broken','slide_status':'queued','slide_submitted_at':submitted}}}
        with patch.object(p,'write_json'):
            with self.assertRaises(p.GenerationFailed):
                p.collect_slides(s,{'id':'e'},[{'id':'broken','status':'failed','title':'e'}])
        remaining=(dt.datetime.fromisoformat(s['episodes']['e']['next_slide_attempt_at'])-dt.datetime.now(p.TZ)).total_seconds()
        expected=p.CONFIG.get('single_episode_retry_interval_seconds',60)
        self.assertGreater(remaining,expected-2);self.assertLess(remaining,expected+2)

    def test_new_deck_is_not_polled_or_failed_before_twenty_minutes(self):
        r={'notebook_id':'nb','artifact_id':'early','slide_status':'queued','slide_submitted_at':p.now()}
        state={'episodes':{'e':r}}
        self.assertFalse(p.notebook_check_due(state,'nb'))
        with patch.object(p,'get_artifacts') as query,patch.object(p,'pause_generation') as pause:
            self.assertFalse(p.collect_slides(state,{'id':'e'},[{'id':'early','status':'failed','title':'e'}]))
            query.assert_not_called();pause.assert_not_called()
        self.assertEqual(r['slide_status'],'queued')

    def test_deck_can_be_checked_after_twenty_minutes(self):
        submitted=(dt.datetime.now(p.TZ)-dt.timedelta(minutes=21)).isoformat()
        self.assertTrue(p.notebook_check_due({'episodes':{'e':{'notebook_id':'nb','slide_status':'queued','slide_submitted_at':submitted}}},'nb'))

    def test_interval_survives_runner_restart(self):
        with self.assertRaises(p.GenerationDeferred):
            p.generation_gate({'episodes':{},'last_slide_submission_at':p.now()})

    def test_cooldown_blocks_and_expired_cooldown_allows(self):
        clock=dt.datetime.now(p.TZ)
        with self.assertRaises(p.GenerationDeferred):
            p.generation_gate({'episodes':{},'generation_cooldown_until':(clock+dt.timedelta(hours=5)).isoformat()})
        p.generation_gate({'episodes':{},'generation_cooldown_until':(clock-dt.timedelta(seconds=1)).isoformat()})

    def test_only_failed_artifacts_replaced(self):
        state={'episodes':{'e':{'notebook_id':'nb','source_id':'src','slide_status':'retry_pending'}}}
        artifacts=[{'id':'old1','status':'failed','title':'e'},{'id':'old2','status':'failed','title':'e'}]
        with patch.object(p,'write_json'),patch.object(p,'cli',return_value={'artifact_id':'new'}) as cli:
            p.start_slides(state,{'id':'e','title':'test'},artifacts)
            self.assertEqual(state['episodes']['e']['artifact_id'],'new')
            self.assertEqual(set(state['episodes']['e']['failed_artifact_ids']),{'old1','old2'})
            self.assertEqual(cli.call_count,1)
            self.assertIn('src',cli.call_args.args)

    def test_existing_result_reused_even_during_cooldown(self):
        state={'episodes':{'e':{'notebook_id':'nb','source_id':'src','slide_status':'retry_pending'}},'generation_cooldown_until':(dt.datetime.now(p.TZ)+dt.timedelta(hours=5)).isoformat()}
        with patch.object(p,'write_json'),patch.object(p,'cli') as cli:
            p.start_slides(state,{'id':'e','title':'test'},[{'id':'ready','status':'completed','title':'e'}])
            self.assertEqual(state['episodes']['e']['artifact_id'],'ready');cli.assert_not_called()

    def test_explicit_rate_limit_sets_global_cooldown(self):
        state={'episodes':{'e':{'notebook_id':'nb','source_id':'src','slide_status':'retry_pending'}}}
        with patch.object(p,'write_json'),patch.object(p,'cli',side_effect=RuntimeError('RESOURCE_EXHAUSTED')):
            with self.assertRaises(RuntimeError):p.start_slides(state,{'id':'e','title':'test'},[])
        self.assertGreater(dt.datetime.fromisoformat(state['generation_cooldown_until']),dt.datetime.now(p.TZ)+dt.timedelta(hours=4))

    def test_manual_retry_can_recover_an_archived_failed_id(self):
        state={'episodes':{'e':{'notebook_id':'nb','source_id':'src','slide_status':'retry_pending','failed_artifact_ids':['recovered'],'attempts':{'slides':3}}}}
        with patch.object(p,'write_json'),patch.object(p,'cli') as cli:
            p.start_slides(state,{'id':'e','title':'test'},[{'id':'recovered','status':'completed','title':'e'}])
        self.assertEqual(state['episodes']['e']['artifact_id'],'recovered')
        self.assertEqual(state['episodes']['e']['attempts']['slides'],3)
        cli.assert_not_called()

    def test_remote_failure_uses_generation_stage_not_download(self):
        state={'episodes':{'quota-test':{'notebook_id':'nb','source_id':'src','artifact_id':'broken','slide_status':'queued'}}}
        artifacts=[{'id':'broken','status':'failed','title':'quota-test'}]
        with patch.object(p,'write_json'):
            with self.assertRaises(p.GenerationFailed) as error:
                p.collect_slides(state,{'id':'quota-test'},artifacts)
            p.mark_error(state,'quota-test','slides',error.exception)
        self.assertEqual(state['episodes']['quota-test']['attempts'],{'slides':1})
        self.assertIn('next_slide_attempt_at',state['episodes']['quota-test'])
        self.assertNotIn('generation_cooldown_until',state)

    def test_archived_failure_does_not_restart_cooldown(self):
        r={'notebook_id':'nb','slide_status':'retry_pending','failed_artifact_ids':['old']}
        state={'episodes':{'e':r},'generation_cooldown_until':'2026-10-12T01:18:58+08:00'}
        with patch.object(p,'write_json'),patch.object(p,'pause_generation') as pause:
            self.assertFalse(p.collect_slides(state,{'id':'e'},[{'id':'old','status':'failed','title':'e'}]))
            pause.assert_not_called()
        self.assertEqual(r['slide_status'],'retry_pending')
        self.assertNotIn('artifact_id',r)

    def test_ambiguous_submission_not_repeated(self):
        state={'episodes':{'e':{'notebook_id':'nb','source_id':'src','slide_status':'submitting'}}}
        with patch.object(p,'cli') as cli:
            with self.assertRaises(RuntimeError):p.start_slides(state,{'id':'e','title':'test'},[])
            cli.assert_not_called()

if __name__=='__main__':unittest.main()
