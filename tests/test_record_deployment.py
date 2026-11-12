import json, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import record_deployment
from publication_assets import (
    hash_static_manifest_files,
    reusable_static_assets,
    validate_static_manifest_path,
)


class StaticAssetReuseTests(unittest.TestCase):
    def test_static_manifest_path_validation_and_hashing(self):
        for bad in ['../secret', 'static/../etc/passwd', '/static/a.webp', 'assets/a.webp', 'static/', 'static\\a.webp']:
            with self.assertRaises(RuntimeError):
                validate_static_manifest_path(bad)

        with tempfile.TemporaryDirectory() as temp:
            dist = Path(temp)
            (dist / 'static/sub').mkdir(parents=True)
            (dist / 'static/a.webp').write_bytes(b'alpha')
            (dist / 'static/sub/1.webp').write_bytes(b'beta')
            hashes = hash_static_manifest_files(dist, ['static/a.webp', 'static/sub/1.webp'])
            self.assertEqual(set(hashes.keys()), {'static/a.webp', 'static/sub/1.webp'})
            self.assertEqual(len(hashes['static/a.webp']), 64)
            with self.assertRaises(RuntimeError):
                hash_static_manifest_files(dist, ['static/missing.webp'])

    def test_reusable_static_assets_requires_matching_verified_deployment_and_digest(self):
        local = {'static/a.webp': 'hash-a', 'static/b.webp': 'hash-b-new', 'static/c.webp': 'hash-c'}
        previous = {'status': 'verified', 'deployment_id': 'dep-1', 'source_sha': 'sha-1'}
        state = {
            'verified_static_assets': {
                'deployment_id': 'dep-1',
                'source_sha': 'sha-1',
                'files': {'static/a.webp': 'hash-a', 'static/b.webp': 'hash-b-old'},
            }
        }
        self.assertEqual(reusable_static_assets(local, state, previous), {'static/a.webp'})
        self.assertEqual(reusable_static_assets(local, state, previous, full_verify=True), set())
        self.assertEqual(reusable_static_assets(local, state, {**previous, 'status': 'deployed_unverified'}), set())
        self.assertEqual(reusable_static_assets(local, state, {**previous, 'deployment_id': 'dep-2'}), set())
        self.assertEqual(reusable_static_assets(local, state, {**previous, 'source_sha': 'sha-2'}), set())
        self.assertEqual(reusable_static_assets(local, {}, previous), set())


