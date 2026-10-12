import importlib.util,unittest
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('site_build',Path(__file__).resolve().parents[1]/'scripts/build.py');b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)

class TopicTests(unittest.TestCase):
    def test_same_name_topics_have_distinct_urls_and_never_mix_episodes(self):
        rows=[{'id':'a','show':'半拿铁','topic':'同名专题','order':1,'title':'半拿铁独有故事','date':'2026-01-01','available':True},{'id':'b','show':'知行小酒馆','topic':'同名专题','order':1,'title':'小酒馆独有故事','date':'2026-01-02','available':True}]
        with patch.object(b,'QUEUE',rows),patch.object(b,'TOPICS',['同名专题']),patch.object(b,'TOPIC_GROUPS',[('半拿铁','同名专题'),('知行小酒馆','同名专题')]),patch.object(b,'ARTICLES',{}):
            self.assertNotEqual(b.topic_url('同名专题','半拿铁'),b.topic_url('同名专题','知行小酒馆'))
            page=b.topic_page('同名专题','半拿铁')
            self.assertIn('半拿铁独有故事',page);self.assertNotIn('小酒馆独有故事',page)
            legacy=b.topic_page('同名专题')
            self.assertIn('/shows/bannatie/',legacy);self.assertIn('/shows/zhixing/',legacy)

    def test_search_index_includes_public_metadata_but_not_private_paths(self):
        index=b.search_index()
        self.assertEqual(len(index['entries']),len(b.QUEUE))
        serialized=__import__('json').dumps(index,ensure_ascii=False)
        for forbidden in ['text_path','json_path','source_id','notebook_id','last_error','/Users/sym','逐字稿原文']:self.assertNotIn(forbidden,serialized)
        for row in index['entries']:self.assertTrue(row['url'].startswith('/podcast-atlas/'))
