import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import slide_decks as slides
import pipeline
import cycle


class SlideDeliveryTests(unittest.TestCase):
    def fixture(self, root):
        image = b'original-page-image'
        deck = {'key': '0123456789abcdef', 'pages': 1, 'images': [
            {'sha256': hashlib.sha256(image).hexdigest(), 'size': len(image), 'width': 100, 'height': 100}]}
        slides.save_decks(root, {'episode': deck})
        (root / 'config.json').write_text(json.dumps({'domain': 'https://example.test/site'}))
        return deck, image

    def test_completed_deck_without_pdf_or_cache_is_not_queued_again(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            episode = {'id': 'episode', 'available': True, 'show': '半拿铁', 'topic': '单集精选', 'rank': 1, 'order': 1, 'date': '2026-01-01'}
            state = {'episodes': {'episode': {}}}
            with patch.object(pipeline, 'ROOT', root), patch.object(cycle.b, 'IDS', []), patch.object(pipeline, 'write_json'), patch.object(pipeline, 'get_artifacts') as remote:
                self.assertTrue(pipeline.collect_slides(state, episode))
                self.assertEqual(cycle.plan(state, [episode], 'slot', 1, 1)['slide_ids'], [])
            remote.assert_not_called()
            self.assertEqual(state['episodes']['episode']['delivery_format'], 'images')

    def test_staging_uses_verified_cache_and_independent_copies(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); deck, image = self.fixture(root)
            source = slides.image_path(root, deck, 1)
            source.parent.mkdir(parents=True); source.write_bytes(image)
            with patch.object(slides, 'restore_image') as restore:
                slides.stage_decks(root, root / 'dist')
            restore.assert_not_called()
            staged = root / 'dist/static' / deck['key'] / '1.webp'
            self.assertEqual(staged.read_bytes(), image)
            staged.write_bytes(b'changed output')
            self.assertEqual(source.read_bytes(), image)

    def test_restore_accepts_only_expected_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); deck, image = self.fixture(root)
            receipt = deck['images'][0]
            with patch('pipeline.network_env', return_value={}), patch('slide_decks.subprocess.run') as fetch:
                fetch.side_effect = lambda cmd, **kwargs: Path(cmd[cmd.index('--output') + 1]).write_bytes(b'corrupted')
                with self.assertRaises(RuntimeError): slides.restore_image(root, deck, 1, receipt)
                self.assertFalse(slides.image_path(root, deck, 1).exists())
                fetch.side_effect = lambda cmd, **kwargs: Path(cmd[cmd.index('--output') + 1]).write_bytes(image)
                self.assertEqual(slides.restore_image(root, deck, 1, receipt).read_bytes(), image)

    def test_input_cleanup_requires_complete_online_receipts_and_matching_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); deck, image = self.fixture(root)
            source = root / 'work/slide-inputs/episode.pdf'
            source.parent.mkdir(parents=True); source.write_bytes(b'pdf-input')
            deck['input_pdf_sha256'] = slides.digest(source)
            slides.save_decks(root, {'episode': deck})
            state = {'deployments': [{'status': 'verified', 'deployment_id': 'd', 'source_sha': 's'}],
                     'verified_static_assets': {'deployment_id': 'd', 'source_sha': 's', 'files': {}}}
            self.assertEqual(slides.remove_verified_pdf_inputs(root, state), [])
            state['verified_static_assets']['files'][f"static/{deck['key']}/1.webp"] = deck['images'][0]['sha256']
            source.write_bytes(b'new-unpublished-input')
            self.assertEqual(slides.remove_verified_pdf_inputs(root, state), [])
            source.write_bytes(b'pdf-input')
            self.assertEqual(len(slides.remove_verified_pdf_inputs(root, state)), 1)
            self.assertFalse(source.exists())

    def test_manifest_rejects_paths_and_incomplete_decks(self):
        with self.assertRaises(ValueError): slides.validate_deck('../private', {})
        with self.assertRaises(ValueError): slides.validate_deck('episode', {'key': '../private', 'pages': 1, 'images': []})
        with self.assertRaises(ValueError): slides.validate_deck('episode', {'key': '0' * 16, 'pages': 2, 'images': [{'sha256': '0' * 64, 'size': 1}]})