class RecordDeploymentTests(unittest.TestCase):
    def _build_fixture(self, root: Path):
        (root / 'work').mkdir()
        (root / 'state').mkdir()
        (root / 'content').mkdir()
        (root / 'assets/slides').mkdir(parents=True)
        (root / 'assets/illustrations/ep1').mkdir(parents=True)
        (root / 'dist/static/deck1').mkdir(parents=True)

        (root / 'config.json').write_text(json.dumps({'domain': 'https://example.test/site'}))
        (root / 'package.json').write_text(json.dumps({'version': '2.1.0'}))
        (root / 'style.css').write_text('body{color:#000}')
        (root / 'app.js').write_text('console.log(1)')
        (root / 'search.js').write_text('export function s(){}')
        (root / 'content/ep1.json').write_text(json.dumps({'headline': '测试标题'}))
        (root / 'assets/slides/ep1.pdf').write_bytes(b'%PDF-1.4\nbody')
        (root / 'assets/illustrations/ep1/0.webp').write_bytes(b'RIFFwebp0')
        (root / 'dist/static/deck1/1.webp').write_bytes(b'RIFFslide1')
        search_idx = {'version': '2.1.0', 'entries': []}
        (root / 'dist/search-index.json').write_text(json.dumps(search_idx))
        manifest = {'version': '2.1.0', 'files': ['static/deck1/1.webp']}
        (root / 'dist/asset-manifest.json').write_text(json.dumps(manifest))
        (root / 'state/progress.json').write_text(json.dumps({'deployments': [], 'episodes': {'ep1': {}}}))

        live_map = {
            'https://example.test/site/': (b'<html>v2.1.0</html>', 'text/html'),
            'https://example.test/site/style.css': (b'body{color:#000}', 'text/css'),
            'https://example.test/site/app.js': (b'console.log(1)', 'application/javascript'),
            'https://example.test/site/search.js': (b'export function s(){}', 'application/javascript'),
            'https://example.test/site/search-index.json': (json.dumps(search_idx).encode(), 'application/json'),
            'https://example.test/site/asset-manifest.json': (json.dumps(manifest).encode(), 'application/json'),
            'https://example.test/site/static/deck1/1.webp': (b'RIFFslide1', 'image/webp'),
            'https://example.test/site/topics/': ('半拿铁 与 知行小酒馆'.encode(), 'text/html'),
            'https://example.test/site/shows/bannatie/t1/': ('半拿铁 / 专题一'.encode(), 'text/html'),
            'https://example.test/site/episodes/ep1/': ('<h1>测试标题</h1>'.encode(), 'text/html'),
            'https://example.test/site/assets/slides/ep1.pdf?verify=sha-1': (b'%PDF-1.4\nbody', 'application/pdf'),
            'https://example.test/site/assets/illustrations/ep1/0.webp': (b'RIFFwebp0', 'image/webp'),
        }
        return live_map

    def _run_with_fake_batch(self, root: Path, deployment_id: str, sha: str, live_map: dict, full_verify=False):
        fetched_urls = []

        class FakeBatch:
            def __init__(self, work, env):
                self.data = {}

            def fetch(self, urls):
                fetched_urls.extend(urls)
                for u in urls:
                    self.data[u] = live_map[u]

            def get(self, url):
                return self.data[url]

        def fake_check_output(cmd, **kwargs):
            if cmd[:3] == ['git', 'rev-parse', 'HEAD']:
                return sha + '\n'
            if cmd[:3] == ['git', 'branch', '--show-current']:
                return 'main\n'
            if 'ls-remote' in cmd:
                return sha + '\trefs/heads/main\n'
            raise AssertionError(f'Unexpected subprocess call: {cmd}')

        with patch('record_deployment.HttpsBatch', FakeBatch), \
             patch('record_deployment.subprocess.check_output', side_effect=fake_check_output), \
             patch('record_deployment.network_env', return_value={}), \
             patch('record_deployment.verified_unchanged_asset', side_effect=lambda *_: sha != 'sha-1'):
            summary = record_deployment.verify_and_record(
                root,
                deployment_id,
                full_verify=full_verify,
                topic_groups=[('半拿铁', '专题一')],
                topic_url_fn=lambda t, s: '/shows/bannatie/t1/',
            )
        return summary, fetched_urls

    def test_incremental_static_asset_reuse_and_full_verify_override(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            live_map = self._build_fixture(root)

            # First verified deployment seeds verified_static_assets after full HTTPS check.
            summary1, fetched1 = self._run_with_fake_batch(root, 'dep-1', 'sha-1', live_map)
            self.assertIn('https://example.test/site/static/deck1/1.webp', fetched1)
            self.assertEqual(summary1, {'verified_episodes': 1, 'static_total': 1, 'static_fetched': 1, 'static_reused': 0})

            state1 = json.loads((root / 'state/progress.json').read_text())
            self.assertEqual(state1['verified_static_assets']['deployment_id'], 'dep-1')
            self.assertEqual(list(state1['verified_static_assets']['files'].keys()), ['static/deck1/1.webp'])

            # Add one new static file while keeping static/deck1/1.webp byte-identical.
            (root / 'dist/static/deck1/2.webp').write_bytes(b'RIFFslide2')
            manifest2 = {'version': '2.1.0', 'files': ['static/deck1/1.webp', 'static/deck1/2.webp']}
            (root / 'dist/asset-manifest.json').write_text(json.dumps(manifest2))
            live_map['https://example.test/site/asset-manifest.json'] = (json.dumps(manifest2).encode(), 'application/json')
            live_map['https://example.test/site/static/deck1/2.webp'] = (b'RIFFslide2', 'image/webp')

            summary2, fetched2 = self._run_with_fake_batch(root, 'dep-2', 'sha-2', live_map)
            self.assertNotIn('https://example.test/site/static/deck1/1.webp', fetched2)
            self.assertIn('https://example.test/site/static/deck1/2.webp', fetched2)
            self.assertEqual(summary2, {'verified_episodes': 1, 'static_total': 2, 'static_fetched': 1, 'static_reused': 1})

            # Failure on live new static file keeps dep-2 baseline intact without overwriting state.
            (root / 'dist/static/deck1/3.webp').write_bytes(b'RIFFslide3')
            manifest3 = {'version': '2.1.0', 'files': ['static/deck1/1.webp', 'static/deck1/2.webp', 'static/deck1/3.webp']}
            (root / 'dist/asset-manifest.json').write_text(json.dumps(manifest3))
            live_map['https://example.test/site/asset-manifest.json'] = (json.dumps(manifest3).encode(), 'application/json')
            live_map['https://example.test/site/static/deck1/3.webp'] = (b'CORRUPTED', 'image/webp')

            with self.assertRaises(RuntimeError):
                self._run_with_fake_batch(root, 'dep-fail', 'sha-3', live_map)
            state_after_fail = json.loads((root / 'state/progress.json').read_text())
            self.assertEqual(state_after_fail['verified_static_assets']['deployment_id'], 'dep-2')
            self.assertEqual(len(state_after_fail['deployments']), 2)

            # Explicit --full-verify re-fetches all static assets even when unchanged.
            live_map['https://example.test/site/static/deck1/3.webp'] = (b'RIFFslide3', 'image/webp')
            live_map['https://example.test/site/assets/slides/ep1.pdf?verify=sha-3'] = (b'%PDF-1.4\nbody', 'application/pdf')
            summary3, fetched3 = self._run_with_fake_batch(root, 'dep-3', 'sha-3', live_map, full_verify=True)
            self.assertIn('https://example.test/site/static/deck1/1.webp', fetched3)
            self.assertIn('https://example.test/site/static/deck1/2.webp', fetched3)
            self.assertIn('https://example.test/site/static/deck1/3.webp', fetched3)
            self.assertEqual(summary3, {'verified_episodes': 1, 'static_total': 3, 'static_fetched': 3, 'static_reused': 0})
