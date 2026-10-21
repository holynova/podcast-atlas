"""Generate cached, fingerprinted cover variants without replacing reviewed sources."""
import hashlib, json, pathlib, shutil, sys
from PIL import Image

def main(root, dist):
    cache = root / 'work/site-thumbnails'
    cache.mkdir(parents=True, exist_ok=True)
    (dist / 'static').mkdir(parents=True, exist_ok=True)
    images = {}
    for source in sorted((root / 'assets/illustrations').glob('*/0.webp')):
        raw = source.read_bytes()
        with Image.open(source) as original:
            variants = []
            for width in sorted(set(min(w, original.width) for w in [480, 768, 1280])):
                key = hashlib.sha256(raw + f'cover-v1:{width}:82'.encode()).hexdigest()[:16]
                target = cache / (key + '.webp')
                if not target.exists():
                    image = original.convert('RGB')
                    image.thumbnail((width, round(original.height * width / original.width)), Image.Resampling.LANCZOS)
                    image.save(target, 'WEBP', quality=82, method=6)
                shutil.copyfile(target, dist / 'static' / target.name)
                variants.append({'url': '/static/' + target.name, 'width': width})
            images[source.parent.name] = {'width': original.width, 'height': original.height, 'variants': variants}
    print(json.dumps(images, separators=(',', ':')))

if __name__ == '__main__':
    main(pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]))
