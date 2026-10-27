import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile

SOURCE = Path(__file__).resolve().parents[1] / 'lab' / 'package_inputs.py'
spec = importlib.util.spec_from_file_location('package_inputs', SOURCE)
packager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packager)


class PackageInputsTests(unittest.TestCase):
    def repository(self, root):
        root.mkdir()
        (root / '.gitignore').write_text('/work/\n')
        (root / 'synthetic.txt').write_text('public synthetic input')
        for command in [['init', '-q'], ['add', '.gitignore', 'synthetic.txt'],
                        ['-c', 'user.name=Synthetic Test', '-c', 'user.email=synthetic@example.test', 'commit', '-qm', 'Synthetic input']]:
            subprocess.run(['git', '-C', str(root)] + command, check=True)
        return subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()

    def test_archives_match_their_commits_and_hashes_without_private_work_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            commit = self.repository(root / 'product')
            self.repository(root / 'harness')
            private = root / 'harness' / 'work'
            private.mkdir()
            (private / 'synthetic-private.json').write_text('must stay outside archives')
            path = packager.package(root / 'product', commit, root / 'harness')
            config = json.loads(path.read_text())
            for name in ('source', 'harness'):
                archive = private / 'transfer' / config[name + '_archive']
                self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(), config[name + '_sha256'])
                with zipfile.ZipFile(archive) as zipped:
                    self.assertEqual(zipped.read('synthetic.txt'), b'public synthetic input')
                    self.assertFalse(any(entry.startswith('work/') for entry in zipped.namelist()))
            with self.assertRaises(RuntimeError):
                packager.package(root / 'product', commit, root / 'harness')

    def test_dirty_harness_is_rejected_before_an_archive_is_created(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            commit = self.repository(root / 'product')
            self.repository(root / 'harness')
            (root / 'harness' / 'synthetic.txt').write_text('uncommitted')
            with self.assertRaises(RuntimeError):
                packager.package(root / 'product', commit, root / 'harness')
            self.assertFalse((root / 'harness' / 'work' / 'transfer').exists())
