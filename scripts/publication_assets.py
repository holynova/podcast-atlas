"""Reuse an asset only when its bytes match an earlier verified deployment."""
import subprocess

def verified_unchanged_asset(root, path, episode_id, previous):
    if not previous or previous.get('status') != 'verified': return False
    if episode_id not in previous.get('verified_episode_ids', []): return False
    sha = previous.get('source_sha')
    if not sha or not path.is_file(): return False
    relative = path.relative_to(root).as_posix()
    result = subprocess.run(['git', 'show', sha + ':' + relative], cwd=root, capture_output=True)
    return result.returncode == 0 and result.stdout == path.read_bytes()
