import io, json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from https_batch import HttpsBatch

class BatchTests(unittest.TestCase):
    def run_batch(self, fail=False):
        with tempfile.TemporaryDirectory() as work:
            batch = HttpsBatch(work,{})
            def fake_process(command, **kwargs):
                config = Path(command[-1]).read_text()
                self.assertIn('--parallel-max',command)
                self.assertNotIn('insecure',config)
                self.assertNotIn('--insecure',command)
                urls = [json.loads(line.split(' = ',1)[1]) for line in config.splitlines() if line.startswith('url = ')]
                outputs = [json.loads(line.split(' = ',1)[1]) for line in config.splitlines() if line.startswith('output = ')]
                self.assertEqual(len(urls),2)
                for target in outputs: Path(target).write_bytes(b'actual body')
                class Process:
                    stdout = io.StringIO(''.join(json.dumps({'url_effective':url,'http_code':500 if fail else 200,'exitcode':22 if fail else 0,'content_type':'text/css; charset=utf-8'})+'\n' for url in urls))
                    def wait(self): return 22 if fail else 0
                return Process()
            with patch('https_batch.subprocess.Popen',fake_process):
                if fail:
                    with self.assertRaises(RuntimeError):batch.fetch(['https://example.test/a','https://example.test/b'])
                else:
                    batch.fetch(['https://example.test/a','https://example.test/b','https://example.test/a'])
                    self.assertEqual(batch.get('https://example.test/a'),(b'actual body','text/css'))
            batch.directory.cleanup()

    def test_complete_responses_are_deduplicated_and_keep_mime(self):self.run_batch()
    def test_any_failed_transfer_prevents_verification(self):self.run_batch(fail=True)
    def test_plain_http_is_rejected(self):
        with tempfile.TemporaryDirectory() as work:
            batch=HttpsBatch(work,{})
            with self.assertRaises(ValueError):batch.fetch(['http://example.test/'])
            batch.directory.cleanup()
