"""Generate cached, fingerprinted cover and chapter image variants without replacing reviewed sources."""
import hashlib, json, pathlib, shutil, sys
from concurrent.futures import ThreadPoolExecutor
from PIL import Image


def build_variant_set(args):
    source, key_name, cache, dist_static, widths, tag_prefix, quality = args
    raw = source.read_bytes()
    with Image.open(source) as original:
        variants = []
        for width in sorted(set(min(w, original.width) for w in widths)):
            key = hashlib.sha256(raw + f'{tag_prefix}:{width}:{quality}'.encode()).hexdigest()[:16]
            target = cache / (key + '.webp')
            if not target.is_file():
                image = original.convert('RGB')
                image.thumbnail((width, round(original.height * width / original.width)), Image.Resampling.LANCZOS)
                tmp = cache / f'{key}.tmp.webp'
                image.save(tmp, 'WEBP', quality=quality, method=4)
                tmp.replace(target)
            shutil.copyfile(target, dist_static / target.name)
            variants.append({'url': '/static/' + target.name, 'width': width})
        return key_name, {'width': original.width, 'height': original.height, 'variants': variants}


def main(root, dist, chapter_manifest=None):
    cache = root / 'work/site-thumbnails'
    cache.mkdir(parents=True, exist_ok=True)
    dist_static = dist / 'static'
    dist_static.mkdir(parents=True, exist_ok=True)
    cover_sources = sorted((root / 'assets/illustrations').glob('*/0.webp'))
    tasks = [
        (s, s.parent.name, cache, dist_static, [480, 768, 960], 'cover-v2', 78)
        for s in cover_sources
    ]
    chapter_rels = json.loads(pathlib.Path(chapter_manifest).read_text()) if chapter_manifest else []
    chapter_tasks = []
    for rel in chapter_rels:
        src = root / 'assets/illustrations' / rel
        if src.is_file():
            chapter_tasks.append((src, rel, cache, dist_static, [640, 1080], 'chap-v1', 76))
    with ThreadPoolExecutor(max_workers=6) as pool:
        covers = dict(pool.map(build_variant_set, tasks))
        chapters = dict(pool.map(build_variant_set, chapter_tasks)) if chapter_tasks else {}
    print(json.dumps({'covers': covers, 'chapters': chapters}, separators=(',', ':')))


if __name__ == '__main__':
    main(pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), sys.argv[3] if len(sys.argv) > 3 else None)
