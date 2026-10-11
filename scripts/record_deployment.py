"""Only mark publication verified after real HTTPS checks pass."""
import argparse, fcntl, hashlib, json, pathlib, subprocess, tempfile
from pipeline import now, write_json, network_env
ROOT = pathlib.Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser(); p.add_argument('--deployment-id', required=True); args = p.parse_args()
config = json.loads((ROOT / 'config.json').read_text()); domain = config['domain']
version = json.loads((ROOT / 'package.json').read_text())['version']
sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
branch = subprocess.check_output(['git', 'branch', '--show-current'], cwd=ROOT, text=True).strip()
if branch != 'main': raise SystemExit('Publication must use main')
env = network_env()
remote_sha = subprocess.check_output(['git','-c','http.version=HTTP/1.1','-c','http.proxy='+env.get('HTTPS_PROXY',''), 'ls-remote', 'origin', 'refs/heads/main'], cwd=ROOT, text=True,env=env).split()[0]
if sha != remote_sha: raise SystemExit('Local main is not the pushed source state')
def get(path, expected=None):
    with tempfile.NamedTemporaryFile(dir=ROOT/'work') as file:
        result = subprocess.run(['curl','-fLsS','--http1.1','--retry','2','--retry-all-errors','--retry-delay','1','--max-time','30','--output',file.name,'--write-out','%{content_type}',domain+path],capture_output=True,text=True,env=env,check=True)
        mime = result.stdout.split(';')[0].strip();data = pathlib.Path(file.name).read_bytes()
        if expected and mime != expected: raise RuntimeError(f'{path}: unexpected content type {mime}')
        return data
if ('v'+version).encode() not in get('/', 'text/html'): raise SystemExit('Live version mismatch')
get('/style.css', 'text/css'); get('/app.js')
verified = []
for file in (ROOT / 'content').glob('*.json'):
    article = json.loads(file.read_text()); eid = file.stem
    if article['headline'].encode() not in get('/episodes/'+eid+'/', 'text/html'): raise RuntimeError('Live article mismatch: '+eid)
    pdf = ROOT / 'assets/slides' / (eid + '.pdf')
    if pdf.exists():
        data = get('/assets/slides/'+eid+'.pdf', 'application/pdf')
        if data[:5] != b'%PDF-' or hashlib.sha256(data).digest() != hashlib.sha256(pdf.read_bytes()).digest(): raise RuntimeError('Live PDF mismatch')
    cover = ROOT / 'assets/illustrations' / eid / '0.webp'
    if cover.exists(): get('/assets/illustrations/'+eid+'/0.webp', 'image/webp')
    verified.append(eid)
with (ROOT / 'state/runner.lock').open('w') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    state = json.loads((ROOT / 'state/progress.json').read_text())
    state['deployments'].append({'at':now(),'source_sha':sha,'version':version,'worker':'podcast-atlas','domain':domain,'deployment_id':args.deployment_id,'verified_episode_ids':verified,'status':'verified'})
    for eid in verified: state['episodes'][eid].update(publication_status='verified', published_sha=sha, published_at=now())
    write_json(ROOT / 'state/progress.json', state)
print(f'Verified {domain}: {len(verified)} articles, v{version}, source {sha}')
