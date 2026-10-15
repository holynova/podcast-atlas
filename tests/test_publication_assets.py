import sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from publication_assets import verified_unchanged_asset

class PublicationAssetTests(unittest.TestCase):
    def test_reuse_requires_verified_episode_and_identical_committed_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);file=root/'asset.pdf';file.write_bytes(b'new')
            previous={'status':'verified','source_sha':'abc','verified_episode_ids':['e']}
            with patch('publication_assets.subprocess.run',return_value=SimpleNamespace(returncode=0,stdout=b'new')) as git:
                self.assertTrue(verified_unchanged_asset(root,file,'e',previous))
                git.assert_called_once()
                self.assertFalse(verified_unchanged_asset(root,file,'other',previous))
                self.assertFalse(verified_unchanged_asset(root,file,'e',{**previous,'status':'deployed_unverified'}))
            with patch('publication_assets.subprocess.run',return_value=SimpleNamespace(returncode=0,stdout=b'old')):
                self.assertFalse(verified_unchanged_asset(root,file,'e',previous))
            with patch('publication_assets.subprocess.run',return_value=SimpleNamespace(returncode=1,stdout=b'')):
                self.assertFalse(verified_unchanged_asset(root,file,'e',previous))
