"""Image-only delivery manifests, verified local caches and reproducible staging.

The manifest is source-controlled; image bytes may be restored from the published
site by SHA-256. A missing local cache never makes a completed deck pending again.
"""
import ctypes
import functools
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile


def digest(path):
    with pathlib.Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def clone_copy(source, destination):
    """Independent APFS copy-on-write staging; ordinary copies elsewhere."""
    source, destination = pathlib.Path(source), pathlib.Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if sys.platform == 'darwin':
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.clonefile(os.fsencode(source), os.fsencode(destination), 0) == 0:
            return str(destination)
    return shutil.copy2(source, destination)


def validate_deck(eid, deck):
    if not re.fullmatch(r'[a-zA-Z0-9_-]+', eid):
        raise ValueError('Unsafe episode id')
    if not re.fullmatch(r'[a-f0-9]{16}', deck.get('key', '')):
        raise ValueError('Invalid image deck key: ' + eid)
    images = deck.get('images', [])
    if not images or type(deck.get('pages')) is not int or deck['pages'] != len(images):
        raise ValueError('Incomplete image deck: ' + eid)
    for image in images:
        if not re.fullmatch(r'[a-f0-9]{64}', image.get('sha256', '')) or image.get('size', 0) <= 0:
            raise ValueError('Invalid image receipt: ' + eid)
    return deck


@functools.lru_cache(maxsize=8)
def _load_manifest(path, mtime_ns, size):
    data = json.loads(pathlib.Path(path).read_text())
    if data.get('schema_version') != 1:
        raise ValueError('Unsupported slide image manifest')
    decks = data['decks']
    for eid, deck in decks.items():
        validate_deck(eid, deck)
    return decks


def load_decks(root):
    path = pathlib.Path(root) / 'assets/slide-decks.json'
    if not path.exists():
        return {}
    stat = path.stat()
    return _load_manifest(str(path), stat.st_mtime_ns, stat.st_size)


def has_deck(root, eid):
    return eid in load_decks(root)


def save_decks(root, decks):
    for eid, deck in decks.items():
        validate_deck(eid, deck)
    path = pathlib.Path(root) / 'assets/slide-decks.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.json.tmp')
    temporary.write_text(json.dumps({'schema_version': 1, 'decks': decks}, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)
    _load_manifest.cache_clear()


def image_path(root, deck, page):
    return pathlib.Path(root) / 'work/site-slides' / deck['key'] / f'{page}.webp'


def verified_image(path, receipt):
    return path.is_file() and not path.is_symlink() and path.stat().st_size == receipt['size'] and digest(path) == receipt['sha256']


def restore_image(root, deck, page, receipt):
    """Fetch only absent/corrupt cached bytes; fail closed on hash mismatch."""
    from pipeline import network_env
    config = json.loads((pathlib.Path(root) / 'config.json').read_text())
    domain = config['domain'].rstrip('/')
    if not domain.startswith('https://'):
        raise ValueError('Image recovery requires HTTPS')
    url = f"{domain}/static/{deck['key']}/{page}.webp"
    env = network_env()
    path = image_path(root, deck, page)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
        temp_path = pathlib.Path(temporary.name)
        try:
            # Use the same TLS-verified curl transport as publication checks.
            subprocess.run(['curl', '--fail', '--silent', '--show-error', '--location',
                            '--proto', '=https', '--proto-redir', '=https',
                            '--connect-timeout', '15', '--max-time', '60',
                            '--output', str(temp_path), url], env=env, check=True, timeout=65,
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            if not verified_image(temp_path, receipt):
                raise RuntimeError('Recovered image does not match manifest: ' + url)
            temp_path.replace(path)
        finally:
            temp_path.unlink(missing_ok=True)
    return path


def stage_decks(root, dist):
    result = {}
    for eid, deck in load_decks(root).items():
        for page, receipt in enumerate(deck['images'], 1):
            source = image_path(root, deck, page)
            if not verified_image(source, receipt):
                source = restore_image(root, deck, page, receipt)
            clone_copy(source, pathlib.Path(dist) / 'static' / deck['key'] / f'{page}.webp')
        result[eid] = {'prefix': f"/static/{deck['key']}/", 'pages': deck['pages']}
    return result


def remove_verified_pdf_inputs(root, state, legacy=False):
    """Remove only exact PDF inputs whose every output page has an HTTPS receipt.

    Caller owns runner.lock. Missing receipts and changed inputs are preserved.
    Legacy removal is an explicit one-time migration, never a broad directory purge.
    """
    root = pathlib.Path(root)
    receipt = state.get('verified_static_assets', {})
    latest = next((d for d in reversed(state.get('deployments', [])) if d.get('status') == 'verified'), {})
    if not latest or not receipt.get('deployment_id') or any(receipt.get(k) != latest.get(k) for k in ('deployment_id', 'source_sha')):
        return []
    verified = receipt.get('files', {})
    removed = []
    for eid, deck in load_decks(root).items():
        if not all(verified.get(f"static/{deck['key']}/{page}.webp") == image['sha256'] for page, image in enumerate(deck['images'], 1)):
            continue
        candidates = [(root / 'work/slide-inputs' / f'{eid}.pdf', deck.get('input_pdf_sha256'))]
        if legacy:
            candidates += [(root / 'assets/slides' / f'{eid}.pdf', deck.get('source_pdf_sha256')),
                           (root / 'work' / f'{eid}-uncompressed.pdf', deck.get('input_pdf_sha256'))]
        for path, expected in candidates:
            if expected and path.is_file() and not path.is_symlink() and digest(path) == expected:
                removed.append({'path': str(path.relative_to(root)), 'bytes': path.stat().st_size, 'sha256': expected})
                path.unlink()
    return removed
