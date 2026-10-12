import pathlib, sys, subprocess, json
from pypdf import PdfReader
from PIL import Image
source = pathlib.Path(sys.argv[1]); doc = PdfReader(source)
target = source.parent.parent / 'illustrations' / source.stem; target.mkdir(parents=True, exist_ok=True)
# Six story panels, distributed through the deck, plus a cover.
manifest = target / 'pages.json'
metadata = json.loads(manifest.read_text()) if manifest.exists() else {}
indices = metadata.get('samples') if metadata.get('reviewed') else sorted(set([0] + [round(i * (len(doc.pages) - 1) / 6) for i in range(1, 7)]))
if not indices or any(type(i) is not int or i < 0 or i >= len(doc.pages) for i in indices): raise ValueError('Invalid reviewed slide samples')
for i, page in enumerate(indices):
    prefix = target / f'tmp-{i}'
    subprocess.run(['/Users/sym/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/override/pdftoppm', '-f', str(page+1), '-l', str(page+1), '-singlefile', '-scale-to', '1280', '-png', str(source), str(prefix)], check=True)
    png = prefix.with_suffix('.png')
    with Image.open(png) as image: image.convert('RGB').save(target / f'{i}.webp', 'WEBP', quality=85)
    png.unlink()
metadata.update(pages=len(doc.pages), samples=indices)
(target / 'pages.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n')
print(f'Rendered {len(doc.pages)} pages, {len(indices)} illustrations: {source.name}')
