"""Use the pinned project CLI with the user's configured system proxy."""
import pathlib, subprocess, sys
from pipeline import network_env
root = pathlib.Path(__file__).resolve().parents[1]
env = network_env()
if '--dns-result-order=' not in env.get('NODE_OPTIONS',''):
    env['NODE_OPTIONS'] = (env.get('NODE_OPTIONS','')+' --dns-result-order=ipv4first').strip()
sys.exit(subprocess.run([str(root/'node_modules/.bin/wrangler'),*sys.argv[1:]],cwd=root,env=env).returncode)
