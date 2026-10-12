"""Resume explicitly assigned missing episodes in a separate NotebookLM account.

Account-specific state, quotas and remote IDs stay in ignored state/accounts/.
One shared runner lock protects files; no saved default profile is switched.
"""
import argparse,copy,datetime as dt,fcntl,json,time
import pipeline as p

IDS=['6892d5fb638b0158792f7031','68d3600a522b40626cffca20']
PRIMARY=p.STATE_FILE

def sync_primary(job,profile):
    main=json.loads(PRIMARY.read_text())
    for eid,r in job['episodes'].items():
        primary=main['episodes'][eid]
        primary.setdefault('alternate_runs',{})[profile]=copy.deepcopy(r)
        if r.get('status')=='complete':
            changed = primary.get('artifact_id') != r.get('artifact_id') or primary.get('status') != 'complete'
            if primary.get('profile')!=profile:
                primary['previous_account_context']={k:copy.deepcopy(primary[k]) for k in ['notebook_id','source_id','artifact_id','failed_artifact_ids','attempts','errors'] if k in primary}
            for k in ['notebook_id','source_id','source_sha256','artifact_id','all_artifact_ids','slide_status','slide_remote_status','pdf']:
                if k in r:primary[k]=r[k]
            primary.update(status='complete',profile=profile,updated_at=p.now())
            if changed: primary['publication_status']='pending'
            primary.pop('delegated_profile',None);primary.pop('last_error',None)
        elif r.get('status') != 'superseded' and primary.get('status') != 'complete':primary['delegated_profile']=profile
    for batch in main['batches'].values():
        batch['complete']=sum(main['episodes'][eid].get('status')=='complete' for eid in batch['ids'])
    p.write_json(PRIMARY,main)

def run(profile,wait_minutes):
    p.CONFIG['notebooklm_profile']=profile
    p.STATE_FILE=p.ROOT/'state/accounts'/(profile+'.json')
    with (p.ROOT/'state/runner.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        main=json.loads(PRIMARY.read_text())
        job=json.loads(p.STATE_FILE.read_text()) if p.STATE_FILE.exists() else {'schema_version':1,'profile':profile,'notebooks':{},'episodes':{}}
        today=dt.datetime.now(p.TZ).date().isoformat()
        for eid in IDS:
            r=job['episodes'].setdefault(eid,{'article_status':'ready','title':main['episodes'][eid]['title'],'status':'pending'})
            if r.get('attempts_date',today)!=today:
                r.setdefault('attempt_history',{})[r['attempts_date']]=r.get('attempts',{});r['attempts']={}
            r['attempts_date']=today
        p.write_json(p.STATE_FILE,job);sync_primary(job,profile)
        selected=[ep for ep in p.catalog() if ep['id'] in IDS and job['episodes'][ep['id']].get('status') != 'superseded']
        selected.sort(key=lambda ep: sum(e.get('stage') == 'slides' for e in job['episodes'][ep['id']].get('errors',[])))
        for ep in selected:
            r=job['episodes'][ep['id']]
            if r.get('status')=='complete' or not p.remaining_attempts(r,'source'):continue
            try:p.prepare_source(job,ep)
            except Exception as e:
                p.mark_error(job,ep['id'],'source',e);break
        deadline=time.monotonic()+wait_minutes*60
        while True:
            cache={}
            for nb in {r.get('notebook_id') for r in job['episodes'].values() if r.get('status') not in ['complete','superseded']}-{None}:
                if not p.notebook_check_due(job,nb):continue
                try:cache[nb]=p.get_artifacts(nb)
                except Exception as e:print('STATUS ERROR',str(e)[:200],flush=True)
            for ep in selected:
                r=job['episodes'][ep['id']];artifacts=cache.get(r.get('notebook_id'))
                if r.get('status')=='complete' or artifacts is None:continue
                recovered=any(a.get('status')=='completed' and ep['id'] in json.dumps(a,ensure_ascii=False) for a in artifacts)
                if not recovered and (r.get('slide_status')=='failed' or not p.remaining_attempts(r,'download')):continue
                try:
                    if p.collect_slides(job,ep,artifacts):
                        r['status']='complete';print('COMPLETE',ep['title'],flush=True)
                except Exception as e:p.mark_error(job,ep['id'],'slides' if isinstance(e,p.GenerationFailed) else 'download',e)
            for ep in selected:
                r=job['episodes'][ep['id']]
                if r.get('status')=='complete' or not r.get('source_id') or r.get('artifact_id') and r.get('slide_status')!='failed':continue
                if not p.remaining_attempts(r,'slides') or not p.remaining_attempts(r,'download'):continue
                artifacts=cache.get(r['notebook_id'])
                if artifacts is None:continue
                try:p.start_slides(job,ep,artifacts);print('SUBMITTED',ep['title'],flush=True)
                except p.GenerationDeferred as e:print('DEFERRED',str(e),flush=True)
                except Exception as e:p.mark_error(job,ep['id'],'slides',e)
                break
            p.write_json(p.STATE_FILE,job);sync_primary(job,profile)
            print('ACCOUNT',profile,[(r['title'],r.get('slide_status')) for r in job['episodes'].values()],flush=True)
            if all(r.get('status') in ['complete','superseded'] for r in job['episodes'].values()) or time.monotonic()>=deadline:break
            active=any(r.get('slide_status') in ['queued','submitting'] for r in job['episodes'].values())
            if not active and not job['notebooks']:break
            if not active and p.cooldown_outlasts_budget(job,deadline):break
            p.paced_sleep(min(p.CONFIG['poll_interval_seconds'],max(0,deadline-time.monotonic())))

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--profile',choices=['account-b'],default='account-b');ap.add_argument('--wait-minutes',type=float,default=60);args=ap.parse_args();run(args.profile,args.wait_minutes)
