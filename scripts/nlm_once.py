"""Use the installed nlm CLI without automatic mutation retries.

The CLI's network/RPC retry can repeat an already accepted generation.
The production runner persists each submission and reconciles before retrying.
"""
import os, sys
os.environ['NOTEBOOKLM_RATE_LIMIT_MAX_RETRIES'] = '0'
import notebooklm_tools.core.base as base
base.DEFAULT_MAX_RETRIES = 0
from notebooklm_tools.cli.main import cli_main
sys.exit(cli_main())
