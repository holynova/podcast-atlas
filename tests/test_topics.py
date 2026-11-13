import importlib.util,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('site_build',Path(__file__).resolve().parents[1]/'scripts/build.py');b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)

class TopicTests(unittest.TestCase):
    def test_repeated_source_timestamps_show_warning_without_hiding_valid_times(self):
        eid,original=next(iter(b.ARTICLES.items()))
        article=__import__('copy').deepcopy(original)
        article['sections'][0]['timestamp_quality']='source_repeated'
        article['sections'][1].pop('timestamp_quality',None)
        ep=next(row for row in b.QUEUE if row['id']==eid)
        page=b.episode(ep,article)
        first=page.split('id="chapter-0"')[1].split('</section>')[0]
        second=page.split('id="chapter-1"')[1].split('</section>')[0]
        self.assertIn('文稿时间异常 · 听原节目',first)
        self.assertNotIn('原节目 '+article['sections'][0]['timestamp'],first)
        self.assertIn('原节目 '+article['sections'][1]['timestamp'],second)

    def test_reviewed_images_use_explicit_chapter_mapping_and_require_real_assets(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(b,'ROOT',Path(temp)):
            directory=Path(temp)/'assets/illustrations/e';directory.mkdir(parents=True)
            (directory/'2.webp').write_bytes(b'picture')
            manifest=directory/'pages.json';manifest.write_text(json.dumps({'chapter_images':{'1':'2.webp'}}))
            self.assertEqual(b.reviewed_chapter_images('e',3),{1:directory/'2.webp'})
            manifest.write_text(json.dumps({'chapter_images':{'1':'missing.webp'}}))
            with self.assertRaises(ValueError):b.reviewed_chapter_images('e',3)
            manifest.write_text(json.dumps({'chapter_images':{'3':'2.webp'}}))
            with self.assertRaises(ValueError):b.reviewed_chapter_images('e',3)

    def test_same_name_topics_have_distinct_urls_and_never_mix_episodes(self):
        rows=[{'id':'a','show':'半拿铁','topic':'同名专题','order':1,'title':'半拿铁独有故事','date':'2026-01-01','available':True},{'id':'b','show':'知行小酒馆','topic':'同名专题','order':1,'title':'小酒馆独有故事','date':'2026-01-02','available':True}]
        with patch.object(b,'QUEUE',rows),patch.object(b,'TOPICS',['同名专题']),patch.object(b,'TOPIC_GROUPS',[('半拿铁','同名专题'),('知行小酒馆','同名专题')]),patch.object(b,'ARTICLES',{}):
            self.assertNotEqual(b.topic_url('同名专题','半拿铁'),b.topic_url('同名专题','知行小酒馆'))
            page=b.topic_page('同名专题','半拿铁')
            main=page.split('<main id="main">')[1].split('</main>')[0]
            self.assertIn('半拿铁独有故事',main);self.assertNotIn('小酒馆独有故事',main)
            legacy=b.topic_page('同名专题')
            self.assertIn('/shows/bannatie/',legacy);self.assertIn('/shows/zhixing/',legacy)

    def test_search_index_includes_public_metadata_but_not_private_paths(self):
        index=b.search_index()
        self.assertEqual(len(index['entries']),len(b.QUEUE))
        serialized=__import__('json').dumps(index,ensure_ascii=False)
        for forbidden in ['text_path','json_path','source_id','notebook_id','last_error','/Users/sym','逐字稿原文']:self.assertNotIn(forbidden,serialized)
        for row in index['entries']:self.assertTrue(row['url'].startswith('/podcast-atlas/'))

    def test_all_topics_uses_hierarchical_bento_and_preserves_show_anchors(self):
        page=b.all_topics()
        main=page.split('<main id="main">')[1].split('</main>')[0]
        self.assertIn('class="wrap topics-bento"',main)
        self.assertIn('id="bannatie"',main)
        self.assertIn('id="zhixing"',main)
        self.assertIn('class="bento-hero-card"',main)
        self.assertIn('class="bento-mid-card"',main)
        self.assertIn('class="bento-chip-row"',main)
        self.assertIn('class="bento-archive-card"',main)
        self.assertIn('/podcast-atlas/shows/bannatie/topics/',main)
        self.assertIn('/podcast-atlas/shows/zhixing/topics/',main)
        self.assertGreater(main.count('<img '),6)

    def test_index_series_uses_hierarchical_bento_and_preserves_show_anchors(self):
        page=b.index()
        series=page.split('<section id="series"')[1].split('<section id="library"')[0]
        self.assertIn('id="bannatie"',series)
        self.assertIn('id="zhixing"',series)
        self.assertIn('class="bento-group"',series)
        self.assertIn('class="bento-hero-card"',series)
        self.assertIn('class="bento-mid-card"',series)
        self.assertIn('class="bento-chip-row"',series)
        self.assertIn('class="bento-archive-card"',series)
        self.assertIn('<h3 id="show-bannatie">',series)
        self.assertGreater(series.count('<img '),6)

    def test_index_library_sorts_by_date_descending_latest_first(self):
        page=b.index()
        library=page.split('<section id="library"')[1]
        dates=__import__('re').findall(r'<time>(\d{4}-\d{2}-\d{2})</time>',library)
        self.assertGreater(len(dates),10)
        self.assertEqual(dates,sorted(dates,reverse=True))

    def test_search_interface_is_minimal_and_avoids_verbose_descriptions(self):
        dlg = b.search_dialog()
        self.assertIn('id="command-search"', dlg)
        self.assertIn('class="command-bar"', dlg)
        self.assertIn('id="command-query"', dlg)
        self.assertIn('id="command-results"', dlg)
        self.assertIn('class="command-close"', dlg)
        for verbose_text in ['找一集，或一个关键词', 'command-heading', 'command-input-label', 'command-filters', 'command-help', '输入关键词开始搜索', '↑ ↓ 选择']:
            self.assertNotIn(verbose_text, dlg)
        index_page = b.index()
        library_tools = index_page.split('<div class="library-tools">')[1].split('<div class="episode-grid"')[0]
        self.assertIn('class="search-icon"', library_tools)
        self.assertNotIn('<span>搜索</span>', library_tools)


