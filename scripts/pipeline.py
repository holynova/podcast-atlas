#!/usr/bin/env python3
"""Resumable NotebookLM production. Raw transcripts only enter ignored work/."""
import argparse, datetime as dt, fcntl, hashlib, json, os, pathlib, re, subprocess, sys, time
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / 'config.json').read_text())
STATE_FILE = ROOT / 'state/progress.json'
TZ = ZoneInfo(CONFIG['timezone'])

def now(): return dt.datetime.now(TZ).isoformat(timespec='seconds')
def network_env():
    env = os.environ.copy()
    env['NLM_PROFILE'] = CONFIG.get('notebooklm_profile','default')
    if not any(env.get(k) for k in ['HTTP_PROXY','HTTPS_PROXY','http_proxy','https_proxy']):
        try:
            settings = subprocess.run(['scutil','--proxy'],capture_output=True,text=True,timeout=5).stdout
            if re.search(r'HTTPSEnable\s*:\s*1',settings):
                host = re.search(r'HTTPSProxy\s*:\s*(\S+)',settings)
                port = re.search(r'HTTPSPort\s*:\s*(\d+)',settings)
                if host and port: env.update(HTTPS_PROXY='http://'+host[1]+':'+port[1], HTTP_PROXY='http://'+host[1]+':'+port[1])
        except (FileNotFoundError,subprocess.TimeoutExpired): pass
    return env

def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    os.replace(temp, path)

def catalog():
    out = []
    for show in ['半拿铁', '知行小酒馆']:
        base = pathlib.Path(CONFIG['source_root']) / show
        for x in json.loads((base / 'manifest.json').read_text()):
            title = x['title']; topic = '单集精选'; number = None; rank = 100
            rules = [(r'中国互联网故事\s*(\d+)', '中国互联网故事', 0),
                     (r'苹果简史\s*(\d+)', '苹果公司简史', 1),
                     (r'中国股市', '中国股市往事', 2),
                     (r'硅谷神话', '硅谷神话', 3),
                     (r'芯片江湖', '芯片江湖', 4),
                     (r'任天堂往事\s*[（(]?(\d+)', '任天堂往事', 5),
                     (r'日漫史\s*(\d+)', '日本漫画史', 6),
                     (r'中国饮料故事', '中国饮料故事', 7),
                     (r'房产万事屋\s*(\d+)', '房产万事屋', 8),
                     (r'我们和养老的距离\s*(\d+)', '我们和养老的距离', 9),
                     (r'科龙往事', '科龙往事', 10)]
            for pattern, label, priority in rules:
                m = re.search(pattern, title)
                if m:
                    topic, rank = label, priority
                    number = int(m.group(1)) if m.lastindex else None
                    break
            number = number or (int(re.search(r'(?:No\.|E)\s*(\d+)', title)[1]) if re.search(r'(?:No\.|E)\s*(\d+)', title) else 10000)
            text = base / x.get('text_file', '__missing__')
            raw = base / x.get('json_file', '__missing__')
            out.append({'id': x['eid'], 'title': title, 'show': show, 'date': x['date'][:10],
                        'url': x['url'], 'topic': topic, 'order': number, 'rank': rank,
                        'available': x['status'] == 'success' and text.is_file() and raw.is_file(),
                        'text_path': str(text), 'json_path': str(raw), 'duration': x.get('duration', 0)})
    out.sort(key=lambda x: (x['rank'], 0 if x['rank'] == 2 and x['show'] == '半拿铁' else 1 if x['rank'] == 2 else 0, x['order'] if x['rank'] < 100 else -dt.date.fromisoformat(x['date']).toordinal(), x['id']))
    return out

class GenerationFailed(RuntimeError):
    pass

class GenerationDeferred(RuntimeError):
    pass

_LAST_REQUEST = None

def paced_sleep(seconds):
    while seconds > 0:
        pause = min(seconds, 30); time.sleep(pause); seconds -= pause

def pause_generation(state, reason, until=None):
    until = until or (dt.datetime.now(TZ) + dt.timedelta(seconds=CONFIG.get('failure_cooldown_seconds',18000))).isoformat(timespec='seconds')
    previous = state.get('generation_cooldown_until')
    state['generation_cooldown_until'] = max(previous or until, until)
    state['generation_pause_reason'] = reason
    write_json(STATE_FILE, state)

