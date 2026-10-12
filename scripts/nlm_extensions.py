"""Project-local additions to the installed nlm command tree; no browser access."""
import json,re
import typer
from notebooklm_tools.cli.commands.studio import app
from notebooklm_tools.cli.utils import get_client

def retry_failed_slide(client, notebook_id, artifact_id):
    artifact = client.get_artifact(notebook_id, artifact_id)
    if not artifact or len(artifact) < 17 or artifact[0] != artifact_id or artifact[2] != 8 or artifact[4] != 4:
        raise ValueError('Only an existing, confirmed failed slide deck can be retried')
    options = artifact[16][0]
    sources = client._extract_artifact_source_ids(artifact, 8)
    if not sources or len(options) < 4:
        raise ValueError('Cannot preserve original sources or slide settings')
    # This is the installed nlm SDK's existing update + kickoff implementation.
    return client.start_artifact_generation(
        notebook_id, artifact_id, steering_prompt=options[0] or '',
        language=options[1], source_ids=sources,
        settings={'slide_format':options[2], 'slide_length':options[3]},
    )

@app.command('retry')
def retry_command(notebook_id: str, id: str = typer.Option(..., '--id'),
                  profile: str = typer.Option('default', '--profile'),
                  confirm: bool = typer.Option(False, '--confirm'),
                  json_output: bool = typer.Option(False, '--json')):
    """Restart a failed slide in place, preserving its ID and original settings."""
    if not confirm: typer.confirm('Retry this failed slide deck?', abort=True)
    with get_client(profile) as client:
        result = retry_failed_slide(client, notebook_id, id)
    print(json.dumps(result, ensure_ascii=False))

@app.command('failure-info')
def failure_info(notebook_id: str, id: str = typer.Option(..., '--id'),
                 profile: str = typer.Option('default', '--profile')):
    """Inspect failed artifact metadata without printing sources, prompts or URLs."""
    with get_client(profile) as client:
        artifact=client.get_artifact(notebook_id,id)
    if not artifact or artifact[0]!=id:raise ValueError('Artifact not found')
    reasons=[]
    def shape(v,path):
        if isinstance(v,list):return [shape(x,path+[i]) for i,x in enumerate(v)]
        if isinstance(v,str):
            if not v.startswith('http') and len(v)<500 and any(k in v.lower() for k in ['error','fail','quota','exhaust','unsupported','denied','safety','blocked','unavailable','timeout','invalid','refused','permission','limit','generation','失败','错误','无法','繁忙','限制','拒绝','违规']):
                reasons.append({'field':path,'message':v})
            return {'string_length':len(v),'is_uuid':bool(re.fullmatch(r'[0-9a-fA-F-]{36}',v)),
                    'is_numeric':v.isdecimal(),'is_url':v.startswith('http'),'has_chinese':bool(re.search(r'[\u4e00-\u9fff]',v)),
                    'enum':v if len(v)<100 and re.fullmatch(r'[A-Z]+(?:_[A-Z0-9]+)+',v) else None}
        return v
    fields={i:shape(v,[i]) for i,v in enumerate(artifact) if i not in [0,1,3,16] and v is not None}
    print(json.dumps({'artifact_id':id,'raw_status':artifact[4],'metadata_shape':fields,'reason_fields':reasons},ensure_ascii=False))
