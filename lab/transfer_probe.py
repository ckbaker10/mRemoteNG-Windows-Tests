"""Transfer a hash-pinned public harness archive and build its native policy probe."""
import argparse
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
    parser.add_argument('archive')
    parser.add_argument('sha256')
    parser.add_argument('source_root')
    parser.add_argument('--build-only', action='store_true')
    parser.add_argument('--print-path-only', action='store_true')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9._-]+\.zip', args.archive) or not re.fullmatch('[0-9a-f]{64}', args.sha256):
        raise ValueError('Invalid archive provenance')
    if not re.fullmatch(r'C:\\mrng-lab\\runs\\[0-9a-f]{12}-[0-9a-f]{32}\\source', args.source_root):
        raise ValueError('Use the pinned extracted source')
    identifier = uuid.uuid4().hex
    output = REPO / 'work' / ('probe-build-' + identifier[:8])
    output.mkdir(parents=True)
    guest_root = 'C:\\mrng-lab\\transfer\\probe-' + identifier
    guest_output = 'C:\\mrng-lab\\probe-build-' + identifier
    build_only = '-BuildOnly' if args.build_only else ''
    script = f"""$ProgressPreference='SilentlyContinue'
$archive = 'C:\\mrng-lab\\transfer\\{args.archive}'
Invoke-WebRequest -UseBasicParsing 'http://10.0.2.2:55987/{args.archive}' -OutFile $archive
if ((Get-FileHash $archive -Algorithm SHA256).Hash -ne '{args.sha256}') {{ throw 'Harness archive hash mismatch' }}
Expand-Archive -LiteralPath $archive -DestinationPath '{guest_root}'
& powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File '{guest_root}\\scripts\\Invoke-PolicyProbeTests.ps1' -SourceRoot '{args.source_root}' -HarnessRoot '{guest_root}' -OutputDirectory '{guest_output}' {build_only}
if ($LASTEXITCODE) {{ throw 'Probe build or matrix failed' }}
"""
    record = {'started_host_epoch': int(time.time()), 'archive': args.archive, 'archive_sha256': args.sha256,
              'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'source_root': args.source_root,
              'guest_output': guest_output, 'build_only': args.build_only, 'status': 'running'}
    (output / 'command.ps1').write_text(script)
    try:
        result = run_ps_with_input(create_session('client'), script, b'')
        (output / 'stdout.log').write_bytes(result.std_out)
        (output / 'stderr.log').write_bytes(result.std_err)
        record['exit_code'] = result.status_code
        if result.status_code:
            raise RuntimeError('Native probe build failed')
        paths = re.findall(r'Policy probe: (C:\\mrng-lab\\transfer\\[^\r\n]+\\PolicyProbe\.dll)', result.std_out.decode('utf-8-sig'))
        if len(paths) != 1:
            raise RuntimeError('No explicit probe artifact was received')
        record['probe_dll'] = paths[0]
        record['status'] = 'passed'
    except Exception as error:
        record['status'] = 'failed'
        record['error_type'] = type(error).__name__
        raise
    finally:
        record['finished_host_epoch'] = int(time.time())
        (output / 'metadata.json').write_text(json.dumps(record, indent=2) + '\n')
    print(record['probe_dll'] if args.print_path_only else 'Native policy probe built: ' + record['probe_dll'])


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('Native probe build stopped: ' + type(error).__name__, file=sys.stderr)
        sys.exit(1)
