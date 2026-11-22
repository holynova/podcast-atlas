"""Convert a temporary NotebookLM PDF into the final, image-only deliverable.

Existing reviewed page images are migrated byte-for-byte, never recompressed.
New inputs are rendered with Poppler (including text/vector corrections).
"""
import argparse
import hashlib
import json
import pathlib
import shutil
import subprocess
import tempfile
from PIL import Image
from pypdf import PdfReader
from slide_decks import digest, load_decks, save_decks

ROOT = pathlib.Path(__file__).resolve().parents[1]
POPPLER = pathlib.Path.home() / '.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/override/pdftoppm'
RECIPE = b'images-only-v1:poppler-native:webp-q90'


def inspect_images(directory, pages):
    images = []
    for page in range(1, pages + 1):
        path = directory / f'{page}.webp'
        with Image.open(path) as image:
            if image.format != 'WEBP':
                raise ValueError('Expected WebP: ' + str(path))
            image.load()
            width, height = image.size
        images.append({'sha256': digest(path), 'size': path.stat().st_size, 'width': width, 'height': height})
    return images


def migrate(root):
    decks = dict(load_decks(root))
    index = json.loads((root / 'work/site-slides/.cache-index.json').read_text())
    for pdf in sorted((root / 'assets/slides').glob('*.pdf')):
        entry = index[pdf.stem]
        key = hashlib.sha256(pdf.read_bytes() + entry['recipe'].encode()).hexdigest()[:16]
        if key != entry['key']:
            raise RuntimeError('Stale reviewed image cache: ' + pdf.stem)
        pages = len(PdfReader(pdf).pages)
        if pages != entry['pages']:
            raise RuntimeError('Page count changed: ' + pdf.stem)
        deck = {'key': key, 'pages': pages, 'source_pdf_sha256': digest(pdf),
                'images': inspect_images(root / 'work/site-slides' / key, pages)}
        raw = root / 'work' / (pdf.stem + '-uncompressed.pdf')
        if raw.is_file():
            deck['input_pdf_sha256'] = digest(raw)
        decks[pdf.stem] = deck
    save_decks(root, decks)
    print(f'Migrated {len(decks)} decks, {sum(d["pages"] for d in decks.values())} unchanged page images')


def convert(root, pdf, eid):
    source_hash = digest(pdf)
    key = hashlib.sha256(pdf.read_bytes() + RECIPE).hexdigest()[:16]
    pages = len(PdfReader(pdf).pages)
    if pages < 1:
        raise ValueError('Empty slide deck')
    cache = root / 'work/site-slides'
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / key
    poppler = str(POPPLER) if POPPLER.is_file() else shutil.which('pdftoppm')
    if not poppler:
        raise RuntimeError('Poppler is required to render image deliverables')
    if not target.is_dir():
        with tempfile.TemporaryDirectory(dir=cache) as temporary:
            stage = pathlib.Path(temporary)
            for page in range(1, pages + 1):
                prefix = stage / 'render'
                subprocess.run([poppler, '-f', str(page), '-l', str(page), '-singlefile', '-scale-to', '2752', '-png', str(pdf), str(prefix)], check=True, timeout=120)
                with Image.open(prefix.with_suffix('.png')) as image:
                    image.convert('RGB').save(stage / f'{page}.webp', 'WEBP', quality=90, method=4)
                prefix.with_suffix('.png').unlink()
            images = inspect_images(stage, pages)
            stage.rename(target)
    else:
        images = inspect_images(target, pages)
    illustrations = root / 'assets/illustrations' / eid
    illustrations.mkdir(parents=True, exist_ok=True)
    meta = illustrations / 'pages.json'
    metadata = json.loads(meta.read_text()) if meta.exists() else {}
    samples = metadata.get('samples') if metadata.get('reviewed') else sorted(set([0] + [round(i * (pages - 1) / 6) for i in range(1, 7)]))
    if not samples or any(type(i) is not int or not 0 <= i < pages for i in samples):
        raise ValueError('Invalid reviewed image samples')
    for i, page in enumerate(samples):
        with Image.open(target / f'{page + 1}.webp') as image:
            image = image.convert('RGB')
            image.thumbnail((1280, 1280), Image.Resampling.LANCZOS)
            image.save(illustrations / f'{i}.webp', 'WEBP', quality=85)
    metadata.update(pages=pages, samples=samples)
    meta.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n')
    decks = dict(load_decks(root))
    decks[eid] = {'key': key, 'pages': pages, 'input_pdf_sha256': source_hash, 'images': images}
    save_decks(root, decks)
    print(f'Imported {eid}: {pages} verified WebP pages; PDF retained only until publication verification')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=pathlib.Path, default=ROOT)
    parser.add_argument('--migrate', action='store_true')
    parser.add_argument('--pdf', type=pathlib.Path)
    parser.add_argument('--id')
    args = parser.parse_args()
    if args.migrate:
        migrate(args.root)
    elif args.pdf and args.id:
        convert(args.root, args.pdf, args.id)
    else:
        parser.error('Use --migrate or --pdf PATH --id EPISODE')
