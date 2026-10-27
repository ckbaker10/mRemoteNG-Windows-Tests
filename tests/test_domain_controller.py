import base64
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

LAB = Path(__file__).resolve().parents[1] / 'lab'
sys.path.insert(0, str(LAB))
spec = importlib.util.spec_from_file_location('domain_controller', LAB / 'domain_tests.py')
controller = importlib.util.module_from_spec(spec)
spec.loader.exec_module(controller)


class DomainControllerTests(unittest.TestCase):
    def run_controller(self, process_exit=0, completion=True):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'scripts').mkdir()
            for name in ('Get-LabStatus.ps1', 'Invoke-DomainGpoTests.ps1', 'LabUserRights.cs'):
                (root / 'scripts' / name).write_text('synthetic ' + name)
            def streamed(session, script, payload):
                if script.startswith('Add-Type'):
                    return SimpleNamespace(status_code=process_exit, std_out=b'synthetic run', std_err=b'')
                data = b''
                if completion and script.count('result.json') and 'standard' not in script:
                    data = base64.b64encode(b'{"Status":"passed"}')
                return SimpleNamespace(status_code=0, std_out=data, std_err=b'')
            session = SimpleNamespace(run_ps=lambda script: SimpleNamespace(status_code=0, std_out=b'{"BootstrapReady":true}'))
            with patch.object(controller, 'REPO', root), patch.object(controller, 'create_session', return_value=session), \
                    patch.object(controller, 'run_ps_with_input', side_effect=streamed), \
                    patch.object(sys, 'argv', ['domain_tests.py', r'C:\mrng-lab\transfer\synthetic\PolicyProbe.dll',
                                              '208236a8-d2dc-402a-b5fc-3bf6c386b077']):
                if process_exit or not completion:
                    with self.assertRaises(RuntimeError):
                        controller.main()
                else:
                    controller.main()
            output = next((root / 'work').iterdir())
            self.assertTrue((output / 'stdout.log').exists())
            return json.loads((output / 'metadata.json').read_text())

    def test_zero_exit_without_explicit_completion_is_rejected(self):
        self.assertEqual(self.run_controller(completion=False)['status'], 'failed')

    def test_failure_exit_cannot_be_overridden_by_passed_json(self):
        self.assertEqual(self.run_controller(process_exit=1)['status'], 'failed')

    def test_success_requires_completion_and_preserves_policy_identity(self):
        result = self.run_controller()
        self.assertEqual(result['status'], 'passed')
        self.assertEqual(result['gpo_id'], '208236a8-d2dc-402a-b5fc-3bf6c386b077')


if __name__ == '__main__':
    unittest.main()
