"""Run a local script on an owned guest through encrypted NTLM WinRM."""
import argparse
import base64
import json
import os
from pathlib import Path
import sys
import winrm

def create_session(machine):
    root = Path(os.environ.get('MRNG_LAB_ROOT', Path(__file__).resolve().parents[1] / 'work' / 'windows-lab')).resolve()
    account = json.loads((root / machine / 'credentials.json').read_text())
    port = 55985 if machine == 'client' else 55986
    return winrm.Session(f'http://127.0.0.1:{port}/wsman',
        auth=(account['username'], account['password']), transport='ntlm',
        message_encryption='always', operation_timeout_sec=30, read_timeout_sec=180)


def run_ps_with_input(session, script, payload):
    """Send data through encrypted stdin; never place it in script/command arguments."""
    if len(payload) > 65536:
        raise ValueError('Input exceeds the bounded lab message size')
    loader = ("$ProgressPreference='SilentlyContinue';[Console]::InputEncoding=[Text.Encoding]::UTF8;"
              "$e=[Console]::In.ReadToEnd()|ConvertFrom-Json;"
              "[Console]::SetIn([IO.StringReader]::new([Text.Encoding]::UTF8.GetString("
              "[Convert]::FromBase64String($e.input))));&([ScriptBlock]::Create($e.script))")
    encoded = base64.b64encode(loader.encode('utf-16-le')).decode('ascii')
    envelope = json.dumps({'script': script, 'input': base64.b64encode(payload).decode('ascii')}).encode('ascii')
    if len(envelope) > 65536:
        raise ValueError('Script and input exceed the bounded lab message size')
    protocol = session.protocol
    shell = protocol.open_shell(noprofile=True, codepage=65001)
    command = None
    try:
        command = protocol.run_command(shell, 'powershell.exe',
            ['-NoProfile', '-NonInteractive', '-EncodedCommand', encoded],
            console_mode_stdin=False, skip_cmd_shell=True)
        protocol.send_command_input(shell, command, envelope, end=True)
        return winrm.Response(protocol.get_command_output(shell, command))
    finally:
        try:
            if command is not None:
                protocol.cleanup_command(shell, command)
        finally:
            protocol.close_shell(shell)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('machine', choices=['client', 'server'])
    parser.add_argument('script', type=Path)
    parser.add_argument('--input-file', type=Path)
    args = parser.parse_args()
    try:
        script = args.script.read_text(encoding='utf-8-sig')
        session = create_session(args.machine)
        result = (run_ps_with_input(session, script, args.input_file.read_bytes()) if args.input_file
                  else session.run_ps(script))
    except Exception as error:
        # Credentials and transport payloads must never enter diagnostic logs.
        print(f'Guest request failed: {type(error).__name__}', file=sys.stderr)
        sys.exit(2)
    sys.stdout.buffer.write(result.std_out)
    sys.stderr.buffer.write(result.std_err)
    sys.exit(result.status_code)
