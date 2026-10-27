Manual lab run

Use the README commands from a clean checkout next to the mRemoteNG source
repository. Keep the source commit and archive hashes with the results.

Download the official evaluation media:
[Windows 11 Enterprise](https://www.microsoft.com/en-us/evalcenter/evaluate-windows-11-enterprise)
and [Windows Server 2025](https://www.microsoft.com/en-us/evalcenter/evaluate-windows-server-2025).
Store them as `media/windows11.iso` and `media/server2025.iso` under MRNG_LAB_ROOT.
Record their SHA-256 hashes. Media and VM state stay outside Git.

The firmware paths in lab/manage.py use Ubuntu's OVMF_CODE_4M.ms.fd and matching
OVMF_VARS_4M.ms.fd. The guests use KVM, TPM 2.0, Secure Boot and separate NAT and
private NICs. Management binds to 127.0.0.1:55985 and :55986. The private guest
connection uses :55990. The archive server binds to 127.0.0.1:55987.

Finish the Windows setup screens when required. Select the US keyboard and skip
the second keyboard. The initial OOBEREGION error can be skipped. After the
first LabAdmin logon, bootstrap enables encrypted WinRM. Check BootstrapReady,
clear setup secrets and seal both guests as shown in the README.

The Build Tools installer must have a valid Microsoft signature. The source
project uses COM references, so build with Windows Framework MSBuild. The lab
installs Visual Studio 2026 Build Tools and .NET 10. An installed-tools resume
checks the installer record, hash, signature, MSBuild and SDK again.

Existing joined lab

The baseline NUnit tests and registry matrix run without the application GPO.
Temporarily disable only the owned lab link and refresh the client:

```bash
mkdir -p work
printf '{"Enabled":false}\n' > work/gpo-off.json
printf '{"ExpectManaged":false}\n' > work/baseline.json
.venv/bin/python lab/remote.py server scripts/Set-LabGpoLink.ps1 --parameters-file work/gpo-off.json
.venv/bin/python lab/remote.py client scripts/Refresh-LabPolicy.ps1 --parameters-file work/baseline.json
```

Run the source, probe and interactive commands from the README. Then restore
the owned link, including after a failed baseline run:

```bash
printf '{"Enabled":true}\n' > work/gpo-on.json
printf '{"ExpectManaged":true}\n' > work/managed.json
.venv/bin/python lab/remote.py server scripts/Set-LabGpoLink.ps1 --parameters-file work/gpo-on.json
.venv/bin/python lab/remote.py client scripts/Refresh-LabPolicy.ps1 --parameters-file work/managed.json
.venv/bin/python lab/domain_tests.py "$PROBE_DLL"
```

The source controller prints GUEST_RUN. transfer_probe.py prints the probe path.
Keep RUN_CONFIG, GUEST_RUN and PROBE_DLL in the shell until the run is complete.
Reusing an existing archive is allowed; package_inputs.py refuses to overwrite
one. Use its existing run configuration for a repeat run.

Interactive desktop

The password-dialog tests need the local LabAdmin desktop. After a reboot,
select LabAdmin, turn Caps Lock off and focus its password field. This helper
reads the protected host credential file and types paced scan codes:

```bash
.venv/bin/python lab/manage.py vnc-key client --key ret
.venv/bin/python lab/sign_in.py
# For an existing locked desktop, use lab/sign_in.py --unlock instead.
.venv/bin/python lab/interactive_tests.py "$GUEST_RUN" "$PROBE_DLL"
```

The sign-in helper refuses an already unlocked desktop. The dialog runner uses
an interactive-token task, validates a nonempty passed TRX and removes its task.

Domain and policy templates

promote_server.py creates only mrng.test. Its separate recovery password stays
in the protected server credential file. join_client.py uses encrypted stdin
for the domain credential and keeps WinRM on the local client account. It also
aligns both guest clocks with the host. New guests use UTC for their QEMU RTC.

The test GPO applies only to OU=mRemoteNG-Lab,DC=mrng,DC=test. It requires 16
characters and four character classes, full AES/GCM encryption and 100000 KDF
iterations. Persistent unlock and secret exports are disabled. These are lab
test values.

Install-LabPolicyTemplates.ps1 takes SourceArchive, ArchiveSha256 and SourceCommit.
It copies the three pinned ADMX/ADML files into the isolated Central Store and
rejects different existing contents. Pass script parameters as JSON:

```bash
.venv/bin/python - "$RUN_CONFIG" <<'PY'
import json, sys
from pathlib import Path
run = json.loads(Path(sys.argv[1]).read_text())
archive = run['source_archive']
Path('work/template-parameters.json').write_text(json.dumps({
    'SourceArchive': 'C:\\mrng-lab\\transfer\\' + archive,
    'ArchiveSha256': run['source_sha256'], 'SourceCommit': run['source_commit'],
    'ArchiveUrl': 'http://10.0.2.2:55987/' + archive
}, indent=2))
PY
.venv/bin/python lab/remote.py server scripts/Install-LabPolicyTemplates.ps1 --parameters-file work/template-parameters.json
```

domain_tests.py checks the secure channel, refreshes computer policy and records
gpresult.xml. It runs the product probe with administrator and standard-user
tokens. The temporary standard account gets only batch-logon permission. Its
S4U task does not store a password. The account, task and temporary right are
removed afterwards.

Checkpoints and application control

Shut down the guest before saving a checkpoint. Stop only its own TPM emulator
if it is still running:

```bash
.venv/bin/python lab/remote.py client scripts/Stop-LabGuest.ps1
# Wait for the QEMU PID to exit.
swtpm_ioctl --unix "$MRNG_LAB_ROOT/client/tpm.sock" -s
.venv/bin/python lab/checkpoint.py save client before-app-control
```

Skip the ioctl command if the owning systemd unit already stopped swtpm. Use a
new checkpoint name for another snapshot. The checkpoint pins the full qcow2
backing chain, firmware and TPM state. Keep the files at their original paths.
Restore is `lab/checkpoint.py restore client before-app-control`; it preserves
the current state under a separate directory. Verify a real guest rollback
before enabling application-control enforcement.

Get-AppControlLabStatus.ps1 records ConfigCI, CiTool and active policies.
Invoke-PinnedScript.ps1 runs an extracted lab script after checking its SHA-256.
Its ScriptPath, ScriptSha256 and Parameters come from the pinned source archive.
The release and App Control tools remain in the product repository under
tools/enterprise. A generated policy is not an enforcement result.

Evidence

The controllers keep raw logs, TRX, result JSON, source hashes and host times in
work. evidence_screen.py displays an actual guest result on the unlocked desktop
and captures that screen. The screenshots use the original pixels; only the
file format changes from PPM to PNG. Review each screenshot before publishing it.
Credentials and setup answer files are excluded from confirmation evidence.
