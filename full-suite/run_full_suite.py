"""Run the complete, unfiltered mRemoteNGTests project per branch in the lab client's desktop.

Usage: run_full_suite.py <environment-label> <product-repo> <branch>[=<commit>]...
Raw results go to work/full-suite/<environment-label>/; nothing outside the owned lab is touched.
"""
import base64
import hashlib
import json
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'lab'))
from remote import create_session, run_ps_with_input  # noqa: E402

HERE = Path(__file__).resolve().parent
RUNNER = HERE / 'Run-FullTests.ps1'
SHOW = HERE / 'Show-FullSuiteResult.ps1'
CAPTURE = HERE / 'Save-WindowImage.ps1'
TRANSFER = REPO / 'work' / 'transfer'
TRANSFER_URL = 'http://10.0.2.2:55987/'


def lab_root():
    import os
    return Path(os.environ.get('MRNG_LAB_ROOT', REPO / 'work' / 'windows-lab')).resolve()


def qmp(command, arguments=None):
    client = socket.socket(socket.AF_UNIX)
    client.connect(str(lab_root() / 'client' / 'qmp.sock'))
    stream = client.makefile('rwb', buffering=0)
    stream.readline()
    for request in ({'execute': 'qmp_capabilities'}, {'execute': command, 'arguments': arguments or {}}):
        stream.write(json.dumps(request).encode() + b'\n')
        while True:
            response = json.loads(stream.readline())
            if 'error' in response:
                raise RuntimeError(response['error'])
            if 'return' in response:
                break
    client.close()


def ps(script, payload=b''):
    result = run_ps_with_input(create_session('client'), script, payload)
    if result.status_code:
        raise RuntimeError('Guest step failed: ' + result.std_err.decode('utf-8', 'replace')[-2000:])
    return result.std_out.decode('utf-8-sig').strip()


def interactive_task(name, arguments, hours=3):
    return f"""
$action = New-ScheduledTaskAction -Execute "$env:SystemRoot\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Argument '{arguments}'
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\\$env:USERNAME" -LogonType Interactive -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours {hours})
Register-ScheduledTask -TaskName '{name}' -Action $action -Principal $principal -Settings $settings | Out-Null
Start-ScheduledTask -TaskName '{name}'
"""


def remove_task(name):
    ps(f"if(Get-ScheduledTask -TaskName '{name}' -ErrorAction SilentlyContinue){{"
       f"if((Get-ScheduledTask -TaskName '{name}').State -eq 'Running'){{Stop-ScheduledTask -TaskName '{name}'}};"
       f"Unregister-ScheduledTask -TaskName '{name}' -Confirm:$false}}")


def screenshot(run, branch, environment, out):
    """Show the recorded result in a console in session 1 and capture that window."""
    token = uuid.uuid4().hex
    title = 'mRemoteNG full test suite ' + token
    show, cap, png = run + '\\Show-FullSuiteResult.ps1', run + '\\Save-WindowImage.ps1', run + '\\desktop-' + token + '.png'
    for path, source in ((show, SHOW), (cap, CAPTURE)):
        ps(f"[IO.File]::WriteAllText('{path}', [Console]::In.ReadToEnd(), [Text.UTF8Encoding]::new($true))", source.read_bytes())
    console = f'conhost.exe powershell.exe -NoProfile -NoExit -ExecutionPolicy Bypass -File "{show}" -Run "{run}" -Branch "{branch}" -Environment "{environment}" -Title "{title}"'
    show_task, cap_task = 'mRemoteNG-Lab-FullShow-' + token, 'mRemoteNG-Lab-FullCap-' + token
    ps(f"""
$action = New-ScheduledTaskAction -Execute "$env:SystemRoot\\System32\\cmd.exe" -Argument '/c start "" {console.replace("'", "''")}'
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\\$env:USERNAME" -LogonType Interactive -RunLevel Highest
Register-ScheduledTask -TaskName '{show_task}' -Action $action -Principal $principal | Out-Null
Start-ScheduledTask -TaskName '{show_task}'
""")
    try:
        ps(interactive_task(cap_task, f'-NoProfile -ExecutionPolicy Bypass -File "{cap}" -Title "{title}" -OutFile "{png}"', hours=1))
        for _ in range(45):
            time.sleep(2)
            if ps(f"Test-Path '{png}'") == 'True' and ps(f"(Get-ScheduledTask -TaskName '{cap_task}').State") != 'Running':
                break
        data = ps(f"if(Test-Path '{png}'){{[Convert]::ToBase64String([IO.File]::ReadAllBytes('{png}'))}}")
        if not data:
            raise RuntimeError('No window image was produced')
        Path(out).write_bytes(base64.b64decode(data))
        if ps("@(Get-Process LogonUI -ErrorAction SilentlyContinue | Where-Object SessionId -ne 0).Count") == '0':
            # Unlocked desktop: also keep the unmodified full screen with the result window in front.
            qmp('send-key', {'keys': [{'type': 'qcode', 'data': 'ctrl'}], 'hold-time': 100})
            time.sleep(2)
            frame = lab_root() / 'client' / ('full-suite-' + token + '.ppm')
            qmp('screendump', {'filename': str(frame)})
            Image.open(frame).save(Path(out).with_name('desktop.png'))  # format conversion only
            frame.unlink()
    finally:
        remove_task(cap_task)
        remove_task(show_task)
        ps(f"Get-CimInstance Win32_Process -Filter \"Name='powershell.exe'\" | Where-Object CommandLine -like '*{token}*' | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force }}")


