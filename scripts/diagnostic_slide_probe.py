"""One isolated prompt-only control on the authorized QQ source, via nlm CLI."""
import argparse,datetime as dt,fcntl,json
import pipeline as p

EPISODE='68d3600a522b40626cffca20'
FOCUS='仅根据所选播客文稿，用简体中文制作详细幻灯片，讲清主要事件、人物与因果。不要把文件名或标识符写进标题。'
ap=argparse.ArgumentParser();ap.add_argument('action',choices=['submit','check'])
ap.add_argument('--variant',choices=['plain','comic'],default='plain')
args=ap.parse_args();p.CONFIG['notebooklm_profile']='account-b'
p.STATE_FILE=p.ROOT/'state/accounts/account-b.json'
with (p.ROOT/'state/runner.lock').open('w') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    state=json.loads(p.STATE_FILE.read_text());r=state['episodes'][EPISODE]
    key=dt.datetime.now(p.TZ).date().isoformat()+'-qq-'+args.variant+'-prompt-control'
    if args.variant=='plain' and key not in state.get('diagnostic_runs',{}) and dt.datetime.now(p.TZ).date().isoformat()+'-qq-prompt-control' in state.get('diagnostic_runs',{}):
        key=dt.datetime.now(p.TZ).date().isoformat()+'-qq-prompt-control'
    runs=state.setdefault('diagnostic_runs',{})
    if args.action=='submit':
        if key in runs:raise SystemExit('This bounded control has already been submitted; reconcile it instead')
        if args.variant=='comic' and not any(v.get('status')=='completed' for v in runs.values()):
            raise SystemExit('Establish a successful plain baseline before the comic control')
        if not p.remaining_attempts(r,'slides'):raise SystemExit('Daily failure cap reached')
        p.generation_gate(state)
        run={'episode':EPISODE,'notebook_id':r['notebook_id'],'source_id':r['source_id'],
             'submitted_at':p.now(),'status':'submitting','purpose':'prompt-only diagnostic; never publish'}
        runs[key]=run;state['diagnostic_inflight']=run;state['last_slide_submission_at']=p.now()
        p.write_json(p.STATE_FILE,state)
        focus=FOCUS if args.variant=='plain' else f'标识 {EPISODE}。用简体中文制作详细学习幻灯片，讲清本集背景、人物、主要事件、时间线和因果。采用《丁丁历险记》漫画风格：黑色轮廓、鲜明平涂色块、时代场景与中文旁白。依据所选逐字稿，不虚构人名、数字或引语。'
        result=p.cli('slides','create',r['notebook_id'],'--source-ids',r['source_id'],
                     '--format','detailed_deck','--length','default','--language','zh-CN',
                     '--focus',focus,'--confirm','--json')
        run.update(artifact_id=result['artifact_id'],status='queued')
        state.setdefault('diagnostic_artifact_ids',[]).append(result['artifact_id'])
    else:
        run=runs[key]
        if (dt.datetime.now(p.TZ)-dt.datetime.fromisoformat(run['submitted_at'])).total_seconds()<1200:
            raise SystemExit('Wait at least 20 minutes before checking the control')
        if not run.get('artifact_id'):raise SystemExit('Submission outcome ambiguous; inspect before another mutation')
        artifact=next((a for a in p.get_artifacts(run['notebook_id']) if a.get('id')==run['artifact_id']),None)
        if artifact is None:raise SystemExit('Diagnostic artifact not found')
        run['status']=artifact['status'];run['checked_at']=p.now()
        if run['status'] in ['failed','completed']:
            state.pop('diagnostic_inflight',None)
            if run['status']=='failed' and not run.get('failure_recorded'):
                p.mark_error(state,EPISODE,'slides','Prompt-only diagnostic also failed; server cause not provided')
                run['failure_recorded']=True
    p.write_json(p.STATE_FILE,state)
    print(json.dumps(run,ensure_ascii=False))
