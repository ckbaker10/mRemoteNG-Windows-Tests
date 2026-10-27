"""Run isolated domain acceptance and retain results even on script failure."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import sys
import time
import uuid
from remote import create_session, run_ps_with_input

REPO = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('probe_dll')
    parser.add_argument('gpo_id', type=uuid.UUID, nargs='?')
    parser.add_argument('--timeout-minutes', type=int, default=20)
    args = parser.parse_args()
    if not re.fullmatch(r'C:\\mrng-lab\\transfer\\[A-Za-z0-9_.\\-]+\\PolicyProbe\.dll', args.probe_dll):
        raise ValueError('Use the pinned lab policy probe')
    if args.gpo_id is None:
        lookup = create_session('server').run_ps("$ErrorActionPreference='Stop';if($env:COMPUTERNAME -ne 'MRNG-DC' -or (Get-ADDomain).DNSRoot -ne 'mrng.test'){throw 'Use the owned domain'};$g=Get-GPO -Name 'mRemoteNG Lab Security Acceptance';if($g.Description -ne 'Owned mRemoteNG automated acceptance policy'){throw 'Unowned GPO'};$g.Id.Guid")
        if lookup.status_code:
            raise RuntimeError('Cannot identify the owned acceptance GPO')
        args.gpo_id = uuid.UUID(lookup.std_out.decode('utf-8-sig').strip())
    identifier = uuid.uuid4().hex
    output = REPO / 'work' / ('domain-acceptance-' + identifier[:8])
    output.mkdir(parents=True)
    guest_output = 'C:\\mrng-lab\\domain-acceptance-' + identifier
    source = REPO / 'scripts' / 'Invoke-DomainGpoTests.ps1'
    rights = REPO / 'scripts' / 'LabUserRights.cs'
    record = {'started_host_epoch': int(time.time()), 'status': 'waiting',
              'script_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
              'user_rights_source_sha256': hashlib.sha256(rights.read_bytes()).hexdigest(),
              'probe_dll': args.probe_dll, 'gpo_id': str(args.gpo_id), 'guest_output': guest_output}
    try:
        deadline = time.monotonic() + args.timeout_minutes * 60
        while time.monotonic() < deadline:
            try:
                status = create_session('client').run_ps((REPO / 'scripts' / 'Get-LabStatus.ps1').read_text())
                if status.status_code == 0 and json.loads(status.std_out).get('BootstrapReady'):
                    (output / 'guest-status.json').write_bytes(status.std_out)
                    break
            except Exception:
                pass
            time.sleep(45)
        else:
            raise TimeoutError('Owned domain client did not become ready')
        record['status'] = 'running'
        (output / 'metadata.json').write_text(json.dumps(record, indent=2) + '\n')
        script = ("Add-Type -TypeDefinition @'\n" + rights.read_text() + "\n'@\n& {\n" + source.read_text() + '\n} -ProbeDll \'' + args.probe_dll +
                  "' -GpoId '" + str(args.gpo_id) + "' -OutputDirectory '" + guest_output + "'")
        result = run_ps_with_input(create_session('client'), script, b'')
        (output / 'stdout.log').write_bytes(result.std_out)
        (output / 'stderr.log').write_bytes(result.std_err)
        record['exit_code'] = result.status_code
        for name in ('result.json', 'admin.json', 'standard\\result.json', 'isolation-progress.json', 'task-info.json', 'gpresult.xml', 'gpresult.log', 'gpupdate.log'):
            path = guest_output + '\\' + name
            fetched = run_ps_with_input(create_session('client'),
                "if(Test-Path -LiteralPath '" + path + "'){[Convert]::ToBase64String([IO.File]::ReadAllBytes('" + path + "'))}", b'')
            if fetched.status_code:
                raise RuntimeError('Cannot retrieve domain diagnostic artifact')
            if fetched.std_out.strip():
                (output / name.replace('\\', '-')).write_bytes(base64.b64decode(fetched.std_out.strip(), validate=True))
        if result.status_code or not (output / 'result.json').exists():
            raise RuntimeError('Domain script failed or produced no completion record')
        if json.loads((output / 'result.json').read_text(encoding='utf-8-sig')).get('Status') != 'passed':
            raise RuntimeError('Domain completion record did not pass')
        record['status'] = 'passed'
    except Exception as error:
        record['status'] = 'failed'
        record['error_type'] = type(error).__name__
        raise
    finally:
        record['finished_host_epoch'] = int(time.time())
        (output / 'metadata.json').write_text(json.dumps(record, indent=2) + '\n')
    print('Owned domain GPO acceptance passed; artifacts: ' + str(output))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('Owned domain acceptance stopped: ' + type(error).__name__, file=sys.stderr)
        sys.exit(1)
