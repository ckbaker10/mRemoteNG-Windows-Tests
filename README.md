mRemoteNG Windows tests

Windows build, password-dialog and GPO tests for the mRemoteNG security branches.
Application-control enforcement remains unverified.

The product changes stay in [mRemoteNG](https://github.com/ckbaker10/mRemoteNG).
This repository contains the lab and acceptance tests.

Run these commands from this repository on a Linux host with KVM, QEMU, swtpm,
Microsoft OVMF firmware, xorriso and uv. The two guests use 20 GB RAM in total.
The default firmware paths match Ubuntu.

```bash
uv venv --python 3.13.15 .venv
uv pip sync --python .venv/bin/python requirements.txt --require-hashes
export MRNG_LAB_ROOT="$PWD/work/windows-lab"
.venv/bin/python -m unittest discover -s tests -v
```

For the existing lab on mediaserv, use
`export MRNG_LAB_ROOT=/opt/paseo-development/mRemoteNG/work/windows-lab` instead.

For a fresh lab, put the official Windows 11 Enterprise and Server 2025 evaluation
ISOs under `$MRNG_LAB_ROOT/media/windows11.iso` and `server2025.iso`. Then:

```bash
.venv/bin/python lab/manage.py start server
.venv/bin/python lab/manage.py boot server
.venv/bin/python lab/manage.py start client
.venv/bin/python lab/manage.py boot client
```

Use `boot` only for the first installation. Finish Windows setup and wait for
`BootstrapReady` from the status command. Setup details and ISO links are in
[docs/LAB.md](docs/LAB.md).

```bash
.venv/bin/python lab/remote.py client scripts/Get-LabStatus.ps1
.venv/bin/python lab/remote.py client scripts/Clear-LabSetupSecrets.ps1
.venv/bin/python lab/manage.py seal client
.venv/bin/python lab/remote.py client scripts/Initialize-BuildClient.ps1
.venv/bin/python lab/remote.py server scripts/Clear-LabSetupSecrets.ps1
.venv/bin/python lab/manage.py seal server
```

Run the unit tests before enabling the lab GPO. On an already joined client,
use the baseline switch in [docs/LAB.md](docs/LAB.md) first.

Create the input archives from committed sources. In a separate terminal, serve
only `work/transfer` with `python3 -m http.server 55987 --bind 127.0.0.1 --directory work/transfer`.

```bash
PRODUCT_COMMIT=7441b3a7f9688faac3254b9912469eb7b37c2203
RUN_CONFIG=$(.venv/bin/python lab/package_inputs.py ../mRemoteNG "$PRODUCT_COMMIT")
SOURCE_RESULT=$(.venv/bin/python lab/continue_client.py "$RUN_CONFIG" --resume-installed)
printf '%s\n' "$SOURCE_RESULT"
GUEST_RUN=${SOURCE_RESULT##*guest artifacts: }
HARNESS_ARCHIVE=$(.venv/bin/python -c 'import json,sys; print(json.load(open(sys.argv[1]))["harness_archive"])' "$RUN_CONFIG")
HARNESS_SHA=$(.venv/bin/python -c 'import json,sys; print(json.load(open(sys.argv[1]))["harness_sha256"])' "$RUN_CONFIG")
PROBE_DLL=$(.venv/bin/python lab/transfer_probe.py "$HARNESS_ARCHIVE" "$HARNESS_SHA" "$GUEST_RUN\source" --print-path-only)
```

Sign in as the local LabAdmin on the client, then run the dialog tests:

```bash
.venv/bin/python lab/interactive_tests.py "$GUEST_RUN" "$PROBE_DLL"
```

Set up the isolated domain after taking a server checkpoint:

```bash
.venv/bin/python lab/remote.py server scripts/Initialize-LabDomainRole.ps1
.venv/bin/python lab/promote_server.py
# Wait for the server restart.
.venv/bin/python lab/remote.py server scripts/Initialize-LabGpo.ps1
.venv/bin/python lab/remote.py client scripts/Initialize-LabClientNetwork.ps1
.venv/bin/python lab/join_client.py
# Wait for the client restart.
.venv/bin/python lab/domain_tests.py "$PROBE_DLL"
MRNG_RUN_NATIVE=1 .venv/bin/python -m unittest discover -s tests -p test_native_transport.py -v
```

The domain is `mrng.test`. Policy changes are limited to its own test OU.
WinRM uses encrypted NTLM messages. Credentials, ISOs, VM state and raw evidence
stay in ignored `work/` directories. The test account and S4U task are removed
after each standard-user run.
