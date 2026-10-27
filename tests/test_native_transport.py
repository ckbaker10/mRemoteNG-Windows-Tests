"""Opt-in checks against the owned Windows server, using synthetic data only."""
import os
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lab'))
from remote import create_session, run_ps_with_input, bind_parameters


@unittest.skipUnless(os.environ.get('MRNG_RUN_NATIVE') == '1', 'Requires the owned Windows lab')
class NativeTransportTests(unittest.TestCase):
    def test_typed_parameters_and_separate_stdin_reach_the_script(self):
        import json
        script, payload = bind_parameters(
            'param([string]$Name,[switch]$Enabled);[pscustomobject]@{Name=$Name;Enabled=[bool]$Enabled;Input=[Console]::In.ReadToEnd()}|ConvertTo-Json',
            {'Name': 'synthetic-parameter', 'Enabled': False}, b'synthetic-input')
        result = run_ps_with_input(create_session('server'), script, payload)
        self.assertEqual(result.status_code, 0)
        self.assertEqual(json.loads(result.std_out), {'Name': 'synthetic-parameter', 'Enabled': False, 'Input': 'synthetic-input'})

    def test_windows_profile_supports_task_scheduler_com(self):
        result = run_ps_with_input(create_session('server'),
            "$s=New-Object -ComObject Schedule.Service;$s.Connect();$s.GetFolder('\\').Path", b'')
        self.assertEqual(result.status_code, 0)
        self.assertEqual(result.std_out.decode('utf-8-sig').strip(), '\\')

    def test_terminating_script_error_has_failed_process_exit(self):
        result = run_ps_with_input(create_session('server'), "throw 'Synthetic transport failure'", b'')
        self.assertNotEqual(result.status_code, 0)
        self.assertIn(b'Synthetic transport failure', result.std_err)

    def test_nested_script_error_cannot_be_reported_as_success(self):
        result = run_ps_with_input(create_session('server'),
                                   "& { Get-Item -LiteralPath 'C:\\mrng-lab\\synthetic-absent-transport-path' }; 'unreachable'", b'')
        self.assertNotEqual(result.status_code, 0)
        self.assertNotIn(b'unreachable', result.std_out)

    def test_utf8_stdin_survives_the_small_command_loader(self):
        value = 'synthetic-äöü-🔐'
        result = run_ps_with_input(create_session('server'),
                                   '[Console]::OutputEncoding=[Text.Encoding]::UTF8;[Console]::Write([Console]::In.ReadToEnd())',
                                   value.encode('utf-8'))
        self.assertEqual(result.status_code, 0)
        self.assertEqual(result.std_out.decode('utf-8-sig'), value)


if __name__ == '__main__':
    unittest.main()
