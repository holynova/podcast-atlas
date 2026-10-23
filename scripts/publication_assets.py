"""Reuse an asset only when its bytes match an earlier verified deployment."""
import subprocess

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
