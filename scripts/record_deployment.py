"""Only mark publication verified after real HTTPS checks pass."""
import argparse, fcntl, hashlib, json, pathlib, subprocess, tempfile
from concurrent.futures import ThreadPoolExecutor
from pipeline import now, write_json, network_env
from publication_assets import verified_unchanged_asset
ROOT = pathlib.Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser(); p.add_argument('--deployment-id', required=True); args = p.parse_args()
config = json.loads((ROOT / 'config.json').read_text()); domain = config['domain']
version = json.loads((ROOT / 'package.json').read_text())['version']
previous_state = json.loads((ROOT / 'state/progress.json').read_text())
previous = next((d for d in reversed(previous_state.get('deployments', [])) if d.get('status') == 'verified'), None)
reused_assets = []
sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
branch = subprocess.check_output(['git', 'branch', '--show-current'], cwd=ROOT, text=True).strip()
if branch != 'main': raise SystemExit('Publication must use main')
env = network_env()
remote_sha = subprocess.check_output(['git','-c','http.version=HTTP/1.1','-c','http.proxy='+env.get('HTTPS_PROXY',''), 'ls-remote', 'origin', 'refs/heads/main'], cwd=ROOT, text=True,env=env).split()[0]
if sha != remote_sha: raise SystemExit('Local main is not the pushed source state')
def get(path, expected=None):
    with tempfile.NamedTemporaryFile(dir=ROOT/'work') as file:
        timeout = '600' if path.endswith('.pdf') else '90'
        protocol = '--http2'
        url = domain + path + ('?verify=' + sha if path.endswith('.pdf') else '')
        result = subprocess.run(['curl','-fLsS','--compressed',protocol,'--retry','2','--retry-all-errors','--retry-delay','1','--max-time',timeout,'--output',file.name,'--write-out','%{content_type}',url],capture_output=True,text=True,env=env,check=True)
        mime = result.stdout.split(';')[0].strip();data = pathlib.Path(file.name).read_bytes()
        if expected and mime not in ([expected] if isinstance(expected,str) else expected): raise RuntimeError(f'{path}: unexpected content type {mime}')
        return data
if ('v'+version).encode() not in get('/', 'text/html'): raise SystemExit('Live version mismatch')
if get('/style.css','text/css') != (ROOT/'style.css').read_bytes():raise RuntimeError('Live CSS mismatch')
for module in ['app.js','search.js']:
    if get('/'+module,['text/javascript','application/javascript']) != (ROOT/module).read_bytes():raise RuntimeError('Live script mismatch: '+module)
index=json.loads(get('/search-index.json','application/json'))
local_index=json.loads((ROOT/'dist/search-index.json').read_text())
if index != local_index or index['version'] != version:raise RuntimeError('Live search index mismatch')
if '半拿铁'.encode() not in get('/topics/','text/html') or '知行小酒馆'.encode() not in get('/topics/','text/html'):raise RuntimeError('Live topic groups missing')
from build import TOPIC_GROUPS,topic_url
def check_topic(group):
    show,topic = group
    page=get(topic_url(topic,show),'text/html')
    if (show+' / ').encode() not in page or topic.encode() not in page:raise RuntimeError('Live show topic mismatch')
verified = []
def check_article(file):
    reused = []
    article = json.loads(file.read_text()); eid = file.stem
    if article['headline'].encode() not in get('/episodes/'+eid+'/', 'text/html'): raise RuntimeError('Live article mismatch: '+eid)
    pdf = ROOT / 'assets/slides' / (eid + '.pdf')
    if pdf.exists():
        if verified_unchanged_asset(ROOT, pdf, eid, previous):
            reused.append(pdf.relative_to(ROOT).as_posix())
        else:
            data = get('/assets/slides/'+eid+'.pdf', 'application/pdf')
            if data[:5] != b'%PDF-' or hashlib.sha256(data).digest() != hashlib.sha256(pdf.read_bytes()).digest(): raise RuntimeError('Live PDF mismatch')
    for image in sorted((ROOT / 'assets/illustrations' / eid).glob('*.webp')):
        if verified_unchanged_asset(ROOT, image, eid, previous):
            reused.append(image.relative_to(ROOT).as_posix())
        else:
            data = get('/assets/illustrations/'+eid+'/'+image.name, 'image/webp')
            if hashlib.sha256(data).digest() != hashlib.sha256(image.read_bytes()).digest(): raise RuntimeError('Live illustration mismatch: '+eid+'/'+image.name)
    return eid, reused
with ThreadPoolExecutor(max_workers=3) as pool:
    list(pool.map(check_topic, TOPIC_GROUPS))
    for eid, reused in pool.map(check_article, (ROOT / 'content').glob('*.json')):
        verified.append(eid)
        reused_assets.extend(reused)
        if len(verified) % 10 == 0: print(f'HTTPS verified: {len(verified)} articles', flush=True)
with (ROOT / 'state/runner.lock').open('w') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    state = json.loads((ROOT / 'state/progress.json').read_text())
    state['deployments'].append({'at':now(),'source_sha':sha,'version':version,'worker':'podcast-atlas','domain':domain,'deployment_id':args.deployment_id,'verified_episode_ids':verified,'status':'verified','reused_verified_assets':reused_assets,'asset_verification_base_sha':previous.get('source_sha') if previous else None})
    for eid in verified: state['episodes'][eid].update(publication_status='verified', published_sha=sha, published_at=now())
    write_json(ROOT / 'state/progress.json', state)
print(f'Verified {domain}: {len(verified)} articles, v{version}, source {sha}')