def generation_gate(state, ep=None):
    watch = state.get('manual_retry_watch', {})
    if watch.get('check_not_before') and not watch.get('checked_at'):
        raise GenerationDeferred('User manually retried this notebook; reconcile its results before submitting another.')
    if state.get('diagnostic_inflight'):
        raise GenerationDeferred('A bounded diagnostic generation is pending; reconcile it first.')
    until = state.get('generation_cooldown_until')
    if until and dt.datetime.fromisoformat(until) > dt.datetime.now(TZ):
        raise GenerationDeferred('Generation paused until ' + until)
    if ep:
        r = state.get('episodes', {}).get(ep['id'], {})
        next_attempt = r.get('next_slide_attempt_at')
        if next_attempt and dt.datetime.fromisoformat(next_attempt) > dt.datetime.now(TZ):
            raise GenerationDeferred(f"Episode {ep['id']} is in retry backoff until {next_attempt}")
    active_in_flight = sum(1 for r in state.get('episodes', {}).values() if r.get('slide_status') in ['queued','submitting'])
    max_in_flight = CONFIG.get('max_concurrent_slides_per_account', 10)
    if active_in_flight >= max_in_flight:
        raise GenerationDeferred(f'Reached maximum concurrent in-flight generations ({max_in_flight}); collect some before submitting more.')
    last = state.get('last_slide_submission_at')
    interval = CONFIG.get('generation_interval_seconds', 60)
    if last and (dt.datetime.now(TZ)-dt.datetime.fromisoformat(last)).total_seconds() < interval:
        raise GenerationDeferred(f'Waiting for the {interval}-second submission interval.')

def generation_waiting(r):
    """Allow a newly submitted deck its initial generation window before polling."""
    submitted = r.get('slide_submitted_at')
    return bool(submitted and r.get('slide_status') in ['queued','submitting'] and
                (dt.datetime.now(TZ)-dt.datetime.fromisoformat(submitted)).total_seconds()
                < CONFIG.get('generation_initial_wait_seconds',1200))

def notebook_check_due(state, nb):
    watch = state.get('manual_retry_watch', {})
    if watch.get('notebook_id') == nb and watch.get('check_not_before') and not watch.get('checked_at'):
        if dt.datetime.fromisoformat(watch['check_not_before']) > dt.datetime.now(TZ): return False
    diagnostic = state.get('diagnostic_inflight')
    if diagnostic and diagnostic.get('notebook_id') == nb:
        elapsed = (dt.datetime.now(TZ)-dt.datetime.fromisoformat(diagnostic['submitted_at'])).total_seconds()
        if elapsed < CONFIG.get('generation_initial_wait_seconds',1200): return False
    unfinished = [r for r in state['episodes'].values()
                  if r.get('notebook_id') == nb and r.get('status') != 'complete']
    return not any(generation_waiting(r) for r in unfinished)

def cooldown_outlasts_budget(state, deadline):
    until = state.get('generation_cooldown_until')
    if not until: return False
    remaining = (dt.datetime.fromisoformat(until)-dt.datetime.now(TZ)).total_seconds()
    return remaining > 0 and remaining >= max(0,deadline-time.monotonic())

def pace_request():
    global _LAST_REQUEST
    if _LAST_REQUEST is not None:
        paced_sleep(max(0, CONFIG.get('request_interval_seconds',15) - (time.monotonic()-_LAST_REQUEST)))
    _LAST_REQUEST = time.monotonic()

def cli(*args, timeout=300):
    pace_request()
    env = network_env()
    env['NOTEBOOKLM_RATE_LIMIT_MAX_RETRIES'] = '0'
    binary = pathlib.Path(os.environ.get('NLM_BIN', '/Users/sym/.local/bin/nlm'))
    command = [str(binary)]
    if len(args) > 1 and (args[0], args[1]) in [('slides', 'create'), ('studio', 'retry'), ('studio','failure-info'), ('notebook', 'create'), ('source', 'add')]:
        interpreter = binary.read_text().splitlines()[0].removeprefix('#!')
        command = [interpreter, str(ROOT / 'scripts/nlm_once.py')]
    p = subprocess.run([*command, *args], capture_output=True, text=True, timeout=timeout, env=env)
    if p.returncode: raise RuntimeError((p.stderr or p.stdout)[-1800:])
    s = p.stdout.strip()
    try: return json.loads(s)
    except json.JSONDecodeError:
        starts = [m.start() for m in re.finditer(r'[\[{]', s)]
        for start in starts:
            try: return json.JSONDecoder().raw_decode(s[start:])[0]
            except json.JSONDecodeError: pass
        raise RuntimeError('CLI did not return JSON: ' + s[:700])

