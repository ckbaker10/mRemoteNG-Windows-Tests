"""Join only the owned client; domain credentials travel through encrypted stdin."""
import hashlib
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
import uuid
from manage import ROOT
from promote_server import save_credentials
from remote import create_session, run_ps_with_input

REPO = Path(__file__).resolve().parents[1]


def main():
    accounts = {}
    for machine in ('server', 'client'):
        path = ROOT / machine / 'credentials.json'
        if path.stat().st_mode & 0o077:
            raise RuntimeError('Lab credentials must be owner-only')
        accounts[machine] = json.loads(path.read_text())
    if accounts['server']['username'] != 'MRNGLAB\\Administrator':
        raise RuntimeError('The owned forest must be promoted first')
    if accounts['client']['username'] not in ('LabAdmin', 'MRNG-CLIENT\\LabAdmin'):
        raise RuntimeError('Unexpected local client identity')
    # Keep management bound to the local account after joining the domain.
    accounts['client']['username'] = 'MRNG-CLIENT\\LabAdmin'
    save_credentials(ROOT / 'client' / 'credentials.json', accounts['client'])
    source = REPO / 'scripts' / 'Join-LabClient.ps1'
    output = REPO / 'work' / ('domain-join-' + uuid.uuid4().hex[:8])
    output.mkdir(mode=0o700, parents=True)
    record = {'started_host_epoch': int(time.time()), 'script_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
              'status': 'running', 'domain': 'mrng.test'}
    try:
        clock = REPO / 'scripts' / 'Initialize-LabClock.ps1'
        record['clock_script_sha256'] = hashlib.sha256(clock.read_bytes()).hexdigest()
        for machine in ('server', 'client'):
            # Python emits six fractional digits; .NET's round-trip format has seven.
            utc = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f') + '0+00:00'
            synced = run_ps_with_input(create_session(machine), clock.read_text(), json.dumps({'utc': utc}).encode('ascii'))
            (output / (machine + '-clock.stdout')).write_bytes(synced.std_out)
            (output / (machine + '-clock.stderr')).write_bytes(synced.std_err)
            if synced.status_code:
                raise RuntimeError('Owned lab clock synchronization failed')
        payload = json.dumps({name: accounts['server'][name] for name in ('username', 'password')}).encode('ascii')
        result = run_ps_with_input(create_session('client'), source.read_text(), payload)
        (output / 'stdout.log').write_bytes(result.std_out)
        (output / 'stderr.log').write_bytes(result.std_err)
        record['exit_code'] = result.status_code
        if result.status_code:
            raise RuntimeError('Owned domain join returned an error')
        reply = json.loads(result.std_out.decode('utf-8-sig'))
        if not reply.get('Joined') or reply.get('Domain') != 'mrng.test':
            raise RuntimeError('No explicit domain join completion was received')
        record['status'] = 'joined-reboot-pending'
    except Exception as error:
        record['status'] = 'failed'
        record['error_type'] = type(error).__name__
        raise
    finally:
        record['finished_host_epoch'] = int(time.time())
        (output / 'result.json').write_text(json.dumps(record, indent=2) + '\n')
    print('Owned client joined mrng.test; restart pending.')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('Owned client domain join stopped: ' + type(error).__name__, file=sys.stderr)
        sys.exit(1)
