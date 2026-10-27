import base64
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lab'))
from remote import run_ps_with_input


class EncryptedInputTests(unittest.TestCase):
    def setUp(self):
        self.protocol = Mock()
        self.protocol.open_shell.return_value = 'shell'
        self.protocol.run_command.return_value = 'command'
        self.protocol.get_command_output.return_value = (b'validated', b'', 0)
        self.session = SimpleNamespace(protocol=self.protocol)

    def test_payload_is_sent_through_stdin_without_command_line_copy(self):
        payload = b'{"synthetic":"stdin-only-value"}'
        result = run_ps_with_input(self.session, '[Console]::In.ReadToEnd() | Out-Null', payload)
        self.assertEqual(result.status_code, 0)
        arguments = self.protocol.run_command.call_args.args[2]
        decoded = base64.b64decode(arguments[-1]).decode('utf-16-le')
        self.assertNotIn('stdin-only-value', decoded)
        sent = self.protocol.send_command_input.call_args
        self.assertEqual(sent.args[:2], ('shell', 'command'))
        envelope = json.loads(sent.args[2])
        self.assertEqual(base64.b64decode(envelope['input']), payload)
        self.assertNotIn('stdin-only-value', envelope['script'])
        self.assertTrue(sent.kwargs['end'])
        self.protocol.cleanup_command.assert_called_once_with('shell', 'command')
        self.protocol.close_shell.assert_called_once_with('shell')

    def test_transport_error_still_closes_the_remote_command_and_shell(self):
        self.protocol.get_command_output.side_effect = RuntimeError('synthetic transport error')
        with self.assertRaises(RuntimeError):
            run_ps_with_input(self.session, '[Console]::In.ReadToEnd() | Out-Null', b'synthetic')
        self.protocol.cleanup_command.assert_called_once_with('shell', 'command')
        self.protocol.close_shell.assert_called_once_with('shell')
