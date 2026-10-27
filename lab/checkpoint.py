"""Offline checkpoints for owned lab guests, including firmware and TPM state."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import uuid
from manage import ROOT

REQUIRED = ('disk.qcow2', 'OVMF_VARS.fd', 'credentials.json', 'installed.marker')


def ensure_offline(machine):
    guest = ROOT / machine
    for name in ('qemu.pid', 'swtpm.pid'):
        path = guest / name
        if path.exists():
            try:
                os.kill(int(path.read_text()), 0)
            except ProcessLookupError:
                continue
            raise RuntimeError('Guest and TPM must be stopped before checkpoint operations')
    return guest


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def inventory(directory):
    result = {}
    for path in sorted(directory.rglob('*')):
        if path.is_symlink():
            raise RuntimeError('Symlinks are not allowed in checkpoint state')
        if path.is_file() and path != directory / 'manifest.json':
            result[path.relative_to(directory).as_posix()] = digest(path)
        elif not path.is_dir() and path != directory / 'manifest.json':
            raise RuntimeError('Only ordinary files and directories may be checkpointed')
    return result


def copy_state(source, destination):
    destination.mkdir(mode=0o700)
    for name in REQUIRED:
        path = source / name
        if not path.is_file() or path.is_symlink():
            raise RuntimeError('Required guest state is missing or is a link')
        subprocess.run(['cp', '--reflink=auto', '--sparse=always', '--preserve=mode,timestamps',
                        '--', str(path), str(destination / name)], check=True)
    if not (source / 'tpm').is_dir() or (source / 'tpm').is_symlink():
        raise RuntimeError('TPM state is missing or is a link')
    shutil.copytree(source / 'tpm', destination / 'tpm', symlinks=True)
    # inventory rejects links and special files before a checkpoint can be trusted.
    return inventory(destination)


def save(machine, label):
    guest = ensure_offline(machine)
    parent = ROOT / 'checkpoints' / machine
    parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    destination = parent / label
    if destination.exists():
        raise FileExistsError('Checkpoint label already exists')
    started = int(time.time())
    files = copy_state(guest, destination)
    manifest = {'format_version': 1, 'machine': machine, 'label': label, 'started_host_epoch': started,
                'finished_host_epoch': int(time.time()), 'sha256': files}
    (destination / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    os.chmod(destination / 'manifest.json', 0o600)
    return destination


def restore(machine, label):
    guest = ensure_offline(machine)
    checkpoint = ROOT / 'checkpoints' / machine / label
    manifest = json.loads((checkpoint / 'manifest.json').read_text())
    if manifest.get('format_version') != 1 or manifest['machine'] != machine or manifest['label'] != label or inventory(checkpoint) != manifest['sha256']:
        raise RuntimeError('Checkpoint identity or hashes do not match')
    # Complete and verify a staged copy before moving any current state.
    staged = ROOT / (machine + '-restore-' + uuid.uuid4().hex)
    if copy_state(checkpoint, staged) != manifest['sha256']:
        raise RuntimeError('Restored copy does not match checkpoint hashes')
    previous = ROOT / (machine + '-before-restore-' + uuid.uuid4().hex)
    guest.rename(previous)
    try:
        staged.rename(guest)
    except Exception:
        previous.rename(guest)
        raise
    return previous


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['save', 'restore'])
    parser.add_argument('machine', choices=['client', 'server'])
    parser.add_argument('label')
    args = parser.parse_args()
    if not re.fullmatch('[a-z0-9-]{1,40}', args.label):
        parser.error('Use a unique lowercase checkpoint label without path separators')
    result = save(args.machine, args.label) if args.action == 'save' else restore(args.machine, args.label)
    print('Checkpoint saved: ' + str(result) if args.action == 'save' else 'Previous state preserved: ' + str(result))
