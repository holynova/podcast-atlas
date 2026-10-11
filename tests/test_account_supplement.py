import json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import supplement_account as a

class AccountSupplementTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.file=Path(self.tmp.name)/'main.json'
        self.original={'episodes':{'e':{'notebook_id':'default-nb','source_id':'default-src','artifact_id':'failed','status':'blocked','attempts':{'slides':3},'errors':[{'message':'old failure'}]},'other':{'status':'complete','artifact_id':'existing'}},'batches':{'today':{'ids':['e','other']}},'generation_cooldown_until':'2030-01-01T00:00:00+08:00'}
        self.file.write_text(json.dumps(self.original));self.patcher=patch.object(a,'PRIMARY',self.file);self.patcher.start()
    def tearDown(self):self.patcher.stop();self.tmp.cleanup()
    def test_pending_job_does_not_replace_original_remote_ids(self):
        a.sync_primary({'episodes':{'e':{'status':'pending','notebook_id':'b-nb'}}},'account-b');s=json.loads(self.file.read_text())
        self.assertEqual(s['episodes']['e']['notebook_id'],'default-nb');self.assertEqual(s['episodes']['e']['delegated_profile'],'account-b');self.assertEqual(s['episodes']['other'],self.original['episodes']['other'])
    def test_completed_job_preserves_first_account_failures_and_cooldown(self):
        a.sync_primary({'episodes':{'e':{'status':'complete','notebook_id':'b-nb','source_id':'b-src','artifact_id':'b-ready','slide_status':'downloaded'}}},'account-b');s=json.loads(self.file.read_text());r=s['episodes']['e']
        self.assertEqual(r['previous_account_context']['artifact_id'],'failed');self.assertEqual(r['attempts'],{'slides':3});self.assertEqual(s['generation_cooldown_until'],self.original['generation_cooldown_until']);self.assertEqual(r['publication_status'],'pending');self.assertEqual(s['batches']['today']['complete'],2)
    def test_repeated_collection_preserves_verified_publication(self):
        job={'episodes':{'e':{'status':'complete','artifact_id':'b-ready'}}};a.sync_primary(job,'account-b');s=json.loads(self.file.read_text());s['episodes']['e']['publication_status']='verified';self.file.write_text(json.dumps(s));a.sync_primary(job,'account-b');self.assertEqual(json.loads(self.file.read_text())['episodes']['e']['publication_status'],'verified')
