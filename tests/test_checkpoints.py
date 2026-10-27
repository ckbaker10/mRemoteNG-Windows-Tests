import importlib.util
import os
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
            (self.guest / name).write_text('synthetic-' + name)
        (self.guest / 'tpm').mkdir()
        (self.guest / 'tpm' / 'state').write_text('synthetic-tpm')

    def test_restore_preserves_current_state_and_firmware_tpm_pair(self):
        checkpoint.save('client', 'before-policy')
        (self.guest / 'disk.qcow2').write_text('changed')
        (self.guest / 'tpm' / 'state').write_text('changed-tpm')
        previous = checkpoint.restore('client', 'before-policy')
        self.assertEqual((previous / 'disk.qcow2').read_text(), 'changed')
        self.assertEqual((self.guest / 'tpm' / 'state').read_text(), 'synthetic-tpm')
        self.assertEqual((self.guest / 'OVMF_VARS.fd').read_text(), 'synthetic-OVMF_VARS.fd')

    def test_corrupted_checkpoint_cannot_replace_current_state(self):
        saved = checkpoint.save('client', 'before-policy')
        (saved / 'disk.qcow2').write_text('corrupt')
        with self.assertRaises(RuntimeError):
            checkpoint.restore('client', 'before-policy')
        self.assertEqual((self.guest / 'disk.qcow2').read_text(), 'synthetic-disk.qcow2')

    def test_running_guest_is_refused(self):
        (self.guest / 'qemu.pid').write_text(str(os.getpid()))
        with self.assertRaises(RuntimeError):
            checkpoint.save('client', 'unsafe')


if __name__ == '__main__':
    unittest.main()
