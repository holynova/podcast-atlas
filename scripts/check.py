"""Verify published asset boundary and links in real generated documents."""
import json, pathlib, sys
from html.parser import HTMLParser
from urllib.parse import unquote, urlparse
ROOT = pathlib.Path(__file__).resolve().parents[1]; DIST = ROOT / 'dist'
errors = []
class Links(HTMLParser):
    def __init__(self, path): super().__init__(); self.path = path
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        for attr in ('href', 'src'):
            val = attrs.get(attr, '')
            if not val.startswith('/') or val.startswith('//'): continue
            val = unquote(urlparse(val).path)
            target = DIST / val.lstrip('/')
            if target.is_dir(): target = target / 'index.html'
            if not target.is_file(): errors.append(f'{self.path.relative_to(DIST)}: missing {val}')
for page in DIST.rglob('*.html'): Links(page).feed(page.read_text())
for name in ['state', 'work', 'config.json', 'transcript.txt', 'transcript.json', '.env']:
    if any(p.name == name for p in DIST.rglob('*')): errors.append('Private/source file in dist: ' + name)
for pdf in (DIST / 'assets/slides').glob('*.pdf'):
    if pdf.read_bytes()[:5] != b'%PDF-': errors.append('Bad PDF: ' + str(pdf))
sys.path.insert(0, str(ROOT / 'scripts'))
from pipeline import validate_article
for article in (ROOT / 'content').glob('*.json'):
    try: validate_article(json.loads(article.read_text()))
    except Exception as e: errors.append(f'{article.name}: {e}')
if errors: print('\n'.join(errors)); sys.exit(1)
print(f'OK: {len(list(DIST.rglob("*.html")))} pages, local links, article schemas, PDF headers and public asset boundary.')
