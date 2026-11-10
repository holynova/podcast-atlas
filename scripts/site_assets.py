"""Content-addressed public assets; original PDFs and reviewed images stay intact."""
import hashlib, json, pathlib, re, shutil, subprocess, sys

def fingerprint(data):
    return hashlib.sha256(data).hexdigest()[:16]

def minify_css(text):
    text = re.sub(r'/\*[\s\S]*?\*/', '', text)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return '\n'.join(lines)

def bundle_app_js(app_text, search_text):
    search_inline = re.sub(r'\bexport\s+', '', search_text)
    bundled = app_text.replace("import {normalize, searchEntries} from './search.js';", search_inline, 1)
    lines = []
    for line in bundled.splitlines():
        s = line.strip()
        if not s or s.startswith('//'):
            continue
        lines.append(s)
    return '\n'.join(lines)

def write_asset(dist, data, suffix):
    rel = 'static/' + fingerprint(data) + suffix
    target = dist / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return '/' + rel

def prepare(root, dist):
    css_bytes = minify_css((root / 'style.css').read_text()).encode()
    app_bytes = bundle_app_js((root / 'app.js').read_text(), (root / 'search.js').read_text()).encode()
    search_bytes = (root / 'search.js').read_bytes()
    digest = fingerprint(css_bytes + app_bytes + search_bytes)
    directory = dist / 'static' / digest
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'style.css').write_bytes(css_bytes)
    (directory / 'app.js').write_bytes(app_bytes)
    (directory / 'search.js').write_bytes(search_bytes)
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
