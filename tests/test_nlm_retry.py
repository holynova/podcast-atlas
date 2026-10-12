"""Run with nlm's installed Python to test the actual installed SDK seam."""
import sys,unittest
from pathlib import Path
from unittest.mock import MagicMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
try:
    from nlm_extensions import retry_failed_slide
except ModuleNotFoundError:
    retry_failed_slide=None

@unittest.skipIf(retry_failed_slide is None,'Use the installed nlm Python interpreter')
class NlmRetryTests(unittest.TestCase):
    def artifact(self,status=4):
        a=[None]*17;a[0]='same-id';a[2]=8;a[4]=status
        a[16]=[['same prompt','zh-CN',1,3]]
        return a

    def test_retry_preserves_sources_prompt_language_and_options(self):
        client=MagicMock();client.get_artifact.return_value=self.artifact()
        client._extract_artifact_source_ids.return_value=['same-source']
        retry_failed_slide(client,'nb','same-id')
        client.start_artifact_generation.assert_called_once_with(
            'nb','same-id',steering_prompt='same prompt',language='zh-CN',
            source_ids=['same-source'],settings={'slide_format':1,'slide_length':3})
        client.create_slide_deck.assert_not_called()

    def test_completed_or_pending_artifact_is_never_restarted(self):
        for status in [1,2,3]:
            client=MagicMock();client.get_artifact.return_value=self.artifact(status)
            with self.assertRaises(ValueError):retry_failed_slide(client,'nb','same-id')
            client.start_artifact_generation.assert_not_called()

    def test_missing_sources_does_not_widen_to_all_sources(self):
        client=MagicMock();client.get_artifact.return_value=self.artifact()
        client._extract_artifact_source_ids.return_value=[]
        with self.assertRaises(ValueError):retry_failed_slide(client,'nb','same-id')
        client.start_artifact_generation.assert_not_called()

    def test_unexpected_artifact_id_is_not_mutated(self):
        client=MagicMock();client.get_artifact.return_value=self.artifact()
        with self.assertRaises(ValueError):retry_failed_slide(client,'nb','different-id')
        client.start_artifact_generation.assert_not_called()

if __name__=='__main__':unittest.main()