SLIDE_FOCUS = '用简体中文制作详细学习幻灯片，讲清本集背景、人物、主要事件、时间线和因果。采用《丁丁历险记》漫画风格：黑色轮廓、鲜明平涂色块、时代场景与中文旁白。依据所选逐字稿，不虚构人名、数字或引语。'
ARTICLE_PROMPT = '''仅根据选中的一集带时间戳逐字稿，把它改写成适合普通人阅读的详细中文图文讲解。语言说人话，短句，解释术语，保留关键背景、故事、机制和因果。不包含广告、片头混剪或无关闲聊。谨慎修正明确的识别错字，不确定人物/日期/金额不猜，不写原文不存在的事实。不长篇复制原话，尽量用自己的话重述。输出一个可由json.loads解析的JSON对象，不用Markdown围栏或额外解释，不插入[1]等引用符号。每个主要章节给出逐字稿中真实存在的时间戳，格式MM:SS，超过一小时可用HH:MM:SS。目标2000—3500汉字。像朋友把故事讲给你听，避免“基石、闭环、赋能、登顶、阵痛、体制藩篱、资本狂人、争霸、霸主、苟延残喘”等夸饰词，不用报纸式套话，讲机制而不是给人物下道德判词。标题20字左右，不使用“从X到Y：XX的崛起与沉沦”模板。解释术语再使用它，节目有不同说法时注明，不当成定论。结构：
{"headline":"通俗有吸引力的标题，20字左右", "dek":"80—140字导读", "takeaways":["3—5条各40—80字的核心认识"], "sections":[{"title":"章节名", "paragraphs":["2—3段，每段100—180字"], "timestamp":"对应原文时间"}], "timeline":[{"date":"原文明确的年份或时期，不确定则写阶段", "title":"事件", "detail":"具体发生什么以及意义，50—100字"}], "people":[{"name":"人物或组织", "role":"身份", "detail":"在故事中的作用，40—80字"}], "connections":[{"from":"people中已有名字", "to":"people中已有名字", "label":"原文明确支持的关系或影响"}], "mechanism":{"title":"一个最重要的因果链", "steps":[{"label":"阶段", "detail":"为什么导致下一个阶段，40—80字"}]}, "glossary":[{"term":"3—6个术语", "meaning":"用生活例子解释"}], "caveats":["原文的局限或尚不确定的地方，不泛泛而谈"]}。
sections至少6个、timeline至少5项、people至少4项、connections至少3项、mechanism.steps至少3项。忠实优先，素材不足可以缩短并在caveats说明。'''

def validate_article(d):
    for key in ['headline', 'dek', 'takeaways', 'sections', 'timeline', 'people', 'connections', 'mechanism', 'glossary', 'caveats']:
        if key not in d: raise ValueError('Missing article field: ' + key)
    if len(d['sections']) < 4 or len(d['timeline']) < 3 or len(d['people']) < 3: raise ValueError('Article too thin')
    for s in d['sections']:
        if not s.get('title') or not s.get('paragraphs') or not re.fullmatch(r'\d{1,3}:\d{2}(?::\d{2})?', s.get('timestamp', '')): raise ValueError('Invalid chapter or timestamp')
    names = {p['name'] for p in d['people']}
    if any(c['from'] not in names or c['to'] not in names for c in d['connections']): raise ValueError('Unknown connection endpoint')
    return d

