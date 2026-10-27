"""Create immutable git archives and a credential-free Windows run configuration."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

REPO = Path(__file__).resolve().parents[1]


def package(product_repo, product_commit, harness_repo=REPO):
    product_repo, harness_repo = Path(product_repo).resolve(), Path(harness_repo).resolve()
    if not re.fullmatch('[0-9a-f]{40}', product_commit):
        raise ValueError('Use a full product commit')
    harness_commit = subprocess.check_output(['git', '-C', str(harness_repo), 'rev-parse', 'HEAD'], text=True).strip()
    if subprocess.check_output(['git', '-C', str(harness_repo), 'status', '--porcelain'], text=True).strip():
        raise RuntimeError('Commit the test harness changes before packaging it')
    transfer = harness_repo / 'work' / 'transfer'
    transfer.mkdir(parents=True, exist_ok=True)
    result = {'source_commit': product_commit, 'harness_commit': harness_commit}
    commands = []
    for name, repository, commit in [('source', product_repo, product_commit), ('harness', harness_repo, harness_commit)]:
        filename = ('mRemoteNG-' if name == 'source' else 'windows-tests-') + commit + '.zip'
        archive = transfer / filename
        if archive.exists():
            raise RuntimeError('Archive already exists; preserve the pinned input and use its existing configuration')
        command = ['git', '-C', str(repository), 'archive', '--format=zip', '--output=' + str(archive), commit]
        subprocess.run(command, check=True)
        commands.append(command)
        result[name + '_archive'] = filename
        result[name + '_sha256'] = hashlib.sha256(archive.read_bytes()).hexdigest()
    destination = harness_repo / 'work' / ('run-' + product_commit[:12] + '-' + harness_commit[:12] + '.json')
    with destination.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    provenance = destination.with_suffix('.provenance.json')
    provenance.write_text(json.dumps({'commands': commands, 'config_sha256': hashlib.sha256(destination.read_bytes()).hexdigest()}, indent=2) + '\n')
    return destination


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('product_repo', type=Path)
    parser.add_argument('product_commit')
    args = parser.parse_args()
    print(package(args.product_repo, args.product_commit))
