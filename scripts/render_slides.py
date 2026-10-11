import pathlib, sys, subprocess, json
from pypdf import PdfReader
from PIL import Image
source = pathlib.Path(sys.argv[1]); doc = PdfReader(source)
target = source.parent.parent / 'illustrations' / source.stem; target.mkdir(parents=True, exist_ok=True)
# Six story panels, distributed through the deck, plus a cover.
indices = sorted(set([0] + [round(i * (len(doc.pages) - 1) / 6) for i in range(1, 7)]))
for i, page in enumerate(indices):
    prefix = target / f'tmp-{i}'
    subprocess.run(['/Users/sym/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/override/pdftoppm', '-f', str(page+1), '-l', str(page+1), '-singlefile', '-scale-to', '1280', '-png', str(source), str(prefix)], check=True)
    png = prefix.with_suffix('.png')
    with Image.open(png) as image: image.convert('RGB').save(target / f'{i}.webp', 'WEBP', quality=85)
    png.unlink()
(target / 'pages.json').write_text(json.dumps({'pages': len(doc.pages), 'samples': indices}))
print(f'Rendered {len(doc.pages)} pages, {len(indices)} illustrations: {source.name}')
