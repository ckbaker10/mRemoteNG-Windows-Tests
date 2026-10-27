"""Promote only the owned isolated server; recovery input never enters argv."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys
import time
import uuid
from manage import ROOT
from remote import create_session, run_ps_with_input

REPO = Path(__file__).resolve().parents[1]


def save_credentials(path, value):
    temporary = path.with_name('credentials-' + uuid.uuid4().hex + '.tmp')
    with open(temporary, 'x', opener=lambda name, flags: os.open(name, flags, 0o600)) as stream:
        json.dump(value, stream)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def main():
    credential_file = ROOT / 'server' / 'credentials.json'
    if credential_file.stat().st_mode & 0o077:
        raise RuntimeError('Lab credentials must be owner-only')
    account = json.loads(credential_file.read_text())
    if account.get('username') != 'LabAdmin':
        raise RuntimeError('Expected the original local lab identity before promotion')
    if 'dsrm_password' not in account:
        account['dsrm_password'] = secrets.token_urlsafe(32) + 'aA1!'
    account['domain_username'] = 'MRNGLAB\\Administrator'
    save_credentials(credential_file, account)
    source = REPO / 'scripts' / 'Initialize-LabForest.ps1'
    output = REPO / 'work' / ('forest-' + uuid.uuid4().hex[:8])
    output.mkdir(mode=0o700, parents=True)
    record = {'started_host_epoch': int(time.time()), 'script_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
              'status': 'running', 'domain': 'mrng.test'}
    try:
        payload = json.dumps({'dsrm_password': account['dsrm_password']}).encode('ascii')
        result = run_ps_with_input(create_session('server'), source.read_text(), payload)
        (output / 'stdout.log').write_bytes(result.std_out)
        (output / 'stderr.log').write_bytes(result.std_err)
        record['exit_code'] = result.status_code
        if result.status_code:
            raise RuntimeError('Owned forest promotion returned an error')
        replies = [json.loads(line) for line in result.std_out.decode('utf-8-sig').splitlines() if line.startswith('{')]
        if len(replies) != 1 or not replies[0].get('PromotionCompleted'):
            raise RuntimeError('No explicit promotion completion was received')
        account['username'] = account['domain_username']
        save_credentials(credential_file, account)
        record['status'] = 'promoted-reboot-pending'
    except Exception as error:
        record['status'] = 'failed'
        record['error_type'] = type(error).__name__
        raise
    finally:
        record['finished_host_epoch'] = int(time.time())
        (output / 'result.json').write_text(json.dumps(record, indent=2) + '\n')
    print('Owned mrng.test forest created; the server is restarting.')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('Owned forest promotion stopped: ' + type(error).__name__, file=sys.stderr)
        sys.exit(1)
