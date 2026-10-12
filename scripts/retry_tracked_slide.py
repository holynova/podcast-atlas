"""One bounded nlm CLI retry of a tracked failed slide; never creates another ID."""
import argparse,fcntl,json
import pipeline as p
import supplement_account as supplement

ap=argparse.ArgumentParser();ap.add_argument('--profile',choices=['default','account-b'],required=True)
ap.add_argument('--episode',required=True);ap.add_argument('--artifact',required=True)
args=ap.parse_args()
if args.profile=='account-b' and args.episode not in supplement.IDS:
    raise SystemExit('Episode is outside this account’s explicitly assigned scope')
p.CONFIG['notebooklm_profile']=args.profile
if args.profile=='account-b':p.STATE_FILE=p.ROOT/'state/accounts/account-b.json'
with (p.ROOT/'state/runner.lock').open('w') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    state=json.loads(p.STATE_FILE.read_text());r=state['episodes'][args.episode]
    if args.artifact not in r.get('failed_artifact_ids',[]) and args.artifact!=r.get('artifact_id'):
        raise SystemExit('Artifact is not a tracked failure for this episode')
    if not p.remaining_attempts(r,'slides'):raise SystemExit('Daily failure cap reached')
    p.generation_gate(state)
    state['last_slide_submission_at']=p.now()
    r.update(artifact_id=args.artifact,slide_status='submitting',slide_submitted_at=p.now())
    r.setdefault('retry_operations',[]).append({'at':p.now(),'method':'nlm studio retry','artifact_id':args.artifact})
    p.write_json(p.STATE_FILE,state)
    try:
        result=p.cli('studio','retry',r['notebook_id'],'--id',args.artifact,'--profile',args.profile,'--confirm','--json')
        if result.get('artifact_id')!=args.artifact:raise ValueError('Retry changed artifact ID')
        r['slide_status']='queued';r['slide_remote_status']=result.get('status')
        r['failed_artifact_ids']=[x for x in r.get('failed_artifact_ids',[]) if x!=args.artifact]
        print(json.dumps(result,ensure_ascii=False))
    except Exception as error:
        # Delivery may be ambiguous. Keep the tracked ID; reconcile before any next mutation.
        p.mark_error(state,args.episode,'slides',error)
        raise
    finally:
        p.write_json(p.STATE_FILE,state)
        if args.profile=='account-b':supplement.sync_primary(state,args.profile)
