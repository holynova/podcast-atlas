import importlib.util, json, unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('performance_build', Path(__file__).resolve().parents[1] / 'scripts/build.py')
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)

class PerformanceTests(unittest.TestCase):
    def test_initial_library_is_bounded_and_later_articles_have_static_pages(self):
        page = b.index()
        self.assertEqual(page.count('class="episode-card"'), min(24, len(b.ARTICLES)))
        self.assertIn('/library/2/#library', page)
        self.assertNotEqual(b.index(), b.index(2))

    def test_metadata_keeps_people_but_does_not_copy_article_paragraphs(self):
        compact = b.search_index(full=False)
        self.assertEqual(len(compact['entries']), len(b.QUEUE))
        indexed = {e['id']: e for e in compact['entries']}
        for eid, article in b.ARTICLES.items():
            entry = indexed[eid]
            self.assertEqual(entry['summary'], article['dek'])
            self.assertNotIn(article['sections'][0]['paragraphs'][0], entry['text'])
            self.assertIn(article['people'][0]['name'], entry['text'])

    def test_styles_do_not_require_external_font_stylesheet(self):
        styles = (b.ROOT / 'style.css').read_text()
        self.assertNotIn('@import', styles)
        self.assertNotIn('fonts.googleapis.com', styles)

    def test_analytics_loads_independently_of_application_startup(self):
        page = b.shell('Test', '<h1>Test</h1>')
        self.assertIn('<script async src="https://cloud.umami.is/script.js"', page)

    def test_generated_site_has_eager_hero_and_no_full_index_initially(self):
        page = (b.ROOT / 'dist/index.html').read_text()
        self.assertIn('loading="eager" fetchpriority="high"', page)
        self.assertIn('srcset=', page)
        self.assertLess(len(page.encode()), 110000)
        metadata = json.loads((b.ROOT / 'dist/search-index.json').read_text())
        self.assertTrue(metadata['shards'])
        for shard in metadata['shards']:
            path = b.ROOT / 'dist' / shard['url'].removeprefix('/podcast-atlas/')
            self.assertLessEqual(len(json.loads(path.read_text())), 16)
