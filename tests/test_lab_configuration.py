"""Host-side regression checks; these do not boot or modify any real VM."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

SOURCE = Path(__file__).resolve().parents[1] / 'lab' / 'manage.py'
spec = importlib.util.spec_from_file_location('lab_manage', SOURCE)
lab = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lab)
NS = {'u': lab.NS}


class LabConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.root_patch = patch.object(lab, 'ROOT', self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)
        self.run_patch = patch.object(lab.subprocess, 'run')
        self.run = self.run_patch.start()
        def emulate_iso(command, **kwargs):
            if command[0] == 'xorriso':
                Path(command[command.index('-o') + 1]).touch()
        self.run.side_effect = emulate_iso
        self.addCleanup(self.run_patch.stop)
        self.copy_patch = patch.object(lab.shutil, 'copyfile')
        self.copy_patch.start()
        self.addCleanup(self.copy_patch.stop)

    def test_partition_action_order_is_independent_of_partition_id(self):
        target = lab.prepare('client')
        answer = ET.parse(target / 'seed' / 'autounattend.xml')
        for group, child in [('CreatePartitions', 'CreatePartition'), ('ModifyPartitions', 'ModifyPartition')]:
            actions = answer.findall(f'.//u:{group}/u:{child}', NS)
            orders = [int(action.find('u:Order', NS).text) for action in actions]
            self.assertEqual(orders, list(range(1, len(orders) + 1)))
        actions = answer.findall('.//u:ModifyPartition', NS)
        self.assertEqual([a.find('u:PartitionID', NS).text for a in actions], ['1', '3'])

    def test_seed_uses_long_filenames_and_protected_credentials(self):
        target = lab.prepare('server')
        self.assertEqual((target / 'credentials.json').stat().st_mode & 0o777, 0o600)
        self.assertEqual((target / 'seed' / 'autounattend.xml').stat().st_mode & 0o777, 0o600)
        iso_command = next(c.args[0] for c in self.run.call_args_list if c.args[0][0] == 'xorriso')
        self.assertIn('-J', iso_command)

    def test_management_is_loopback_and_guest_macs_are_unique(self):
        addresses = set()
        for machine in ('server', 'client'):
            lab.start(machine)
            command = next(c.args[0] for c in reversed(self.run.call_args_list)
                           if c.args[0][0] == 'qemu-system-x86_64')
            self.assertTrue(any('hostfwd=tcp:127.0.0.1:' in value for value in command))
            self.assertTrue(any('=127.0.0.1:55990' in value for value in command))
            for value in command:
                if value.startswith('e1000e,'):
                    address = value.split('mac=')[1]
                    self.assertNotIn(address, addresses)
                    addresses.add(address)
        self.assertEqual(len(addresses), 4)


if __name__ == '__main__':
    unittest.main()
