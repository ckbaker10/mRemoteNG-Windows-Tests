"""Continue an explicitly started owned client installation into build/tests.

Does not provision a domain, apply production policy, or retry failed builds.
Configuration contains archive provenance, never credentials.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid
from remote import create_session

REPO = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('config', type=Path)
    parser.add_argument('--timeout-minutes', type=int, default=180)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    for name in ('source_commit', 'harness_commit'):
        if not re.fullmatch('[0-9a-f]{40}', config[name]):
            raise ValueError('Invalid commit provenance')
    for name in ('source_sha256', 'harness_sha256'):
        if not re.fullmatch('[0-9a-f]{64}', config[name]):
            raise ValueError('Invalid archive hash')
    if not re.fullmatch(r'[A-Za-z0-9._-]+\.zip', config['source_archive']):
        raise ValueError('Invalid source archive filename')
    output = REPO / 'work' / ('client-' + config['source_commit'][:12] + '-' + uuid.uuid4().hex[:8])
    output.mkdir(parents=True, exist_ok=False)
    started = int(time.time())
    record = {'started_host_epoch': started, 'config_sha256': hashlib.sha256(args.config.read_bytes()).hexdigest(),
              'source_commit': config['source_commit'], 'harness_commit': config['harness_commit'], 'status': 'waiting'}

    def save():
        (output / 'controller.json').write_text(json.dumps(record, indent=2) + '\n')

    def run(name, script):
        record['phase'] = name
        save()
        result = create_session('client').run_ps(script)
        (output / (name + '.stdout')).write_bytes(result.std_out)
        (output / (name + '.stderr')).write_bytes(result.std_err)
        if result.status_code:
            raise RuntimeError('Guest phase failed: ' + name)
        return result

    save()
    try:
        status_script = (REPO / 'scripts' / 'Get-LabStatus.ps1').read_text()
        while int(time.time()) - started < args.timeout_minutes * 60:
            try:
                result = create_session('client').run_ps(status_script)
                if result.status_code == 0 and json.loads(result.std_out).get('BootstrapReady'):
                    (output / 'guest-status.json').write_bytes(result.std_out)
                    break
            except Exception:
                pass  # Installation has not exposed WinRM yet; no transport payload logging.
            time.sleep(45)
        else:
            raise TimeoutError('Client did not become ready within the configured deadline')
        record['status'] = 'running'
        run('cleanup', (REPO / 'scripts' / 'Clear-LabSetupSecrets.ps1').read_text())
        subprocess.run([sys.executable, str(REPO / 'lab' / 'manage.py'), 'seal', 'client'], check=True)
        run('build-tools', (REPO / 'scripts' / 'Initialize-BuildClient.ps1').read_text())
        # Only a dedicated loopback transfer service is used, containing public source archives.
        script = f"""$ErrorActionPreference = 'Stop'
$root = 'C:\\mrng-lab\\transfer'
New-Item -ItemType Directory $root -Force | Out-Null
$source = Join-Path $root '{config['source_archive']}'
$harness = Join-Path $root 'windows-tests.zip'
Invoke-WebRequest 'http://10.0.2.2:55987/{config['source_archive']}' -OutFile $source
Invoke-WebRequest 'http://10.0.2.2:55987/windows-tests.zip' -OutFile $harness
if ((Get-FileHash $source -Algorithm SHA256).Hash -ne '{config['source_sha256']}') {{ throw 'Source hash mismatch' }}
if ((Get-FileHash $harness -Algorithm SHA256).Hash -ne '{config['harness_sha256']}') {{ throw 'Harness hash mismatch' }}
$destination = Join-Path $root '{config['harness_commit']}-{output.name}'
Expand-Archive -LiteralPath $harness -DestinationPath $destination
& (Join-Path $destination 'scripts\\Invoke-SourceTests.ps1') -SourceArchive $source -ArchiveSha256 '{config['source_sha256']}' -SourceCommit '{config['source_commit']}'
"""
        result = run('source-tests', script)
        paths = re.findall(r'Run artifacts: (C:\\mrng-lab\\runs\\[0-9a-f]{12}-[0-9a-f]{32})', result.std_out.decode('utf-8'))
        if len(paths) != 1:
            raise ValueError('Cannot identify the guest test artifact directory')
        for name in ('tests.trx', 'result.json'):
            fetched = run('fetch-' + name, f"[Convert]::ToBase64String([IO.File]::ReadAllBytes('{paths[0]}\\{name}'))")
            (output / name).write_bytes(base64.b64decode(fetched.std_out.strip(), validate=True))
        record['status'] = 'passed-source-tests'
    except Exception as error:
        record['status'] = 'failed'
        record['error_type'] = type(error).__name__
        raise
    finally:
        record['finished_host_epoch'] = int(time.time())
        save()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('Client continuation stopped: ' + type(error).__name__, file=sys.stderr)
        sys.exit(1)
