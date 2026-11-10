"""Render cached, content-addressed WebP slide decks without modifying original PDFs."""
import hashlib, json, os, pathlib, re, shutil, subprocess, sys, tempfile
from concurrent.futures import ThreadPoolExecutor
from PIL import Image

POPPLER_BIN = '/Users/sym/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/override/pdftoppm'
RECIPE_TAG = b'slides-v1:1376:75'


def find_pdftoppm():
    if pathlib.Path(POPPLER_BIN).is_file():
        return POPPLER_BIN
    found = shutil.which('pdftoppm')
    if not found:
        raise RuntimeError('Slide WebP builds require Poppler pdftoppm.')
    return found


def page_sort_key(path):
    match = re.search(r'-(\d+)$', path.stem)
    return int(match.group(1)) if match else 0


def copy_cached_deck(src_dir, dst_dir, pages):
    dst_dir.mkdir(parents=True, exist_ok=True)
    for page in range(1, pages + 1):
        name = f'{page}.webp'
        shutil.copyfile(src_dir / name, dst_dir / name)


def build_deck(args):
    pdf, cache, dist_static, pdftoppm, cached_entry = args
    stat = pdf.stat()
    if cached_entry and cached_entry.get('size') == stat.st_size and cached_entry.get('mtime_ns') == stat.st_mtime_ns:
        key = cached_entry['key']
        deck_cache = cache / key
        meta_path = deck_cache / 'meta.json'
        if meta_path.is_file():
            pages = json.loads(meta_path.read_text()).get('pages', 0)
            if pages > 0 and all((deck_cache / f'{p}.webp').is_file() for p in range(1, pages + 1)):
                copy_cached_deck(deck_cache, dist_static / key, pages)
                return pdf.stem, {'prefix': f'/static/{key}/', 'pages': pages, 'size': stat.st_size, 'mtime_ns': stat.st_mtime_ns, 'key': key}

    raw = pdf.read_bytes()
    key = hashlib.sha256(raw + RECIPE_TAG).hexdigest()[:16]
    deck_cache = cache / key
    meta_path = deck_cache / 'meta.json'
    if not meta_path.is_file():
        tmp_cache = cache / f'{key}.tmp-{os.getpid()}-{pdf.stem}'
        if tmp_cache.exists():
            shutil.rmtree(tmp_cache)
        tmp_cache.mkdir(parents=True, exist_ok=True)
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                prefix = str(pathlib.Path(tmpdir) / 'p')
                subprocess.run([pdftoppm, '-scale-to', '1376', str(pdf), prefix], check=True)
                rendered = sorted(pathlib.Path(tmpdir).glob('p-*.p?m'), key=page_sort_key)
                if not rendered:
                    raise RuntimeError(f'No pages rendered for {pdf.name}')
                for idx, ppm in enumerate(rendered, 1):
                    with Image.open(ppm) as im:
                        im.convert('RGB').save(tmp_cache / f'{idx}.webp', 'WEBP', quality=75, method=2)
                (tmp_cache / 'meta.json').write_text(json.dumps({'pages': len(rendered)}))
            if deck_cache.exists():
                shutil.rmtree(tmp_cache)
            else:
                tmp_cache.replace(deck_cache)
        finally:
            if tmp_cache.exists():
                shutil.rmtree(tmp_cache, ignore_errors=True)

    pages = json.loads(meta_path.read_text())['pages']
    copy_cached_deck(deck_cache, dist_static / key, pages)
    return pdf.stem, {'prefix': f'/static/{key}/', 'pages': pages, 'size': stat.st_size, 'mtime_ns': stat.st_mtime_ns, 'key': key}


def main(root, dist):
    slides_dir = root / 'assets/slides'
    if not slides_dir.is_dir():
        print('{}')
        return
    pdfs = sorted(slides_dir.glob('*.pdf'))
    if not pdfs:
        print('{}')
        return
    pdftoppm = find_pdftoppm()
    cache = root / 'work/site-slides'
    cache.mkdir(parents=True, exist_ok=True)
    index_path = cache / '.cache-index.json'
    cached_index = json.loads(index_path.read_text()) if index_path.is_file() else {}
    dist_static = dist / 'static'
    dist_static.mkdir(parents=True, exist_ok=True)
    workers = min(8, max(2, os.cpu_count() or 4))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = dict(pool.map(build_deck, [(p, cache, dist_static, pdftoppm, cached_index.get(p.stem)) for p in pdfs]))
    index_path.write_text(json.dumps({k: {'key': v['key'], 'pages': v['pages'], 'size': v['size'], 'mtime_ns': v['mtime_ns']} for k, v in results.items()}, separators=(',', ':')))
    output = {k: {'prefix': v['prefix'], 'pages': v['pages']} for k, v in results.items()}
    print(json.dumps(output, separators=(',', ':')))


if __name__ == '__main__':
    main(pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]))