def answer_json(result):
    if isinstance(result, dict):
        if 'headline' in result: return result
        for key in ['answer', 'response', 'text']:
            if key in result:
                if isinstance(result[key], str):
                    s = result[key].strip(); start = s.find('{')
                    if start >= 0: return json.JSONDecoder().raw_decode(s[start:])[0]
                elif isinstance(result[key], dict): return answer_json(result[key])
        for v in result.values():
            if isinstance(v, dict):
                try: return answer_json(v)
                except (ValueError, json.JSONDecodeError): pass
    raise ValueError('No JSON article in query response')

def get_artifacts(nb):
    result = cli('studio', 'status', nb, '--json')
    if isinstance(result, list): return result
    return result.get('artifacts', result.get('data', []))

def mark_error(state, eid, stage, error):
    r = state['episodes'][eid]; r.setdefault('errors', []).append({'at': now(), 'stage': stage, 'message': str(error)[:2000]})
    r.setdefault('attempts', {})[stage] = r.get('attempts', {}).get(stage, 0) + 1
    r['last_error'] = {'at': now(), 'stage': stage, 'message': str(error)[:1000]}
    write_json(STATE_FILE, state)
    print('ERROR', eid, stage, str(error)[:250], flush=True)

def remaining_attempts(record, stage): return record.get('attempts', {}).get(stage, 0) < CONFIG['max_attempts']

def prepare_source(state, ep):
    r = state['episodes'].setdefault(ep['id'], {})
    if r.get('source_id'): return
    # At most 50 standalone episodes per notebook; topics stay together.
    key = ep['topic'] if ep['rank'] < 100 else ep['show'] + '｜单集组' + str(ep.get('standalone_group', 1))
    if key not in state['notebooks']:
        notebooks = cli('notebook', 'list', '--json')
        items = notebooks if isinstance(notebooks, list) else notebooks.get('notebooks', [])
        title = '播客图解｜' + key
        found = next((n for n in items if n.get('title') == title), None)
        if not found:
            state.setdefault('pending_notebook', {})[key] = now(); write_json(STATE_FILE, state)
            found = cli('notebook', 'create', title, '--json')
        state['notebooks'][key] = found.get('notebook_id', found.get('id'))
        if not state['notebooks'][key]: raise ValueError('Missing notebook ID')
        state.get('pending_notebook', {}).pop(key, None); write_json(STATE_FILE, state)
    nb = state['notebooks'][key]; r['notebook_id'] = nb
    title = ep['id'] + '｜' + ep['title']
    sources = cli('source', 'list', nb, '--json')
    items = sources if isinstance(sources, list) else sources.get('sources', [])
    found = next((s for s in items if s.get('title', '').startswith(ep['id'] + '｜')), None)
    if not found:
        segments = json.loads(pathlib.Path(ep['json_path']).read_text())
        text = f"节目：{ep['show']}\n单集：{ep['title']}\n发布日期：{ep['date']}\n原节目：{ep['url']}\n以下仅是这一集逐字稿，含语音识别误差。不要把片头混剪当本集故事，也不要猜测不存在的集号。\n\n" + '\n'.join(f"[{s['startMs']//3600000:02d}:{s['startMs']//60000%60:02d}:{s['startMs']//1000%60:02d}] {s['text']}" for s in segments)
        source = ROOT / 'work' / (ep['id'] + '.txt'); source.write_text(text)
        r['source_sha256'] = hashlib.sha256(text.encode()).hexdigest()
        r['source_status'] = 'uploading'; write_json(STATE_FILE, state)
        found = cli('source', 'add', nb, '--file', str(source), '--title', title, '--wait', '--json', timeout=660)
    r['source_id'] = found.get('source_id', found.get('id'))
    if not r['source_id']: raise ValueError('Missing source ID')
    r['source_status'] = 'ready'; r['updated_at'] = now(); write_json(STATE_FILE, state)

