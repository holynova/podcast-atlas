#!/usr/bin/env python3
"""One resumable five-hour cycle, shared by two nlm profiles.

The coordinator releases the writer lock while waiting. Source, article and
slide failures stay independent; only explicit account assignments are used.
"""
import argparse,copy,datetime as dt,fcntl,json,time
import pipeline as p
import supplement_account as b

MAIN=p.ROOT/'state/progress.json'

def read(path):return json.loads(path.read_text())
def cycle_key(moment=None):
    moment=moment or dt.datetime.now(p.TZ)
    anchor=dt.datetime.fromisoformat(p.CONFIG['cycle_anchor_at'])
    slot=max(0,int((moment-anchor).total_seconds()//(p.CONFIG['cycle_interval_hours']*3600)))
    return anchor.isoformat(timespec='seconds')+'#'+str(slot)

def owner(eid,main):
    if eid in b.IDS:return 'account-b'
    return main['episodes'][eid].get('delegated_profile','default')

def refresh_attempts(job):
    today=dt.datetime.now(p.TZ).date().isoformat()
    for r in job['episodes'].values():
        if r.get('attempts_date',today)!=today:
            r.setdefault('attempt_history',{})[r['attempts_date']]=copy.deepcopy(r.get('attempts',{}))
            r['attempts']={}
            if r.get('status')=='blocked':r['status']='pending'
        r['attempts_date']=today

def configure(profile):
    p.CONFIG['notebooklm_profile']=profile
    p.STATE_FILE=MAIN if profile=='default' else p.ROOT/'state/accounts/account-b.json'
    main=read(MAIN)
    job=main if profile=='default' else read(p.STATE_FILE)
    if profile=='account-b':
        for eid in b.IDS:
            primary=main['episodes'][eid]
            r=job['episodes'].setdefault(eid,{'title':primary['title'],'status':'pending'})
            if primary.get('status')=='complete' and primary.get('profile')!='account-b':
                r.update(status='superseded',superseded_by={'profile':primary.get('profile','default'),'artifact_id':primary.get('artifact_id'),'at':p.now()})
    refresh_attempts(job);p.write_json(p.STATE_FILE,job)
    return job

def sync(job,profile):
    p.write_json(p.STATE_FILE,job)
    if profile=='account-b':b.sync_primary(job,profile)

def save_cycle(cycle):
    main=read(MAIN);main.setdefault('cycles',{})[cycle['key']]=cycle;p.write_json(MAIN,main)

def checkpoint(cycle,job):
    save_cycle(cycle)
    # Pipeline writes the whole default-account snapshot during each CLI stage.
    # Carry the reserved cycle into that snapshot before any remote mutation.
    if p.STATE_FILE==MAIN:job.setdefault('cycles',{})[cycle['key']]=copy.deepcopy(cycle)

def balanced(candidates,main,limit):
    pools={profile:[ep for ep in candidates if owner(ep['id'],main)==profile] for profile in ['default','account-b']}
    order=b.SERIES_IDS+b.SUPPLEMENT_IDS
    pools['account-b'].sort(key=lambda ep:order.index(ep['id']) if ep['id'] in order else len(order))
    result=[]
    while len(result)<limit and any(pools.values()):
        for profile in ['default','account-b']:
            if pools[profile] and len(result)<limit:result.append(pools[profile].pop(0)['id'])
    return result

def stage_eligible(ep,main,stages):
    r=main['episodes'][ep['id']]
    if owner(ep['id'],main)=='account-b':r=r.get('alternate_runs',{}).get('account-b',{})
    today=dt.datetime.now(p.TZ).date().isoformat()
    if r.get('attempts_date',today)!=today:return True
    return all(p.remaining_attempts(r,stage) for stage in stages)

def plan(main,items,key,slide_limit,article_limit):
    if key in main.get('cycles',{}):return copy.deepcopy(main['cycles'][key])
    available=[ep for ep in items if ep['available']]
    slide_candidates=[ep for ep in available if not (p.ROOT/'assets/slides'/(ep['id']+'.pdf')).exists() and stage_eligible(ep,main,['source','slides','download'])]
    # Ready text can get its missing visuals first; series order is retained within each group.
    slide_candidates.sort(key=lambda ep:not (p.ROOT/'content'/(ep['id']+'.json')).exists())
    article_candidates=[ep for ep in available if not (p.ROOT/'content'/(ep['id']+'.json')).exists() and stage_eligible(ep,main,['source','article'])]
    return {'key':key,'started_at':p.now(),'slide_limit':slide_limit,
            'slide_ids':balanced(slide_candidates,main,slide_limit),
            'article_ids':balanced(article_candidates,main,article_limit),
            'attempted_slide_ids':[],'submitted_slide_ids':[],'recovered_ids':[],
            'status':'running'}

def can_submit(cycle,eid):
    return eid in cycle['slide_ids'] and eid not in cycle['attempted_slide_ids'] and len(cycle['attempted_slide_ids'])<cycle['slide_limit']

def status_cache(job,profiles,checked,full=False):
    cache={}
    notebooks={r.get('notebook_id') for r in job['episodes'].values() if r.get('status') not in ['complete','superseded'] and (full or r.get('slide_status') in ['queued','submitting'])}
    watch=job.get('manual_retry_watch',{})
    if watch.get('notebook_id') and not watch.get('checked_at'):notebooks.add(watch['notebook_id'])
    for nb in notebooks-{None}:
        if not p.notebook_check_due(job,nb):continue
        key=(profiles,nb)
        if key in checked:continue
        last=job.get('last_notebook_checks',{}).get(nb)
        if last and (dt.datetime.now(p.TZ)-dt.datetime.fromisoformat(last)).total_seconds()<p.CONFIG['poll_interval_seconds']:continue
        checked.add(key)
        try:
            cache[nb]=p.get_artifacts(nb)
            job.setdefault('last_notebook_checks',{})[nb]=p.now()
        except Exception as error:print('STATUS ERROR',profiles,str(error)[:200],flush=True)
    return cache

def collect(profile,items,cycle,checked,caches,full=False):
    job=configure(profile);cache=status_cache(job,profile,checked,full)
    for nb,artifacts in cache.items():caches[(profile,nb)]=(artifacts,time.monotonic())
    watch=job.get('manual_retry_watch',{})
    if watch.get('notebook_id') in cache:
        watched=cache[watch['notebook_id']];watch['last_checked_at']=p.now()
        if all(a.get('status') in ['completed','failed'] for a in watched):watch['checked_at']=p.now()
    for ep in items:
        eid=ep['id'];r=job['episodes'].get(eid)
        if not r or r.get('status') in ['complete','superseded']:continue
        artifacts=cache.get(r.get('notebook_id'))
        if artifacts is None:continue
        if r.get('slide_status') in ['queued','submitting'] and not r.get('artifact_id'):
            related=[a for a in artifacts if eid in json.dumps(a,ensure_ascii=False) and a.get('id') not in job.get('diagnostic_artifact_ids',[])]
            if related:
                match=next((a for a in related if a.get('status')=='completed'),next((a for a in related if a.get('status')!='failed'),related[0]))
                r['artifact_id']=match.get('id',match.get('artifact_id'));r['slide_status']='queued'
        recovered=any(a.get('status')=='completed' and eid in json.dumps(a,ensure_ascii=False) and a.get('id') not in job.get('diagnostic_artifact_ids',[]) for a in artifacts)
        if not recovered and (r.get('slide_status')=='failed' or not r.get('artifact_id')):continue
        try:
            if p.collect_slides(job,ep,artifacts):
                article=p.ROOT/'content'/(eid+'.json')
                if article.exists():p.validate_article(read(article));r.update(article_status='ready',status='complete')
                else:r['status']='pending'
                r['publication_status']='pending'
                if eid not in cycle['recovered_ids']:cycle['recovered_ids'].append(eid)
                print('COLLECTED',profile,eid,flush=True)
        except Exception as error:p.mark_error(job,eid,'slides' if isinstance(error,p.GenerationFailed) else 'download',error)
    sync(job,profile);save_cycle(cycle)

def prepare_cycle_source(job,ep,cycle):
    eid=ep['id']
    if job['episodes'][eid].get('source_id'):return
    attempted=cycle.setdefault('attempted_source_ids',[])
    if eid in attempted:raise p.GenerationDeferred('Source already attempted this cycle; next retry is in the next five-hour window')
    attempted.append(eid);checkpoint(cycle,job)
    p.prepare_source(job,ep)

def articles(items,cycle,deadline):
    for ep in items:
        eid=ep['id']
        if eid not in cycle['article_ids'] or time.monotonic()>=deadline:continue
        if (p.ROOT/'content'/(eid+'.json')).exists() or eid in cycle.get('attempted_article_ids',[]):continue
        main=read(MAIN);profile=owner(eid,main);job=configure(profile)
        r=job['episodes'][eid]
        if not all(p.remaining_attempts(r,k) for k in ['source','article']):continue
        stage='source'
        try:
            prepare_cycle_source(job,ep,cycle);stage='article'
            cycle.setdefault('attempted_article_ids',[]).append(eid);checkpoint(cycle,job)
            p.make_article(job,ep)
            r['publication_status']='pending';print('TEXT READY',profile,eid,flush=True)
        except p.GenerationDeferred as error:print('DEFERRED',profile,str(error),flush=True)
        except Exception as error:p.mark_error(job,eid,stage,error)
        sync(job,profile);save_cycle(cycle)

def submit(profile,items,cycle,checked,caches,deadline):
    job=configure(profile)
    candidates=[ep for ep in items if owner(ep['id'],read(MAIN))==profile and can_submit(cycle,ep['id'])]
    order=cycle['slide_ids'];candidates.sort(key=lambda ep:order.index(ep['id']))
    for ep in candidates:
        eid=ep['id'];r=job['episodes'][eid]
        if time.monotonic()>=deadline:return
        if (p.ROOT/'assets/slides'/(eid+'.pdf')).exists() or r.get('slide_status') in ['queued','submitting']:continue
        if not all(p.remaining_attempts(r,k) for k in ['source','slides','download']):continue
        stage='source'
        try:
            p.generation_gate(job);prepare_cycle_source(job,ep,cycle);stage='slides'
            nb=r['notebook_id']
            if not p.notebook_check_due(job,nb):return
            # Reconcile once immediately before any mutation, including ambiguous deliveries.
            if (profile,nb) in checked:
                cached=caches.get((profile,nb))
                if not cached or time.monotonic()-cached[1]>=p.CONFIG['poll_interval_seconds']:return
                artifacts=cached[0]
            else:
                checked.add((profile,nb));artifacts=p.get_artifacts(nb)
                caches[(profile,nb)]=(artifacts,time.monotonic())
            if any(a.get('status') in ['completed','in_progress','queued'] and eid in json.dumps(a,ensure_ascii=False) and a.get('id') not in job.get('diagnostic_artifact_ids',[]) for a in artifacts):
                if p.collect_slides(job,ep,artifacts):
                    if (p.ROOT/'content'/(eid+'.json')).exists():r.update(status='complete',article_status='ready')
                    r['publication_status']='pending'
                    if eid not in cycle['recovered_ids']:cycle['recovered_ids'].append(eid)
                sync(job,profile);save_cycle(cycle);return
            cycle['attempted_slide_ids'].append(eid);checkpoint(cycle,job)
            p.start_slides(job,ep,artifacts)
            if r.get('slide_status') in ['queued','submitting']:
                cycle['submitted_slide_ids'].append(eid);print('SUBMITTED',profile,eid,flush=True)
        except p.GenerationDeferred as error:print('DEFERRED',profile,str(error),flush=True)
        except Exception as error:p.mark_error(job,eid,stage,error)
        sync(job,profile);save_cycle(cycle)
        return

def can_continue(cycle,main,second,deadline):
    for profile,job in [('default',main),('account-b',second)]:
        if any(r.get('slide_status') in ['queued','submitting'] and r.get('status')!='superseded' for r in job['episodes'].values()):return True
        if job.get('manual_retry_watch') and not job['manual_retry_watch'].get('checked_at'):return True
        if p.cooldown_outlasts_budget(job,deadline):continue
        for eid in cycle['slide_ids']:
            if owner(eid,main)!=profile or not can_submit(cycle,eid):continue
            r=job['episodes'].get(eid,{})
            if (p.ROOT/'assets/slides'/(eid+'.pdf')).exists():continue
            if not all(p.remaining_attempts(r,k) for k in ['source','slides','download']):continue
            if eid in cycle.get('attempted_source_ids',[]) and not r.get('source_id'):continue
            return True
    return False

def run(args):
    items=p.catalog()
    deadline=time.monotonic()+args.wait_minutes*60
    with (p.ROOT/'state/cycle.lock').open('w') as run_lock:
        fcntl.flock(run_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        key=cycle_key();main=read(MAIN)
        cycle=plan(main,items,key,args.slide_limit,args.article_limit)
        if args.plan_only:
            print(json.dumps(cycle,ensure_ascii=False,indent=2));return
        first=True
        while True:
            with (p.ROOT/'state/runner.lock').open('w') as write_lock:
                fcntl.flock(write_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                # Do not hold the writer lock across the five-minute wait.
                checked=set();caches={}
                for profile in ['default','account-b']:collect(profile,items,cycle,checked,caches,full=first)
                if first:
                    articles(items,cycle,deadline);first=False
                if not args.text_only:
                    for profile in ['default','account-b']:submit(profile,items,cycle,checked,caches,deadline)
                cycle['article_ready_ids']=[eid for eid in cycle['article_ids'] if (p.ROOT/'content'/(eid+'.json')).exists()]
                cycle['completed_slide_ids']=[eid for eid in cycle['slide_ids'] if (p.ROOT/'assets/slides'/(eid+'.pdf')).exists()]
                cycle['status']='complete' if len(cycle['completed_slide_ids'])==len(cycle['slide_ids']) else 'pending'
                cycle['last_checked_at']=p.now();save_cycle(cycle)
                print('CYCLE',json.dumps({k:cycle[k] for k in ['key','status','article_ready_ids','completed_slide_ids','submitted_slide_ids']},ensure_ascii=False),flush=True)
            if args.text_only or cycle['status']=='complete' or time.monotonic()>=deadline:break
            if not can_continue(cycle,read(MAIN),read(p.ROOT/'state/accounts/account-b.json'),deadline):break
            # A failed target is never submitted again in this cycle, and pending deliveries
            # stay tracked. Unfinished work resumes in the next five-hour cycle.
            p.paced_sleep(min(p.CONFIG['poll_interval_seconds'],max(0,deadline-time.monotonic())))
        with (p.ROOT/'state/runner.lock').open('w') as write_lock:
            fcntl.flock(write_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            cycle['finished_at']=p.now();save_cycle(cycle)
        print('Saved cycle. Build/publish separately after reviewing the new artifacts.',flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--slide-limit',type=int,default=p.CONFIG['cycle_slide_limit']);ap.add_argument('--article-limit',type=int,default=p.CONFIG['cycle_article_limit']);ap.add_argument('--wait-minutes',type=float,default=150);ap.add_argument('--text-only',action='store_true');ap.add_argument('--plan-only',action='store_true')
    args=ap.parse_args()
    if args.slide_limit<0 or args.slide_limit>p.CONFIG['cycle_slide_limit']:ap.error('Slide limit must stay within the configured shared cycle limit')
    if args.article_limit<0 or args.article_limit>p.CONFIG['cycle_article_limit']:ap.error('Article limit must stay within the configured cycle limit')
    if args.wait_minutes<0 or args.wait_minutes>150:ap.error('Run window must be between 0 and 150 minutes')
    run(args)
