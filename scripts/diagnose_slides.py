"""Read-only, red-capable check of an actual NotebookLM slide artifact."""
import argparse, json
import pipeline as p
ap=argparse.ArgumentParser();ap.add_argument('--profile',required=True)
ap.add_argument('--notebook',required=True);ap.add_argument('--id',required=True)
args=ap.parse_args();p.CONFIG['notebooklm_profile']=args.profile
artifact=next((x for x in p.get_artifacts(args.notebook) if x.get('id')==args.id),None)
status=artifact.get('status') if artifact else 'missing'
print(json.dumps({'profile':args.profile,'artifact_id':args.id,'status':status}))
raise SystemExit(0 if status=='completed' else 1)
