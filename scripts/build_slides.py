"""Render cached, high-clarity WebP slide decks without modifying original PDFs."""
import hashlib, io, json, os, pathlib, re, shutil, subprocess, sys, tempfile
from concurrent.futures import ThreadPoolExecutor
from PIL import Image, ImageChops
from pypdf import PdfReader

POPPLER_BIN = '/Users/sym/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/override/pdftoppm'
CWEBP_BIN = '/opt/homebrew/bin/cwebp'
RECIPE_TAG = b'slides-v2:uncomp-q90-sharp'


def find_tool(preferred, name):
    if pathlib.Path(preferred).is_file():
        return preferred
    return shutil.which(name)


def flatten_rgb(image):
    if image.mode in ('RGBA', 'LA') or (image.mode == 'P' and 'transparency' in image.info):
        rgba = image.convert('RGBA')
        bg = Image.new('RGB', rgba.size, (255, 255, 255))
        bg.paste(rgba, mask=rgba.getchannel('A'))
        return bg
    return image.convert('RGB')


def macro_hot_tiles(img_a, img_b):
    if img_a.size != img_b.size:
        return 9999
    thumb_a = img_a.resize((64, 36), Image.Resampling.BILINEAR)
    thumb_b = img_b.resize((64, 36), Image.Resampling.BILINEAR)
    diff = ImageChops.difference(thumb_a, thumb_b).get_flattened_data() if hasattr(thumb_a, 'get_flattened_data') else ImageChops.difference(thumb_a, thumb_b).getdata()
    return sum(1 for r, g, b in diff if (r + g + b) / 3 > 12)


def has_vector_overlay(pub_page):
    if pub_page.extract_text().strip():
        return True
    if len(pub_page.images) != 1:
        return True
    contents = pub_page.get_contents()
    if contents is None:
        return False
    if hasattr(contents, 'get_data'):
        return len(contents.get_data()) > 200
    return sum(len(s.get_object().get_data()) for s in contents) > 200


def render_overlay_page(pdf, page_num, pdftoppm, tmpdir, target_size):
    prefix = str(pathlib.Path(tmpdir) / f'ov-{page_num}')
    subprocess.run(
        [pdftoppm, '-f', str(page_num), '-l', str(page_num), '-singlefile', '-scale-to', '2752', str(pdf), prefix],
        check=True
    )
    ppm_path = next(iter(sorted(pathlib.Path(tmpdir).glob(f'ov-{page_num}.p?m'))))
    with Image.open(ppm_path) as rendered:
        img = flatten_rgb(rendered)
        if img.size != target_size:
            img = img.resize(target_size, Image.Resampling.LANCZOS)
        return img


def encode_webp(image, out_path, tmp_ppm, cwebp):
    if cwebp:
        image.save(tmp_ppm, 'PPM')
        subprocess.run([cwebp, '-quiet', '-q', '90', '-m', '4', '-sharp_yuv', str(tmp_ppm), '-o', str(out_path)], check=True)
        tmp_ppm.unlink(missing_ok=True)
    else:
        image.save(out_path, 'WEBP', quality=90, method=4)


def copy_cached_deck(src_dir, dst_dir, pages):
    dst_dir.mkdir(parents=True, exist_ok=True)
    for page in range(1, pages + 1):
        name = f'{page}.webp'
        shutil.copyfile(src_dir / name, dst_dir / name)


