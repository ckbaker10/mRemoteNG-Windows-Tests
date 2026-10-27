"""Run a local script on an owned guest through encrypted NTLM WinRM."""
import argparse
import json
import os
from pathlib import Path
import sys
import winrm

parser = argparse.ArgumentParser()
parser.add_argument('machine', choices=['client', 'server'])
parser.add_argument('script', type=Path)
args = parser.parse_args()
root = Path(os.environ.get('MRNG_LAB_ROOT', Path(__file__).resolve().parents[1] / 'work' / 'windows-lab')).resolve()
account = json.loads((root / args.machine / 'credentials.json').read_text())
port = 55985 if args.machine == 'client' else 55986
session = winrm.Session(f'http://127.0.0.1:{port}/wsman',
    auth=(account['username'], account['password']), transport='ntlm',
    message_encryption='always', operation_timeout_sec=30, read_timeout_sec=40)
try:
    result = session.run_ps(args.script.read_text(encoding='utf-8-sig'))
except Exception as error:
    # Credentials and transport payloads must never enter diagnostic logs.
    print(f'Guest request failed: {type(error).__name__}', file=sys.stderr)
    sys.exit(2)
sys.stdout.buffer.write(result.std_out)
sys.stderr.buffer.write(result.std_err)
sys.exit(result.status_code)
