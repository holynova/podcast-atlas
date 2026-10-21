"""Content-addressed public assets; original PDFs and reviewed images stay intact."""
import hashlib, json, pathlib, shutil, subprocess, sys

def fingerprint(data):
    return hashlib.sha256(data).hexdigest()[:16]

def write_asset(dist, data, suffix):
    rel = 'static/' + fingerprint(data) + suffix
    target = dist / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return '/' + rel

def prepare(root, dist):
    names = ['style.css', 'app.js', 'search.js']
    digest = fingerprint(b''.join((root / n).read_bytes() for n in names))
    directory = dist / 'static' / digest
    directory.mkdir(parents=True, exist_ok=True)
    for name in names:
        shutil.copyfile(root / name, directory / name)
    # Pillow is already used by the project's slide renderer. Use its bundled
    # interpreter when the shell's Python doesn't have it; allow a portable override.
    import importlib.util, os
    interpreter = sys.executable
    if not importlib.util.find_spec('PIL'):
        interpreter = os.environ.get('PODCAST_IMAGE_PYTHON', str(pathlib.Path.home() / '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3'))
    if not pathlib.Path(interpreter).is_file():
        raise RuntimeError('Cover builds require Pillow: install it for Python 3, or set PODCAST_IMAGE_PYTHON to a Python interpreter with Pillow.')
    result = subprocess.run([interpreter, str(root / 'scripts/build_thumbnails.py'), str(root), str(dist)], check=True, capture_output=True, text=True)
    return '/static/' + digest + '/', json.loads(result.stdout)