def start_slides(state, ep, artifacts=None):
    r = state['episodes'][ep['id']]
    if r.get('slide_status') in ['failed', 'retry_pending']:
        if r.get('artifact_id'):
            r.setdefault('failed_artifact_ids', []).append(r['artifact_id'])
            r['failed_artifact_ids'] = sorted(set(r['failed_artifact_ids']))
            r.pop('artifact_id', None)
        r['slide_status'] = 'retry_pending'
        write_json(STATE_FILE, state)
    if r.get('artifact_id'): return
    # Recover an ambiguous create before any retry: each focus contains a unique episode marker.
    if artifacts is None: artifacts = get_artifacts(r['notebook_id'])
    related = [a for a in artifacts if (ep['id'] in json.dumps(a, ensure_ascii=False) or r.get('source_id') in a.get('source_ids', [])) and a.get('id',a.get('artifact_id')) not in state.get('diagnostic_artifact_ids',[])]
    failed_ids = set(r.get('failed_artifact_ids', []))
    failed_ids.update(a.get('id', a.get('artifact_id')) for a in related if str(a.get('status', '')).lower() in ['failed', 'error', '4'])
    failed_ids.difference_update(a.get('id',a.get('artifact_id')) for a in related if str(a.get('status', '')).lower() in ['completed', '3'])
    r['failed_artifact_ids'] = sorted(failed_ids - {None})
    matches = [a for a in related if a.get('id', a.get('artifact_id')) not in failed_ids]
    if matches:
        candidates = sorted(matches, key=lambda a: 0 if str(a.get('status', '')).lower() in ['completed', '3'] else 1 if str(a.get('status', '')).lower() not in ['failed', 'error', '4'] else 2)
        a = candidates[0]; r['artifact_id'] = a.get('artifact_id', a.get('id'))
        r['all_artifact_ids'] = [x.get('artifact_id', x.get('id')) for x in matches]
    elif r.get('slide_status') == 'submitting':
        raise RuntimeError('Slide submission outcome uncertain. Inspect NotebookLM before re-submitting to avoid duplicates.')
    else:
        generation_gate(state, ep=ep)
        state['last_slide_submission_at'] = now()
        r['slide_submitted_at'] = state['last_slide_submission_at']
        r['slide_status'] = 'submitting'; write_json(STATE_FILE, state)
        try:
            a = cli('slides', 'create', r['notebook_id'], '--source-ids', r['source_id'], '--format', 'detailed_deck', '--language', 'zh-CN', '--focus', f"标识 {ep['id']}。{SLIDE_FOCUS}", '--confirm', '--json')
        except RuntimeError as error:
            if 'Rate limited' in str(error) or 'RESOURCE_EXHAUSTED' in str(error) or '429' in str(error):
                r['slide_status'] = 'rate_limited'
                if 'Wait 1-2 minutes' in str(error) or 'Wait a few minutes' in str(error):
                    cooldown = CONFIG.get('rate_limit_throttle_seconds', 180)
                    until = (dt.datetime.now(TZ) + dt.timedelta(seconds=cooldown)).isoformat(timespec='seconds')
                    pause_generation(state, 'NotebookLM frequency limit (wait a few minutes)', until)
                else:
                    pause_generation(state, 'NotebookLM explicitly rate limited slide creation')
                r['next_slide_attempt_at'] = state['generation_cooldown_until']
                write_json(STATE_FILE, state)
            raise
        r['artifact_id'] = a['artifact_id']
        r.setdefault('all_artifact_ids', []).append(a['artifact_id'])
    r['slide_status'] = 'queued'; r['updated_at'] = now(); write_json(STATE_FILE, state)

def make_article(state, ep):
    path = ROOT / 'content' / (ep['id'] + '.json'); r = state['episodes'][ep['id']]
    if path.exists(): validate_article(json.loads(path.read_text())); r['article_status'] = 'ready'; return
    response = cli('notebook', 'query', r['notebook_id'], ARTICLE_PROMPT, '--source-ids', r['source_id'], '--new-conversation', '--timeout', '240', '--json', timeout=300)
    write_json(ROOT / 'work' / (ep['id'] + '-query.json'), response)
    article = validate_article(answer_json(response))
    article['source'] = {k: ep[k] for k in ['id', 'title', 'show', 'date', 'url', 'topic', 'order']}
    article['generated_at'] = now(); write_json(path, article)
    r['article_status'] = 'ready'; r['updated_at'] = now(); write_json(STATE_FILE, state)

