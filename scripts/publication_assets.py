"""Reuse an asset only when its bytes match an earlier verified deployment."""
import hashlib, pathlib, subprocess

_diff_cache = {}

def verified_unchanged_asset(root, path, episode_id, previous):
    if not previous or previous.get('status') != 'verified': return False
    if episode_id not in previous.get('verified_episode_ids', []): return False
    sha = previous.get('source_sha')
    if not sha or not path.is_file(): return False
    relative = path.relative_to(root).as_posix()
    if sha not in _diff_cache:
        res = subprocess.run(['git', 'diff', '--name-only', sha, 'HEAD', 'assets/'], cwd=root, capture_output=True, text=True)
        _diff_cache[sha] = set(res.stdout.splitlines()) if res.returncode == 0 else None
    changed = _diff_cache[sha]
    if changed is not None:
        return relative not in changed
    result = subprocess.run(['git', 'show', sha + ':' + relative], cwd=root, capture_output=True)
    return result.returncode == 0 and result.stdout == path.read_bytes()


def validate_static_manifest_path(rel):
    """Validate that an asset-manifest entry stays safely under static/."""
    if not isinstance(rel, str) or '\\' in rel or not rel.startswith('static/') or rel.endswith('/'):
        raise RuntimeError(f'Unsafe static manifest path: {rel!r}')
    parts = pathlib.PurePosixPath(rel).parts
    if '..' in parts or len(parts) < 2:
        raise RuntimeError(f'Unsafe static manifest path: {rel}')


def hash_static_manifest_files(dist_root, files):
    """Return {rel: sha256_hex} for every validated file listed in dist/asset-manifest.json."""
    dist_root = pathlib.Path(dist_root)
    digests = {}
    for rel in files:
        validate_static_manifest_path(rel)
        if rel in digests:
            continue
        path = dist_root / rel
        if not path.is_file():
            raise RuntimeError('Missing local static asset: ' + rel)
        digests[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return digests


def reusable_static_assets(local_hashes, state, previous, full_verify=False):
    """Return static/ paths whose SHA-256 already passed on the latest verified deployment."""
    if full_verify or not previous or previous.get('status') != 'verified':
        return set()
    prev_sha = previous.get('source_sha')
    prev_id = previous.get('deployment_id')
    record = (state or {}).get('verified_static_assets')
    if not prev_sha or not prev_id or not isinstance(record, dict):
        return set()
    if record.get('source_sha') != prev_sha or record.get('deployment_id') != prev_id:
        return set()
    saved_files = record.get('files')
    if not isinstance(saved_files, dict):
        return set()
    return {rel for rel, digest in local_hashes.items() if saved_files.get(rel) == digest}
