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
spec = importlib.util.spec_from_file_location('client_continuation', LAB / 'continue_client.py')
controller = importlib.util.module_from_spec(spec)
spec.loader.exec_module(controller)


class ClientContinuationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / 'scripts').mkdir()
        for name in ('Get-LabStatus', 'Clear-LabSetupSecrets', 'Initialize-BuildClient'):
            (self.root / 'scripts' / (name + '.ps1')).write_text(name)
        self.config = self.root / 'config.json'
        self.config.write_text(json.dumps({
            'source_commit': 'a' * 40, 'harness_commit': 'b' * 40,
            'source_sha256': 'c' * 64, 'harness_sha256': 'd' * 64,
            'source_archive': 'source.zip'
        }))
        patcher = patch.object(controller, 'REPO', self.root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_controller(self, fail_build=False, fail_source=False):
        calls = []
        def run_ps(script):
            calls.append(script)
            if script == 'Get-LabStatus':
                return SimpleNamespace(status_code=0, std_out=b'{"BootstrapReady":true}', std_err=b'')
            if script == 'Initialize-BuildClient' and fail_build:
                return SimpleNamespace(status_code=1, std_out=b'', std_err=b'synthetic failure')
            if 'Invoke-SourceTests.ps1' in script:
                return SimpleNamespace(status_code=int(fail_source), std_out=(
                    'Run artifacts: C:\\mrng-lab\\runs\\' + 'a' * 12 + '-' + 'e' * 32
                ).encode(), std_err=b'')
            if 'ToBase64String' in script:
                return SimpleNamespace(status_code=0, std_out=base64.b64encode(b'synthetic artifact'), std_err=b'')
            return SimpleNamespace(status_code=0, std_out=b'', std_err=b'')
        with patch.object(controller, 'create_session', return_value=SimpleNamespace(run_ps=run_ps)), \
                patch.object(controller.subprocess, 'run') as seal, \
                patch.object(sys, 'argv', ['continue_client.py', str(self.config)]):
            if fail_build or fail_source:
                with self.assertRaises(RuntimeError):
                    controller.main()
            else:
                controller.main()
            seal.assert_called_once()
        record_file = next((self.root / 'work').glob('*/controller.json'))
        return json.loads(record_file.read_text()), calls, record_file.parent

    def test_failed_installation_stops_before_source_tests(self):
        record, calls, _ = self.run_controller(fail_build=True)
        self.assertEqual(record['status'], 'failed')
        self.assertFalse(any('Invoke-SourceTests.ps1' in script for script in calls))

    def test_success_preserves_provenance_and_fetches_artifacts(self):
        record, calls, output = self.run_controller()
        self.assertEqual(record['status'], 'passed-source-tests')
        source_script = next(script for script in calls if 'Invoke-SourceTests.ps1' in script)
        self.assertIn('c' * 64, source_script)
        self.assertIn('d' * 64, source_script)
        self.assertTrue((output / 'tests.trx').exists())
        self.assertTrue((output / 'result.json').exists())

    def test_failed_source_build_retains_diagnostics_and_failed_status(self):
        record, _, output = self.run_controller(fail_source=True)
        self.assertEqual(record['status'], 'failed')
        self.assertEqual(record['phase'], 'source-tests')
        self.assertTrue((output / 'build.log').exists())
        self.assertTrue((output / 'result.json').exists())


if __name__ == '__main__':
    unittest.main()