def collect_slides(state, ep, artifacts=None):
    r = state['episodes'][ep['id']]
    if generation_waiting(r): return False
    if artifacts is not None:
        matches = [a for a in artifacts if (ep['id'] in json.dumps(a, ensure_ascii=False) or r.get('source_id') in a.get('source_ids', [])) and a.get('id',a.get('artifact_id')) not in state.get('diagnostic_artifact_ids',[])]
        if matches:
            r['all_artifact_ids'] = [a.get('artifact_id', a.get('id')) for a in matches]
            completed = next((a for a in matches if str(a.get('status', '')).lower() in ['completed', '3']), None)
            if completed or not r.get('artifact_id'):
                a = completed or next((a for a in matches if str(a.get('status', '')).lower() not in ['failed', 'error', '4']), matches[0])
                r['artifact_id'] = a.get('artifact_id', a.get('id'))
    if not r.get('artifact_id'): return False
    target = ROOT / 'assets/slides' / (ep['id'] + '.pdf')
    if target.exists():
        if not (ROOT / 'assets/illustrations' / ep['id'] / '0.webp').exists():
            runtime = '/Users/sym/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3'
            subprocess.run([runtime, str(ROOT / 'scripts/optimize_slides.py'), str(target)], check=True, timeout=180)
            subprocess.run([runtime, str(ROOT / 'scripts/render_slides.py'), str(target)], check=True, timeout=180)
        r['slide_status'] = 'downloaded'; r['pdf'] = 'assets/slides/' + target.name; return True
    if artifacts is None: artifacts = get_artifacts(r['notebook_id'])
    a = next((a for a in artifacts if a.get('id', a.get('artifact_id')) == r['artifact_id']), None)
    if not a: raise ValueError('Tracked artifact missing')
    status = str(a.get('status', '')).lower(); r['slide_remote_status'] = status
    if status in ['failed', 'error', '4']:
        if r['artifact_id'] in r.get('failed_artifact_ids', []):
            # A historical failure is not a new attempt and must not restart cooldown.
            r.pop('artifact_id', None); r['slide_status'] = 'retry_pending'
            write_json(STATE_FILE, state)
            return False
        alternatives = [x for x in artifacts if (ep['id'] in json.dumps(x, ensure_ascii=False) or r.get('source_id') in x.get('source_ids', [])) and str(x.get('status', '')).lower() not in ['failed', 'error', '4'] and x.get('id',x.get('artifact_id')) not in state.get('diagnostic_artifact_ids',[])]
        if alternatives:
            best = next((x for x in alternatives if str(x.get('status', '')).lower() in ['completed', '3']), alternatives[0])
            r['artifact_id'] = best.get('artifact_id', best.get('id')); write_json(STATE_FILE, state); return False
        r['slide_status'] = 'failed'
        r.setdefault('failed_artifact_ids', []).append(r['artifact_id'])
        r['failed_artifact_ids'] = sorted(set(r['failed_artifact_ids']))
        retry_delay = CONFIG.get('single_episode_retry_interval_seconds', 60)
        until = (dt.datetime.now(TZ) + dt.timedelta(seconds=retry_delay)).isoformat(timespec='seconds')
        r['next_slide_attempt_at'] = until
        write_json(STATE_FILE, state)
        raise GenerationFailed('NotebookLM slide generation failed; cause not provided')
    if status not in ['completed', 'complete', 'ready', '3']: write_json(STATE_FILE, state); return False
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix('.part.pdf')
    pace_request()
    cli_result = subprocess.run(['/Users/sym/.local/bin/nlm', 'download', 'slide-deck', r['notebook_id'], '--id', r['artifact_id'], '--output', str(temp), '--no-progress'], capture_output=True, text=True, timeout=300,env=network_env())
    if cli_result.returncode: raise RuntimeError(cli_result.stderr or cli_result.stdout)
    if not temp.exists() or temp.read_bytes()[:5] != b'%PDF-': raise ValueError('Downloaded slide is not a PDF')
    os.replace(temp, target); r['slide_status'] = 'downloaded'; r['pdf'] = 'assets/slides/' + target.name
    # Native slide visuals become the illustrated web chapter assets.
    py = '/Users/sym/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3'
    subprocess.run([py, str(ROOT / 'scripts/optimize_slides.py'), str(target)], check=True, timeout=180)
    subprocess.run([py, str(ROOT / 'scripts/render_slides.py'), str(target)], check=True, timeout=180)
    r['updated_at'] = now(); write_json(STATE_FILE, state); return True

