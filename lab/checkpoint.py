"""Offline qcow2 checkpoints with pinned backing chains, firmware and TPM state."""
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


def image_chain(path):
    images = json.loads(subprocess.check_output(
        ['qemu-img', 'info', '--backing-chain', '--output=json', str(path)]))
    for image in images:
        source = Path(image['filename'])
        file = source.resolve()
        if image['format'] != 'qcow2' or not file.is_relative_to(ROOT) or source.is_symlink():
            raise RuntimeError('Only owned qcow2 backing files are supported')
    return images


def chain_hashes(images, known=None):
    known = known or {}
    return {Path(image['filename']).resolve().relative_to(ROOT).as_posix():
            known.get(Path(image['filename']).resolve()) or digest(Path(image['filename']))
            for image in images}


def copy_metadata(source, destination):
    destination.mkdir(mode=0o700)
    for name in REQUIRED:
        path = source / name
        if not path.is_file() or path.is_symlink():
            raise RuntimeError('Required guest state is missing or is a link')
        if name != 'disk.qcow2':
            shutil.copy2(path, destination / name)
    if not (source / 'tpm').is_dir() or (source / 'tpm').is_symlink():
        raise RuntimeError('TPM state is missing or is a link')
    shutil.copytree(source / 'tpm', destination / 'tpm', symlinks=True)
    return inventory(destination)


def create_overlay(path, backing):
    subprocess.run(['qemu-img', 'create', '-q', '-f', 'qcow2', '-F', 'qcow2',
                    '-b', str(backing), str(path)], check=True)


def save(machine, label):
    guest = ensure_offline(machine)
    parent = ROOT / 'checkpoints' / machine
    parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    destination = parent / label
    if destination.exists():
        raise FileExistsError('Checkpoint label already exists')
    started = int(time.time())
    disk = guest / 'disk.qcow2'
    images = image_chain(disk)
    hashes = chain_hashes(images)
    metadata = copy_metadata(guest, destination)
    saved_disk = destination / 'disk.qcow2'
    disk.rename(saved_disk)
    try:
        create_overlay(disk, saved_disk)
    except Exception:
        if disk.exists():
            disk.rename(guest / ('failed-overlay-' + uuid.uuid4().hex))
        saved_disk.rename(disk)
        raise
    metadata['disk.qcow2'] = hashes.pop(disk.relative_to(ROOT).as_posix())
    hashes[saved_disk.relative_to(ROOT).as_posix()] = metadata['disk.qcow2']
    os.chmod(saved_disk, 0o400)
    manifest = {
        'format_version': 2, 'machine': machine, 'label': label,
        'started_host_epoch': started, 'finished_host_epoch': int(time.time()),
        'sha256': metadata, 'backing_chain': hashes, 'virtual_size': images[0]['virtual-size']
    }
    (destination / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    os.chmod(destination / 'manifest.json', 0o600)
    return destination


def restore(machine, label):
    guest = ensure_offline(machine)
    checkpoint = ROOT / 'checkpoints' / machine / label
    manifest = json.loads((checkpoint / 'manifest.json').read_text())
    if manifest.get('format_version') != 2 or manifest['machine'] != machine or manifest['label'] != label:
        raise RuntimeError('Checkpoint format or identity does not match')
    files = inventory(checkpoint)
    if files != manifest['sha256']:
        raise RuntimeError('Checkpoint hashes do not match')
    saved_disk = checkpoint / 'disk.qcow2'
    if chain_hashes(image_chain(saved_disk), {saved_disk: files['disk.qcow2']}) != manifest['backing_chain']:
        raise RuntimeError('Backing chain does not match the pinned checkpoint')
    staged = ROOT / (machine + '-restore-' + uuid.uuid4().hex)
    copied = copy_metadata(checkpoint, staged)
    if copied != {name: value for name, value in files.items() if name != 'disk.qcow2'}:
        raise RuntimeError('Restored firmware or TPM metadata does not match')
    create_overlay(staged / 'disk.qcow2', saved_disk)
    images = image_chain(staged / 'disk.qcow2')
    if Path(images[0]['full-backing-filename']).resolve() != saved_disk or images[0]['virtual-size'] != manifest['virtual_size']:
        raise RuntimeError('Restored overlay has an unexpected backing file or size')
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
