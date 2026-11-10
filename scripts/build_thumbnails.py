"""Generate cached, fingerprinted cover variants without replacing reviewed sources."""
import hashlib, json, pathlib, shutil, sys
from concurrent.futures import ThreadPoolExecutor
from PIL import Image

def build_one(args):
    source, cache, dist_static = args
    raw = source.read_bytes()
    with Image.open(source) as original:
        variants = []
        for width in sorted(set(min(w, original.width) for w in [480, 768, 960])):
            key = hashlib.sha256(raw + f'cover-v2:{width}:78'.encode()).hexdigest()[:16]
            target = cache / (key + '.webp')
            if not target.exists():
                image = original.convert('RGB')
                image.thumbnail((width, round(original.height * width / original.width)), Image.Resampling.LANCZOS)
                image.save(target, 'WEBP', quality=78, method=4)
            shutil.copyfile(target, dist_static / target.name)
            variants.append({'url': '/static/' + target.name, 'width': width})
        return source.parent.name, {'width': original.width, 'height': original.height, 'variants': variants}

def main(root, dist):
    cache = root / 'work/site-thumbnails'
    cache.mkdir(parents=True, exist_ok=True)
    dist_static = dist / 'static'
    dist_static.mkdir(parents=True, exist_ok=True)
    sources = sorted((root / 'assets/illustrations').glob('*/0.webp'))
    with ThreadPoolExecutor(max_workers=6) as pool:
        images = dict(pool.map(build_one, [(s, cache, dist_static) for s in sources]))
    print(json.dumps(images, separators=(',', ':')))

if __name__ == '__main__':
    main(pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]))