def assigned_episode_ids(state):
    assigned = {eid for batch in state['batches'].values() for eid in batch['ids']}
    return assigned | set(CONFIG.get('account_b_series_ids', []))

def run(args):
    (ROOT / 'work').mkdir(exist_ok=True); (ROOT / 'state').mkdir(exist_ok=True)
    with (ROOT / 'state/runner.lock').open('w') as lock:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise SystemExit('Another batch is running; no duplicate run started.')
        state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {'schema_version': 1, 'notebooks': {}, 'episodes': {}, 'batches': {}, 'deployments': []}
        items = catalog()
        date = dt.datetime.now(TZ).date().isoformat()
        group_count = {}
        for ep in items:
            if ep['rank'] == 100:
                group_count[ep['show']] = group_count.get(ep['show'], 0) + 1
                ep['standalone_group'] = (group_count[ep['show']] - 1) // 50 + 1
            state['episodes'].setdefault(ep['id'], {}).update({'title': ep['title'], 'show': ep['show'], 'topic': ep['topic'], 'source_available': ep['available']})
            record = state['episodes'][ep['id']]
            if record.get('attempts_date', date) != date:
                record.setdefault('attempt_history', {})[record['attempts_date']] = record.get('attempts', {})
                record['attempts'] = {}
                if record.get('status') == 'blocked': record['status'] = 'pending'
            record['attempts_date'] = date
            if not ep['available']: record['status'] = 'missing_source'
            elif any(v >= CONFIG['max_attempts'] for k,v in record.get('attempts', {}).items() if (k == 'article' and record.get('article_status') != 'ready') or (k == 'source' and not record.get('source_id')) or (k in ['slides', 'download'] and record.get('slide_status') != 'downloaded')):
                record['status'] = 'blocked'
        write_json(ROOT / 'state/queue.json', [{k: v for k, v in ep.items() if not k.endswith('_path')} for ep in items])
        if date not in state['batches']:
            assigned = assigned_episode_ids(state)
            eligible = [ep for ep in items if ep['available'] and ep['id'] not in assigned]
            retries = [ep['id'] for ep in items if ep['id'] in assigned and ep['available'] and state['episodes'][ep['id']].get('status') != 'complete']
            state['batches'][date] = {'ids': [ep['id'] for ep in eligible[:args.limit]], 'retry_ids': retries, 'started_at': now()}
        selected_ids = set(state['batches'][date]['ids'] + state['batches'][date].get('retry_ids', []))
        selected = [ep for ep in items if ep['id'] in selected_ids and not state['episodes'][ep['id']].get('delegated_profile')]
        retry_ids = set(state['batches'][date].get('retry_ids', []))
        selected.sort(key=lambda ep: ep['id'] not in retry_ids)
        write_json(STATE_FILE, state)
        print('BATCH', date, [ep['title'] for ep in selected], flush=True)
        for ep in selected if args.command == 'run' else []:
            if state['episodes'][ep['id']].get('status') == 'complete': continue
            if not remaining_attempts(state['episodes'][ep['id']], 'source'): continue
            try: prepare_source(state,ep)
            except Exception as error: mark_error(state,ep['id'],'source',error)
        for ep in selected if args.command == 'run' else []:
            if not state['episodes'][ep['id']].get('source_id'): continue
            if not remaining_attempts(state['episodes'][ep['id']], 'article'): continue
            try: make_article(state, ep); print('ARTICLE', ep['title'], flush=True)
            except Exception as error: mark_error(state, ep['id'], 'article', error)
        deadline = time.monotonic() + args.wait_minutes * 60
        while True:
            pending = 0
            artifact_cache = {}
            for nb in ({r.get('notebook_id') for r in state['episodes'].values() if r.get('slide_status') in ['queued','submitting']} | {state['episodes'][ep['id']].get('notebook_id') for ep in selected if state['episodes'][ep['id']].get('status') != 'complete'}) - {None}:
                if not notebook_check_due(state, nb): continue
                try: artifact_cache[nb] = get_artifacts(nb)
                except Exception as error: print('STATUS ERROR', str(error)[:250], flush=True)
            collecting = [ep for ep in items if ep in selected or state['episodes'][ep['id']].get('slide_status') in ['queued','submitting']]
            for ep in collecting:
                r = state['episodes'][ep['id']]
                remote = artifact_cache.get(r.get('notebook_id'), [])
                recovered = any(a.get('status') == 'completed' and ep['id'] in json.dumps(a,ensure_ascii=False) for a in remote)
                if not recovered and (r.get('slide_status') == 'failed' or not remaining_attempts(r, 'download')):
                    pending += 1; continue
                if r.get('notebook_id') not in artifact_cache and not (ROOT/'assets/slides'/(ep['id']+'.pdf')).exists():
                    pending += 1; continue
                try:
                    ready = collect_slides(state, ep, artifact_cache.get(r.get('notebook_id')))
                    if ready and r.get('article_status') == 'ready': r['status'] = 'complete'; r.pop('last_error', None)
                    else: pending += 1
                except Exception as error:
                    mark_error(state, ep['id'], 'slides' if isinstance(error,GenerationFailed) else 'download', error); pending += 1
            if args.command == 'run':
                for ep in selected:
                    r = state['episodes'][ep['id']]
                    if r.get('status') == 'complete' or not r.get('source_id') or r.get('artifact_id') and r.get('slide_status') != 'failed': continue
                    if not remaining_attempts(r,'slides') or not remaining_attempts(r,'download'): continue
                    artifacts = artifact_cache.get(r['notebook_id'])
                    if artifacts is None: continue  # Never submit when reconciliation failed.
                    try:
                        start_slides(state,ep,artifacts)
                        print('SLIDES',ep['title'],flush=True)
                    except GenerationDeferred as error:
                        print('DEFERRED',str(error),flush=True)
                    except Exception as error: mark_error(state,ep['id'],'slides',error)
                    break  # At most one new generation per polling cycle.
            write_json(STATE_FILE, state)
            print('COLLECT pending:', pending, flush=True)
            if not pending or time.monotonic() >= deadline: break
            active = any(r.get('slide_status') in ['queued','submitting'] for r in state['episodes'].values())
            if not active and cooldown_outlasts_budget(state,deadline): break
            paced_sleep(min(CONFIG.get('poll_interval_seconds',300),max(0,deadline-time.monotonic())))
        state['batches'][date]['finished_at'] = now()
        state['batches'][date]['complete'] = sum(state['episodes'][eid].get('status') == 'complete' for eid in state['batches'][date]['ids'])
        write_json(STATE_FILE, state)
        subprocess.run([sys.executable, str(ROOT / 'scripts/build.py')], check=True)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('command', choices=['run', 'collect', 'status', 'retry'])
    parser.add_argument('--limit', type=int, default=10); parser.add_argument('--wait-minutes', type=float, default=20)
    parser.add_argument('--id'); parser.add_argument('--stage', choices=['source', 'slides', 'article', 'download'])
    args = parser.parse_args()
    if args.command == 'status':
        s = json.loads(STATE_FILE.read_text()); counts = {}
        for e in s['episodes'].values(): counts[e.get('status', 'pending')] = counts.get(e.get('status', 'pending'), 0) + 1
        print(json.dumps({'counts': counts, 'batches': s['batches']}, ensure_ascii=False, indent=2))
    elif args.command == 'retry':
        if not args.id or not args.stage: parser.error('retry requires --id and --stage')
        with (ROOT / 'state/runner.lock').open('w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            s = json.loads(STATE_FILE.read_text()); r = s['episodes'][args.id]
            date = dt.datetime.now(TZ).date().isoformat()
            if r.get('attempts_date',date) != date:
                r.setdefault('attempt_history',{})[r['attempts_date']] = r.get('attempts',{})
                r['attempts'] = {}; r['attempts_date'] = date
            if not remaining_attempts(r,args.stage):
                raise SystemExit('Daily failure limit reached; retry does not reset today’s failures.')
            if args.stage == 'slides':
                if r.get('slide_status') != 'failed': raise SystemExit('Only confirmed failed artifacts may be retried; inspect ambiguous submission first.')
                # Keep the failed ID until start_slides archives it during reconciliation.
            write_json(STATE_FILE, s)
            r['status'] = 'pending'; write_json(STATE_FILE, s)
        print('Retry enabled. Run the daily batch to resume.')
    else: run(args)
