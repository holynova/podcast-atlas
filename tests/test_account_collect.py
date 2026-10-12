import contextlib,datetime as dt,io,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import pipeline as p
import supplement_account as b

class AccountCollectTests(unittest.TestCase):
    def test_collect_only_never_prepares_or_submits_another_episode(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'state/accounts').mkdir(parents=True)
            main=root/'state/progress.json'
            main.write_text(json.dumps({'episodes':{'e':{'title':'episode','status':'pending'}},'batches':{}}))
            submitted=(dt.datetime.now(p.TZ)-dt.timedelta(minutes=21)).isoformat()
            (root/'state/accounts/account-b.json').write_text(json.dumps({'notebooks':{'topic':'nb'},'episodes':{'e':{'title':'episode','status':'pending','source_id':'src','notebook_id':'nb','artifact_id':'a','slide_status':'queued','slide_submitted_at':submitted}}}))
            with patch.object(p,'ROOT',root),patch.object(p,'STATE_FILE',main),patch.object(b,'PRIMARY',main),patch.object(b,'IDS',['e']),patch.object(b,'SERIES_IDS',['e']),patch.object(b,'SUPPLEMENT_IDS',[]),patch.dict(p.CONFIG,{'notebooklm_profile':'default'}),patch.object(p,'catalog',return_value=[{'id':'e','title':'episode'}]),patch.object(p,'get_artifacts',return_value=[{'id':'a','status':'queued'}]) as status,patch.object(p,'collect_slides',return_value=False),patch.object(p,'prepare_source') as source,patch.object(p,'start_slides') as generate,contextlib.redirect_stdout(io.StringIO()):
                b.run('account-b',0,collect_only=True)
            status.assert_called_once_with('nb');source.assert_not_called();generate.assert_not_called()
            self.assertEqual(json.loads(main.read_text())['episodes']['e']['status'],'pending')
