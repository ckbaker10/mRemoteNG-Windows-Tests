"""The client stays signed in and unlocked for desktop evidence; no real VM is touched."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('lab_manage_no_lock', REPO / 'lab' / 'manage.py')
lab = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lab)
NS = {'u': lab.NS}


class DesktopNoLockTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        for target, name, value in [(lab, 'ROOT', Path(directory.name))]:
            patcher = patch.object(target, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        run = patch.object(lab.subprocess, 'run', side_effect=self.emulate_iso)
        run.start()
        self.addCleanup(run.stop)
        self.copy = patch.object(lab.shutil, 'copyfile').start()
        self.addCleanup(patch.stopall)

    @staticmethod
    def emulate_iso(command, **kwargs):
        if command[0] == 'xorriso':
            Path(command[command.index('-o') + 1]).touch()

    def logon_count(self, name):
        answer = ET.parse(lab.prepare(name) / 'seed' / 'autounattend.xml')
        return int(answer.find('.//u:AutoLogon/u:LogonCount', NS).text)

    def test_client_keeps_signing_in_automatically(self):
        self.assertGreater(self.logon_count('client'), 1000)

    def test_server_signs_in_only_for_bootstrap(self):
        self.assertEqual(self.logon_count('server'), 1)

    def test_seed_carries_the_no_lock_script(self):
        lab.prepare('client')
        copied = [Path(call.args[0]).name for call in self.copy.call_args_list]
        self.assertIn('Set-LabNoLock.ps1', copied)
        self.assertIn('Set-LabUpdatePolicy.ps1', copied)

    def test_bootstrap_applies_no_lock_settings_without_blocking_readiness(self):
        bootstrap = (REPO / 'lab' / 'bootstrap.ps1').read_text(encoding='utf-8-sig')
        call = bootstrap.index('Set-LabNoLock.ps1')
        self.assertLess(call, bootstrap.index('ready.txt'))
        self.assertIn('catch', bootstrap[call:bootstrap.index('ready.txt')])

    def test_bootstrap_pins_the_windows_build_without_blocking_readiness(self):
        bootstrap = (REPO / 'lab' / 'bootstrap.ps1').read_text(encoding='utf-8-sig')
        call = bootstrap.index('Set-LabUpdatePolicy.ps1')
        self.assertLess(call, bootstrap.index('ready.txt'))
        script = (REPO / 'scripts' / 'Set-LabUpdatePolicy.ps1').read_text(encoding='utf-8-sig')
        for value in ('NoAutoUpdate', 'NoAutoRebootWithLoggedOnUsers', 'SetDisableUXWUAccess'):
            self.assertIn(value, script)

    def test_no_lock_script_never_stores_a_plaintext_password(self):
        script = (REPO / 'scripts' / 'Set-LabNoLock.ps1').read_text(encoding='utf-8-sig')
        self.assertIn('LsaStorePrivateData', script)
        self.assertNotRegex(script, r"Set-ItemProperty[^\n]*DefaultPassword")
        for setting in ('standby-timeout', 'hibernate-timeout', 'monitor-timeout', 'ScreenSaverIsSecure',
                        '0e796bdb-100d-47d6-a2d5-f7d2daa51f51'):
            self.assertIn(setting, script)


if __name__ == '__main__':
    unittest.main()
