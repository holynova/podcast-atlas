"""Only mark publication verified after real HTTPS checks pass."""
import argparse, fcntl, hashlib, json, pathlib, subprocess
from concurrent.futures import ThreadPoolExecutor
from pipeline import now, write_json, network_env
from publication_assets import hash_static_manifest_files, reusable_static_assets, verified_unchanged_asset
from https_batch import HttpsBatch

ROOT = pathlib.Path(__file__).resolve().parents[1]


def verify_and_record(root, deployment_id, full_verify=False, topic_groups=None, topic_url_fn=None):
    """Fetch and verify live deployment assets, reusing verified unchanged assets."""
    root = pathlib.Path(root)
    config = json.loads((root / 'config.json').read_text())
    domain = config['domain']
    version = json.loads((root / 'package.json').read_text())['version']
    previous_state = json.loads((root / 'state/progress.json').read_text())
    previous = next((d for d in reversed(previous_state.get('deployments', [])) if d.get('status') == 'verified'), None)

    sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    branch = subprocess.check_output(['git', 'branch', '--show-current'], cwd=root, text=True).strip()
    if branch != 'main':
        raise SystemExit('Publication must use main')
    env = network_env()
    remote_sha = subprocess.check_output(
        ['git', '-c', 'http.version=HTTP/1.1', '-c', 'http.proxy=' + env.get('HTTPS_PROXY', ''), 'ls-remote', 'origin', 'refs/heads/main'],
        cwd=root,
        text=True,
        env=env,
    ).split()[0]
    if sha != remote_sha:
        raise SystemExit('Local main is not the pushed source state')

    if topic_groups is None or topic_url_fn is None:
        from build import TOPIC_GROUPS, topic_url
        topic_groups = TOPIC_GROUPS if topic_groups is None else topic_groups
        topic_url_fn = topic_url if topic_url_fn is None else topic_url_fn

    paths = ['/', '/style.css', '/app.js', '/search.js', '/search-index.json', '/topics/']
    paths += [topic_url_fn(topic, show) for show, topic in topic_groups]

    manifest_path = root / 'dist/asset-manifest.json'
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        static_hashes = hash_static_manifest_files(root / 'dist', manifest['files'])
        reused_static = reusable_static_assets(static_hashes, previous_state, previous, full_verify=full_verify)
        pending_static = [rel for rel in static_hashes if rel not in reused_static]
        paths.append('/asset-manifest.json')
        paths += ['/' + rel for rel in pending_static]
    else:
        manifest = None
        static_hashes = {}
        reused_static = set()
        pending_static = []

    content_files = sorted((root / 'content').glob('*.json'))
    for file in content_files:
        eid = file.stem
        paths.append('/episodes/' + eid + '/')
        candidates = [root / 'assets/slides' / (eid + '.pdf'), *sorted((root / 'assets/illustrations' / eid).glob('*.webp'))]
        for asset in candidates:
            if asset.exists() and (full_verify or not verified_unchanged_asset(root, asset, eid, previous)):
                paths.append('/' + asset.relative_to(root).as_posix())

    def url_for(path):
        return domain + path + ('?verify=' + sha if path.endswith('.pdf') else '')

    transport = HttpsBatch(root / 'work', env)
    transport.fetch([url_for(path) for path in paths])

    def get(path, expected=None):
        data, mime = transport.get(url_for(path))
        if expected and mime not in ([expected] if isinstance(expected, str) else expected):
            raise RuntimeError(f'{path}: unexpected content type {mime}')
        return data

    if ('v' + version).encode() not in get('/', 'text/html'):
        raise SystemExit('Live version mismatch')
    if get('/style.css', 'text/css') != (root / 'style.css').read_bytes():
        raise RuntimeError('Live CSS mismatch')
    for module in ['app.js', 'search.js']:
        if get('/' + module, ['text/javascript', 'application/javascript']) != (root / module).read_bytes():
            raise RuntimeError('Live script mismatch: ' + module)
    index = json.loads(get('/search-index.json', 'application/json'))
    local_index = json.loads((root / 'dist/search-index.json').read_text())
    if index != local_index or index['version'] != version:
        raise RuntimeError('Live search index mismatch')

    # New content-addressed scripts, search shards and cover variants are the files
    # browsers actually use; checking legacy root aliases alone cannot verify them.
    if manifest is not None:
        if json.loads(get('/asset-manifest.json', 'application/json')) != manifest:
            raise RuntimeError('Live asset manifest mismatch')
        def check_static(rel):
            if hashlib.sha256(get('/' + rel)).hexdigest() != static_hashes[rel]:
                raise RuntimeError('Live static asset mismatch: ' + rel)
        if pending_static:
            with ThreadPoolExecutor(max_workers=3) as pool:
                list(pool.map(check_static, pending_static))
        print(
            f'HTTPS verified: {len(static_hashes)} fingerprinted assets ({len(pending_static)} fetched, {len(reused_static)} reused)',
            flush=True,
        )

    if '半拿铁'.encode() not in get('/topics/', 'text/html') or '知行小酒馆'.encode() not in get('/topics/', 'text/html'):
        raise RuntimeError('Live topic groups missing')

    def check_topic(group):
        show, topic = group
        page = get(topic_url_fn(topic, show), 'text/html')
        if (show + ' / ').encode() not in page or topic.encode() not in page:
            raise RuntimeError('Live show topic mismatch')

    def check_article(file):
        reused = []
        article = json.loads(file.read_text())
        eid = file.stem
        if article['headline'].encode() not in get('/episodes/' + eid + '/', 'text/html'):
            raise RuntimeError('Live article mismatch: ' + eid)
        pdf = root / 'assets/slides' / (eid + '.pdf')
        if pdf.exists():
            if not full_verify and verified_unchanged_asset(root, pdf, eid, previous):
                reused.append(pdf.relative_to(root).as_posix())
            else:
                data = get('/assets/slides/' + eid + '.pdf', 'application/pdf')
                if data[:5] != b'%PDF-' or hashlib.sha256(data).digest() != hashlib.sha256(pdf.read_bytes()).digest():
                    raise RuntimeError('Live PDF mismatch')
        for image in sorted((root / 'assets/illustrations' / eid).glob('*.webp')):
            if not full_verify and verified_unchanged_asset(root, image, eid, previous):
                reused.append(image.relative_to(root).as_posix())
            else:
                data = get('/assets/illustrations/' + eid + '/' + image.name, 'image/webp')
                if hashlib.sha256(data).digest() != hashlib.sha256(image.read_bytes()).digest():
                    raise RuntimeError('Live illustration mismatch: ' + eid + '/' + image.name)
        return eid, reused

    verified = []
    reused_assets = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(check_topic, topic_groups))
        for eid, reused in pool.map(check_article, content_files):
            verified.append(eid)
            reused_assets.extend(reused)
            if len(verified) % 10 == 0:
                print(f'HTTPS verified: {len(verified)} articles', flush=True)

    with (root / 'state/runner.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = json.loads((root / 'state/progress.json').read_text())
        verified_at = now()
        state['deployments'].append({
            'at': verified_at,
            'source_sha': sha,
            'version': version,
            'worker': 'podcast-atlas',
            'domain': domain,
            'deployment_id': deployment_id,
            'verified_episode_ids': verified,
            'status': 'verified',
            'reused_verified_assets': reused_assets,
            'reused_static_asset_count': len(reused_static),
            'verified_static_asset_count': len(static_hashes),
            'asset_verification_base_sha': previous.get('source_sha') if previous else None,
            'static_verification_base_deployment_id': previous.get('deployment_id') if reused_static else None,
        })
        if manifest is not None:
            state['verified_static_assets'] = {
                'deployment_id': deployment_id,
                'source_sha': sha,
                'at': verified_at,
                'files': static_hashes,
            }
        episodes = state.setdefault('episodes', {})
        for eid in verified:
            episodes.setdefault(eid, {}).update(publication_status='verified', published_sha=sha, published_at=verified_at)
        write_json(root / 'state/progress.json', state)

    print(f'Verified {domain}: {len(verified)} articles, v{version}, source {sha}')
    return {
        'verified_episodes': len(verified),
        'static_total': len(static_hashes),
        'static_fetched': len(pending_static),
        'static_reused': len(reused_static),
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--deployment-id', required=True)
    parser.add_argument('--full-verify', action='store_true', help='Re-fetch and verify all static/ and episode assets over HTTPS.')
    args = parser.parse_args(argv)
    verify_and_record(ROOT, args.deployment_id, full_verify=args.full_verify)


if __name__ == '__main__':
    main()
