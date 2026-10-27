import importlib.util
import json
import os
import subprocess
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

LAB = Path(__file__).resolve().parents[1] / 'lab'
sys.path.insert(0, str(LAB))
spec = importlib.util.spec_from_file_location('lab_checkpoint', LAB / 'checkpoint.py')
checkpoint = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checkpoint)


class CheckpointTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        patcher = patch.object(checkpoint, 'ROOT', self.root)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.guest = self.root / 'client'
        self.guest.mkdir(mode=0o700)
        for name in checkpoint.REQUIRED:
            if name != 'disk.qcow2':
                (self.guest / name).write_text('synthetic-' + name)
        subprocess.run(['qemu-img', 'create', '-q', '-f', 'qcow2', str(self.guest / 'disk.qcow2'), '1M'], check=True)
        self.disk_io(self.guest / 'disk.qcow2', 'write -P 0x41 0 512')
        (self.guest / 'tpm').mkdir()
        (self.guest / 'tpm' / 'state').write_text('synthetic-tpm')

    def test_restore_preserves_current_state_and_firmware_tpm_pair(self):
        checkpoint.save('client', 'before-policy')
        self.disk_io(self.guest / 'disk.qcow2', 'write -P 0x42 0 512')
        (self.guest / 'tpm' / 'state').write_text('changed-tpm')
        previous = checkpoint.restore('client', 'before-policy')
        self.disk_io(previous / 'disk.qcow2', 'read -P 0x42 0 512')
        self.disk_io(self.guest / 'disk.qcow2', 'read -P 0x41 0 512')
        self.assertEqual((self.guest / 'tpm' / 'state').read_text(), 'synthetic-tpm')
        self.assertEqual((self.guest / 'OVMF_VARS.fd').read_text(), 'synthetic-OVMF_VARS.fd')

    def test_corrupted_checkpoint_cannot_replace_current_state(self):
        saved = checkpoint.save('client', 'before-policy')
        unchanged = checkpoint.digest(self.guest / 'disk.qcow2')
        os.chmod(saved / 'disk.qcow2', 0o600)
        (saved / 'disk.qcow2').write_text('corrupt')
        with self.assertRaises(RuntimeError):
            checkpoint.restore('client', 'before-policy')
        self.assertEqual(checkpoint.digest(self.guest / 'disk.qcow2'), unchanged)

    @staticmethod
    def disk_io(path, command):
        subprocess.run(['qemu-io', '-f', 'qcow2', '-c', command, str(path)], check=True, capture_output=True)

    def test_running_guest_is_refused(self):
        (self.guest / 'qemu.pid').write_text(str(os.getpid()))
        with self.assertRaises(RuntimeError):
            checkpoint.save('client', 'unsafe')

    def test_multiple_checkpoints_restore_the_pinned_virtual_disk_chain(self):
        checkpoint.save('client', 'first')
        self.disk_io(self.guest / 'disk.qcow2', 'write -P 0x42 0 512')
        second = checkpoint.save('client', 'second')
        manifest = json.loads((second / 'manifest.json').read_text())
        self.assertEqual(len(manifest['backing_chain']), 2)
        self.disk_io(self.guest / 'disk.qcow2', 'write -P 0x43 0 512')
        checkpoint.restore('client', 'second')
        self.disk_io(self.guest / 'disk.qcow2', 'read -P 0x42 0 512')
        checkpoint.restore('client', 'first')
        self.disk_io(self.guest / 'disk.qcow2', 'read -P 0x41 0 512')

    def test_tampering_with_an_older_backing_file_is_rejected(self):
        first = checkpoint.save('client', 'first')
        checkpoint.save('client', 'second')
        unchanged = checkpoint.digest(self.guest / 'disk.qcow2')
        os.chmod(first / 'disk.qcow2', 0o600)
        self.disk_io(first / 'disk.qcow2', 'write -P 0x44 0 512')
        with self.assertRaises(RuntimeError):
            checkpoint.restore('client', 'second')
        self.assertEqual(checkpoint.digest(self.guest / 'disk.qcow2'), unchanged)

    def test_linked_backing_files_are_refused(self):
        link = self.root / 'linked.qcow2'
        link.symlink_to(self.guest / 'disk.qcow2')
        with self.assertRaises(RuntimeError):
            checkpoint.image_chain(link)


if __name__ == '__main__':
    unittest.main()