def build_deck(args):
    pdf, uncomp_dir, cache, dist_static, pdftoppm, cwebp, cached_entry = args
    stat = pdf.stat()
    if (
        cached_entry
        and cached_entry.get('recipe') == RECIPE_TAG.decode()
        and cached_entry.get('size') == stat.st_size
        and cached_entry.get('mtime_ns') == stat.st_mtime_ns
    ):
        key = cached_entry['key']
        deck_cache = cache / key
        meta_path = deck_cache / 'meta.json'
        if meta_path.is_file():
            pages = json.loads(meta_path.read_text()).get('pages', 0)
            if pages > 0 and all((deck_cache / f'{p}.webp').is_file() for p in range(1, pages + 1)):
                copy_cached_deck(deck_cache, dist_static / key, pages)
                return pdf.stem, {
                    'prefix': f'/static/{key}/',
                    'pages': pages,
                    'size': stat.st_size,
                    'mtime_ns': stat.st_mtime_ns,
                    'key': key,
                }

    raw = pdf.read_bytes()
    key = hashlib.sha256(raw + RECIPE_TAG).hexdigest()[:16]
    deck_cache = cache / key
    meta_path = deck_cache / 'meta.json'
    if not meta_path.is_file():
        pub_reader = PdfReader(io.BytesIO(raw))
        uncomp_path = uncomp_dir / f'{pdf.stem}-uncompressed.pdf'
        uncomp_reader = PdfReader(uncomp_path) if uncomp_path.is_file() else None
        if uncomp_reader and len(uncomp_reader.pages) != len(pub_reader.pages):
            uncomp_reader = None

        tmp_cache = cache / f'{key}.tmp-{os.getpid()}-{pdf.stem}'
        if tmp_cache.exists():
            shutil.rmtree(tmp_cache)
        tmp_cache.mkdir(parents=True, exist_ok=True)
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_ppm = pathlib.Path(tmpdir) / 'frame.ppm'
                for idx, pub_page in enumerate(pub_reader.pages, 1):
                    target_w = round(float(pub_page.mediabox.width))
                    target_h = round(float(pub_page.mediabox.height))
                    if has_vector_overlay(pub_page):
                        if not pdftoppm:
                            raise RuntimeError('Overlay slide pages require Poppler pdftoppm.')
                        frame = render_overlay_page(pdf, idx, pdftoppm, tmpdir, (target_w, target_h))
                    else:
                        with Image.open(io.BytesIO(pub_page.images[0].data)) as pub_im:
                            pub_rgb = flatten_rgb(pub_im)
                        frame = pub_rgb
                        if uncomp_reader and len(uncomp_reader.pages[idx - 1].images) == 1:
                            with Image.open(io.BytesIO(uncomp_reader.pages[idx - 1].images[0].data)) as u_im:
                                u_rgb = flatten_rgb(u_im)
                            if macro_hot_tiles(u_rgb, pub_rgb) <= 5:
                                frame = u_rgb
                    encode_webp(frame, tmp_cache / f'{idx}.webp', tmp_ppm, cwebp)
                (tmp_cache / 'meta.json').write_text(json.dumps({'pages': len(pub_reader.pages)}))
            if deck_cache.exists():
                shutil.rmtree(tmp_cache)
            else:
                tmp_cache.replace(deck_cache)
        finally:
            if tmp_cache.exists():
                shutil.rmtree(tmp_cache, ignore_errors=True)

    pages = json.loads(meta_path.read_text())['pages']
    copy_cached_deck(deck_cache, dist_static / key, pages)
    return pdf.stem, {
        'prefix': f'/static/{key}/',
        'pages': pages,
        'size': stat.st_size,
        'mtime_ns': stat.st_mtime_ns,
        'key': key,
    }


def main(root, dist):
    slides_dir = root / 'assets/slides'
    if not slides_dir.is_dir():
        print('{}')
        return
    pdfs = sorted(slides_dir.glob('*.pdf'))
    if not pdfs:
        print('{}')
        return
    pdftoppm = find_tool(POPPLER_BIN, 'pdftoppm')
    cwebp = find_tool(CWEBP_BIN, 'cwebp')
    uncomp_dir = root / 'work'
    cache = root / 'work/site-slides'
    cache.mkdir(parents=True, exist_ok=True)
    index_path = cache / '.cache-index.json'
    cached_index = json.loads(index_path.read_text()) if index_path.is_file() else {}
    dist_static = dist / 'static'
    dist_static.mkdir(parents=True, exist_ok=True)
    workers = min(8, max(2, os.cpu_count() or 4))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = dict(pool.map(build_deck, [(p, uncomp_dir, cache, dist_static, pdftoppm, cwebp, cached_index.get(p.stem)) for p in pdfs]))
    index_path.write_text(json.dumps({
        k: {'key': v['key'], 'pages': v['pages'], 'size': v['size'], 'mtime_ns': v['mtime_ns'], 'recipe': RECIPE_TAG.decode()}
        for k, v in results.items()
    }, separators=(',', ':')))
    output = {k: {'prefix': v['prefix'], 'pages': v['pages']} for k, v in results.items()}
    print(json.dumps(output, separators=(',', ':')))


if __name__ == '__main__':
    main(pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]))
