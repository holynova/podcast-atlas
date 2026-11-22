"""Verify published asset boundary and links in real generated documents."""
import json, pathlib, sys
from html.parser import HTMLParser
from urllib.parse import unquote, urlparse
ROOT = pathlib.Path(__file__).resolve().parents[1]; DIST = ROOT / 'dist'
BASE = json.loads((ROOT / 'config.json').read_text()).get('base_path', '')
errors = []
class Links(HTMLParser):
    def __init__(self, path): super().__init__(); self.path = path
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        prefix = attrs.get('data-slide-prefix')
        if prefix:
            if BASE and prefix.startswith(BASE + '/'): prefix = prefix[len(BASE):]
            count = int(attrs.get('data-slide-count', '0'))
            if count <= 0: errors.append('Invalid slide page count')
            for page in range(1, count + 1):
                if not (DIST / prefix.lstrip('/') / f'{page}.webp').is_file():
                    errors.append(f'Missing slide page: {prefix}{page}.webp')
        for attr in ('href', 'src'):
            val = attrs.get(attr, '')
            if not val.startswith('/') or val.startswith('//'): continue
            val = unquote(urlparse(val).path)
            if val.lower().endswith('.pdf'): errors.append('Local PDF reference: ' + val)
            if BASE and (val == BASE or val.startswith(BASE + '/')): val = val[len(BASE):] or '/'
            target = DIST / val.lstrip('/')
            if target.is_dir(): target = target / 'index.html'
            if not target.is_file(): errors.append(f'{self.path.relative_to(DIST)}: missing {val}')
for page in DIST.rglob('*.html'): Links(page).feed(page.read_text())
for name in ['state', 'work', 'config.json', 'transcript.txt', 'transcript.json', '.env']:
    if any(p.name == name for p in DIST.rglob('*')): errors.append('Private/source file in dist: ' + name)
for pdf in DIST.rglob('*.pdf'):
    errors.append('PDF is not a deliverable: ' + str(pdf.relative_to(DIST)))
if 'pdfjs' in (DIST / 'app.js').read_text().lower(): errors.append('PDF viewer still included')
for asset in DIST.rglob('*'):
    if asset.is_file() and asset.stat().st_size > 25*1024*1024: errors.append('Static asset exceeds 25 MiB: ' + str(asset.relative_to(DIST)))
sys.path.insert(0, str(ROOT / 'scripts'))
from pipeline import validate_article
for article in (ROOT / 'content').glob('*.json'):
    try: validate_article(json.loads(article.read_text()))
    except Exception as e: errors.append(f'{article.name}: {e}')
if errors: print('\n'.join(errors)); sys.exit(1)
print(f'OK: {len(list(DIST.rglob("*.html")))} pages, local links, article schemas, image-only delivery and public asset boundary.')
