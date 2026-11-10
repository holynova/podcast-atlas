"""Content-addressed public assets; original PDFs and reviewed images stay intact."""
import hashlib, importlib.util, json, os, pathlib, re, subprocess, sys, tempfile


def fingerprint(data):
    return hashlib.sha256(data).hexdigest()[:16]


def minify_css(text):
    text = re.sub(r'/\*[\s\S]*?\*/', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    text = re.sub(r'\s*([{};,])\s*', r'\1', text)
    text = re.sub(r':\s+', ':', text)
    return text.replace(';}', '}')


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


def image_interpreter():
    # Pillow is already used by the project's slide renderer. Use its bundled
    # interpreter when the shell's Python doesn't have it; allow a portable override.
    interpreter = sys.executable
    if not importlib.util.find_spec('PIL'):
        interpreter = os.environ.get('PODCAST_IMAGE_PYTHON', str(pathlib.Path.home() / '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3'))
    if not pathlib.Path(interpreter).is_file():
        raise RuntimeError('Cover builds require Pillow: install it for Python 3, or set PODCAST_IMAGE_PYTHON to a Python interpreter with Pillow.')
    return interpreter


def prepare(root, dist, chapter_sources=None):
    inline_css = minify_css((root / 'style.css').read_text())
    app_bytes = bundle_app_js((root / 'app.js').read_text(), (root / 'search.js').read_text()).encode()
    digest = fingerprint(app_bytes)
    directory = dist / 'static' / digest
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'app.js').write_bytes(app_bytes)

    interpreter = image_interpreter()
    with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as tf:
        tf.write(json.dumps(chapter_sources or [], separators=(',', ':')))
        manifest_file = tf.name
    try:
        thumbs = subprocess.run(
            [interpreter, str(root / 'scripts/build_thumbnails.py'), str(root), str(dist), manifest_file],
            check=True, capture_output=True, text=True
        )
    finally:
        pathlib.Path(manifest_file).unlink(missing_ok=True)
    thumb_data = json.loads(thumbs.stdout)

    slides_res = subprocess.run(
        [interpreter, str(root / 'scripts/build_slides.py'), str(root), str(dist)],
        check=True, capture_output=True, text=True
    )
    slides_data = json.loads(slides_res.stdout)
    return '/static/' + digest + '/', inline_css, thumb_data['covers'], thumb_data['chapters'], slides_data
