"""Display an actual guest result on its desktop and capture the unmodified screen."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import sys
import time
import uuid
from PIL import Image
from manage import ROOT, qmp
from remote import create_session, run_ps_with_input

REPO = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('stage', choices=['Environment', 'Source', 'Interactive', 'Registry', 'Domain', 'Rekey'])
    parser.add_argument('output', type=Path)
    parser.add_argument('--result-path')
    args = parser.parse_args()
    if args.result_path and not re.fullmatch(r'C:\\mrng-lab\\[A-Za-z0-9_.\\-]+', args.result_path):
        raise ValueError('Use an unquoted lab result path')
    if args.stage != 'Environment' and not args.result_path:
        raise ValueError('A recorded result is required')
    worker = REPO / 'scripts' / 'Show-LabEvidence.ps1'
    identifier = uuid.uuid4().hex
    work = REPO / 'work' / ('evidence-screen-' + identifier[:8])
    work.mkdir(parents=True)
    task = 'mRemoteNG-Lab-Evidence-' + identifier
    payload = json.dumps({'worker': base64.b64encode(worker.read_bytes()).decode('ascii'),
                          'sha256': hashlib.sha256(worker.read_bytes()).hexdigest(),
                          'stage': args.stage, 'result': args.result_path, 'id': identifier}).encode('ascii')
    script = r"""$ErrorActionPreference='Stop'
$d=[Console]::In.ReadToEnd()|ConvertFrom-Json
$folder='C:\mrng-lab\evidence-'+$d.id
New-Item -ItemType Directory $folder|Out-Null
$worker=Join-Path $folder 'Show-LabEvidence.ps1'
[IO.File]::WriteAllBytes($worker,[Convert]::FromBase64String($d.worker))
if((Get-FileHash $worker -Algorithm SHA256).Hash -ne $d.sha256){throw 'Evidence worker hash mismatch'}
$ready=Join-Path $folder 'ready.txt'
$errorFile=Join-Path $folder 'error.txt'
$command="& '$worker' -Stage $($d.stage)"
if($d.result){$command+=" -ResultPath '$($d.result)'"}
$command="try{$command;if(-not `$?){throw 'Evidence worker failed'};[IO.File]::WriteAllText('$ready','passed')}catch{(`$_|Out-String)|Set-Content '$errorFile';throw}"
$arguments='-NoProfile -NoExit -ExecutionPolicy Bypass -Command "'+$command+'"'
$action=New-ScheduledTaskAction -Execute "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -Argument $arguments
$principal=New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Highest
$settings=New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 3)
$task='mRemoteNG-Lab-Evidence-'+$d.id
Register-ScheduledTask -TaskName $task -Action $action -Principal $principal -Settings $settings|Out-Null
Start-ScheduledTask -TaskName $task
$deadline=[DateTime]::UtcNow.AddSeconds(45)
while(-not(Test-Path $ready) -and -not(Test-Path $errorFile) -and [DateTime]::UtcNow -lt $deadline){Start-Sleep -Seconds 1}
if(Test-Path $errorFile){throw (Get-Content $errorFile -Raw)}
if(-not(Test-Path $ready)){throw 'The logged-on lab desktop did not display a passed result'}
'Actual guest result displayed'
"""
    started = int(time.time())
    record = {'host_started': started, 'worker_sha256': hashlib.sha256(worker.read_bytes()).hexdigest(),
              'stage': args.stage, 'result_path': args.result_path, 'status': 'running'}
    try:
        qmp('client', 'send-key', {'keys': [{'type': 'qcode', 'data': 'ctrl'}], 'hold-time': 100})
        time.sleep(1)
        response = run_ps_with_input(create_session('client'), script, payload)
        (work / 'stdout.log').write_bytes(response.std_out)
        (work / 'stderr.log').write_bytes(response.std_err)
        if response.status_code:
            raise RuntimeError('Evidence desktop display failed')
        # The PNG changes only the screenshot file format; no pixels are annotated.
        qmp('client', 'send-key', {'keys': [{'type': 'qcode', 'data': 'ctrl'}], 'hold-time': 100})
        time.sleep(1)
        frame = ROOT / 'client' / ('evidence-' + identifier + '.ppm')
        qmp('client', 'screendump', {'filename': str(frame)})
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if args.output.exists():
            raise RuntimeError('Preserve existing evidence; use a new screenshot filename')
        screenshot = Image.open(frame)
        if all(low == high == 0 for low, high in screenshot.convert('RGB').getextrema()):
            raise RuntimeError('The guest display is asleep; a black frame is not confirmation evidence')
        screenshot.save(args.output)
        record['screenshot_sha256'] = hashlib.sha256(args.output.read_bytes()).hexdigest()
        record['status'] = 'passed'
    except Exception as error:
        record['status'] = 'failed'
        record['error_type'] = type(error).__name__
        raise
    finally:
        cleanup = ("$t=Get-ScheduledTask -TaskName '" + task + "' -ErrorAction SilentlyContinue;"
                   "if($t){if($t.State -eq 'Running'){Stop-ScheduledTask -TaskName '" + task + "'};"
                   "Unregister-ScheduledTask -TaskName '" + task + "' -Confirm:$false}")
        response = run_ps_with_input(create_session('client'), cleanup, b'')
        record['cleanup_exit_code'] = response.status_code
        record['host_finished'] = int(time.time())
        (work / 'metadata.json').write_text(json.dumps(record, indent=2) + '\n')
        if response.status_code:
            raise RuntimeError('Evidence task cleanup failed')
    print('Actual guest screenshot: ' + str(args.output))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('Evidence screenshot stopped: ' + type(error).__name__, file=sys.stderr)
        sys.exit(1)