def run_branch(environment, product, spec):
    ref, _, pinned = spec.partition('=')
    commit = subprocess.check_output(['git', '-C', str(product), 'rev-parse', pinned or ref], text=True).strip()
    label = ref.replace('/', '_')
    out = REPO / 'work' / 'full-suite' / environment / f'{label}-{commit[:8]}-{uuid.uuid4().hex[:6]}'
    out.mkdir(parents=True)
    rec = {'environment': environment, 'ref': ref, 'commit': commit, 'host_started': int(time.time()),
           'runner_sha256': hashlib.sha256(RUNNER.read_bytes()).hexdigest(),
           'show_sha256': hashlib.sha256(SHOW.read_bytes()).hexdigest(),
           'capture_sha256': hashlib.sha256(CAPTURE.read_bytes()).hexdigest()}
    save = lambda: (out / 'metadata.json').write_text(json.dumps(rec, indent=2) + '\n')
    name = f'mRemoteNG-full-{commit}.zip'
    archive = TRANSFER / name
    if not archive.exists():
        cmd = ['git', '-C', str(product), 'archive', '--format=zip', '--output=' + str(archive), commit]
        subprocess.run(cmd, check=True)
    rec['archive_command'] = ['git', 'archive', '--format=zip', commit]
    sha = hashlib.sha256(archive.read_bytes()).hexdigest()
    rec['archive_sha256'] = sha
    task = 'mRemoteNG-Lab-Full-' + uuid.uuid4().hex
    rec['task'] = task
    save()
    run = ps(f"""
$run = 'C:\\mrng-lab\\runs\\full-{commit[:12]}-{uuid.uuid4().hex}'
New-Item -ItemType Directory $run | Out-Null
$zip = Join-Path $run '{name}'
Invoke-WebRequest '{TRANSFER_URL}{name}' -OutFile $zip
if ((Get-FileHash $zip -Algorithm SHA256).Hash -ne '{sha}') {{ throw 'hash mismatch' }}
[IO.File]::WriteAllText((Join-Path $run 'Run-FullTests.ps1'), [Console]::In.ReadToEnd(), [Text.UTF8Encoding]::new($true))
$run
""", RUNNER.read_bytes())
    args = (f'-NoProfile -ExecutionPolicy Bypass -File "{run}\\Run-FullTests.ps1" -Run "{run}" '
            f'-SourceArchive "{run}\\{name}" -ArchiveSha256 {sha} -SourceCommit {commit}')
    ps(interactive_task(task, args))
    rec['guest_run'] = run
    save()
    deadline = time.time() + 3 * 3600 + 600
    try:
        while time.time() < deadline:
            time.sleep(60)
            try:
                state = ps(f"$s=(Get-ScheduledTask -TaskName '{task}').State; $r=Test-Path '{run}\\result.json'; \"$s $r\"")
            except Exception:
                continue
            if state.split()[0] != 'Running' and state.endswith('True'):
                break
        else:
            rec['status'] = 'timeout'
    finally:
        remove_task(task)
    for f in ('result.json', 'test.log', 'list.log', 'build.log', 'tests.trx'):
        data = ps(f"if(Test-Path '{run}\\{f}'){{[Convert]::ToBase64String([IO.File]::ReadAllBytes('{run}\\{f}'))}}")
        if data:
            (out / f).write_bytes(base64.b64decode(data))
    rec['result'] = json.loads((out / 'result.json').read_text(encoding='utf-8-sig'))
    rec.setdefault('status', rec['result'].get('Status'))
    try:
        screenshot(run, ref, environment, out / 'result-window.png')
        rec['screenshot'] = 'result-window.png'
        if (out / 'desktop.png').exists():
            rec['desktop_screenshot'] = 'desktop.png'
    except Exception as error:
        rec['screenshot_error'] = type(error).__name__ + ': ' + str(error)[:200]
    rec['host_finished'] = int(time.time())
    save()
    print(ref, rec['status'], out, flush=True)


if __name__ == '__main__':
    env, product = sys.argv[1], Path(sys.argv[2]).resolve()
    for ref in sys.argv[3:]:
        try:
            run_branch(env, product, ref)
        except Exception as e:
            print(ref, 'controller-error', type(e).__name__, str(e)[:500], flush=True)
