import datetime as dt
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import pipeline as p

class GenerationTests(unittest.TestCase):
    def test_account_is_pinned_without_switching_saved_default(self):
        with patch.dict(p.os.environ,{'NLM_PROFILE':'account-b','HTTPS_PROXY':'http://localhost:7897'}):
            self.assertEqual(p.network_env()['NLM_PROFILE'],p.CONFIG['notebooklm_profile'])

    def test_pending_job_prevents_new_generation(self):
        with self.assertRaises(p.GenerationDeferred):
            p.generation_gate({'episodes':{'other':{'slide_status':'queued'}}})

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
        self.assertIn('generation_cooldown_until',state)

    def test_ambiguous_submission_not_repeated(self):
        state={'episodes':{'e':{'notebook_id':'nb','source_id':'src','slide_status':'submitting'}}}
        with patch.object(p,'cli') as cli:
            with self.assertRaises(RuntimeError):p.start_slides(state,{'id':'e','title':'test'},[])
            cli.assert_not_called()

if __name__=='__main__':unittest.main()
