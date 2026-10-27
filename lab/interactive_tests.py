"""Run the pinned dialog tests in the signed-in local lab desktop."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import sys
import time
import uuid
from remote import create_session, run_ps_with_input, bind_parameters

REPO = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('guest_run')
    parser.add_argument('probe_dll')
    args = parser.parse_args()
    if not re.fullmatch(r'C:\\mrng-lab\\runs\\[0-9a-f]{12}-[0-9a-f]{32}', args.guest_run):
        raise ValueError('Use the source run directory')
    if not re.fullmatch(r'C:\\mrng-lab\\transfer\\[A-Za-z0-9_.\\-]+\\PolicyProbe\.dll', args.probe_dll):
        raise ValueError('Use the pinned probe path')
    harness = args.probe_dll.split('\\probes\\', 1)[0]
    source = REPO / 'scripts' / 'Invoke-InteractiveUnitTests.ps1'
    wrapper = REPO / 'scripts' / 'Invoke-PinnedScript.ps1'
    parameters = {'ScriptPath': harness + '\\scripts\\Invoke-InteractiveUnitTests.ps1',
                  'ScriptSha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                  'Parameters': {'ProjectPath': args.guest_run + '\\source\\mRemoteNGTests\\mRemoteNGTests.csproj'}}
    script, payload = bind_parameters(wrapper.read_text(), parameters)
    output = REPO / 'work' / ('interactive-' + uuid.uuid4().hex[:8])
    output.mkdir(parents=True)
    record = {'host_started': int(time.time()), 'parameters': parameters,
              'wrapper_sha256': hashlib.sha256(wrapper.read_bytes()).hexdigest(), 'status': 'running'}
    try:
        result = run_ps_with_input(create_session('client'), script, payload)
        (output / 'stdout.log').write_bytes(result.std_out)
        (output / 'stderr.log').write_bytes(result.std_err)
        record['exit_code'] = result.status_code
        if result.status_code:
            raise RuntimeError('Interactive tests failed')
        paths = re.findall(r'Interactive test artifacts: (C:\\mrng-lab\\runs\\[^\r\n]+)', result.std_out.decode('utf-8-sig'))
        if len(paths) != 1:
            raise RuntimeError('No explicit interactive artifact directory')
        record['guest_output'] = paths[0]
        for name in ('interactive.trx', 'interactive-result.json', 'interactive.log'):
            fetched = run_ps_with_input(create_session('client'),
                "[Convert]::ToBase64String([IO.File]::ReadAllBytes('" + paths[0] + '\\' + name + "'))", b'')
            if fetched.status_code:
                raise RuntimeError('Cannot retrieve interactive result')
            (output / name).write_bytes(base64.b64decode(fetched.std_out.strip(), validate=True))
        completed = json.loads((output / 'interactive-result.json').read_text(encoding='utf-8-sig'))
        if completed.get('Status') != 'passed' or completed.get('SessionId', 0) <= 0:
            raise RuntimeError('No passed result from an interactive session')
        record['status'] = 'passed'
    except Exception as error:
        record['status'] = 'failed'
        record['error_type'] = type(error).__name__
        raise
    finally:
        record['host_finished'] = int(time.time())
        (output / 'metadata.json').write_text(json.dumps(record, indent=2) + '\n')
    print('Interactive tests passed; guest artifacts: ' + record['guest_output'])


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('Interactive tests stopped: ' + type(error).__name__, file=sys.stderr)
        sys.exit(1)
