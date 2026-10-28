"""Build COMPLIANCE.md from recorded full-suite runs; refuses to report an unaccepted run as passed.

Usage: make_compliance.py <refs-file>
<refs-file> lists "<branch> <commit>" lines. Runs come from work/full-suite/<environment>/.
Each run is compared test by test with the upstream run of the same environment.
"""
import hashlib
import json
from PIL import Image
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RUNS = REPO / 'work' / 'full-suite'
IMAGES = REPO / 'reports' / 'compliance'
NS = {'t': 'http://microsoft.com/schemas/VisualStudio/TeamTest/2010'}
UPSTREAM = 'upstream/v1.78.2-dev'
ENVIRONMENTS = {
    'no-policy': ('Without machine policy', 'GPO link disabled; HKLM\\SOFTWARE\\Policies\\mRemoteNG\\Security absent', False),
    'gpo': ('With the lab security GPO', 'mRemoteNG Lab Security Acceptance linked to the client OU', True),
}


def outcomes(run):
    data = (run / 'tests.trx').read_bytes()
    if b'<!DOCTYPE' in data or b'<!ENTITY' in data:
        raise SystemExit(f'Refusing TRX with DTD or entity declarations: {run}')
    tree = ET.ElementTree(ET.fromstring(data))
    names = {u.get('id'): u.find('t:TestMethod', NS).get('className') for u in tree.iterfind('.//t:UnitTest', NS)}
    return {names[r.get('testId')] + '.' + r.get('testName'): r.get('outcome')
            for r in tree.iterfind('.//t:UnitTestResult', NS)}


def latest(environment, ref, commit):
    found = []
    for meta in (RUNS / environment).glob('*/metadata.json'):
        record = json.loads(meta.read_text())
        if record.get('ref') == ref and record.get('commit') == commit and (meta.parent / 'tests.trx').exists():
            found.append((record['host_started'], meta.parent, record))
    if not found:
        raise SystemExit(f'No recorded {environment} run for {ref} at {commit}')
    return max(found, key=lambda item: item[0])[1:]


def evaluate(environment, run, record, base):
    result = record['result']
    tests = outcomes(run)
    base_failed = {name for name, outcome in base.items() if outcome != 'Passed'}
    failed = {name for name, outcome in tests.items() if outcome != 'Passed'}
    added = set(tests) - set(base)
    managed = bool(result.get('MachinePolicyValues'))
    problems = []
    if result.get('BuildExitCode') != 0:
        problems.append('build failed')
    if result.get('Trx_aborted') or result.get('Trx_error') or result.get('Trx_timeout'):
        problems.append('aborted, error or timeout')
    if failed - base_failed:
        problems.append(f'{len(failed - base_failed)} failure(s) not in upstream')
    if set(base) - set(tests):
        problems.append(f'{len(set(base) - set(tests))} upstream test(s) missing')
    if managed != ENVIRONMENTS[environment][2]:
        problems.append('machine policy state does not match the environment')
    if not record.get('desktop_screenshot'):
        problems.append('no desktop screenshot')
    return {'result': result, 'added': len(added), 'added_failed': len(added & failed),
            'upstream_failed': len(failed & base_failed), 'problems': problems, 'managed': managed}


def main(refs_file):
    refs = [line.split() for line in Path(refs_file).read_text().splitlines() if line.strip()]
    upstream_commit = 'e3b0108e5ea06c9b8baedcfa385e1b18e9de2385'
    lines, failures = [], []
    for environment, (title, description, _) in ENVIRONMENTS.items():
        base_run, base_record = latest(environment, UPSTREAM, upstream_commit)
        base = outcomes(base_run)
        sample = base_record['result']
        lines += [title, '',
                  f'{description}. Windows {sample.get("OSEdition")} build {sample.get("OSBuild")}, '
                  f'MSBuild {sample.get("MSBuild")}, .NET SDK {sample.get("DotnetSdk")}. '
                  f'Upstream `{upstream_commit[:8]}`: {sample["Trx_total"]} tests, {sample["Trx_passed"]} passed, '
                  f'{sample["Trx_failed"]} failed.', '',
                  '| Branch | Commit | Archive SHA-256 | Total | Passed | Failed (all upstream) | New tests | Result | Screenshot |',
                  '|---|---|---|---:|---:|---:|---:|---|---|']
        for ref, commit in [(UPSTREAM, upstream_commit)] + [tuple(r) for r in refs]:
            run, record = latest(environment, ref, commit) if ref != UPSTREAM else (base_run, base_record)
            check = evaluate(environment, run, record, base)
            image = IMAGES / environment / (ref.replace('/', '_') + '.png')
            image.parent.mkdir(parents=True, exist_ok=True)
            source = run / record['desktop_screenshot'] if record.get('desktop_screenshot') else None
            if source and source.exists():
                # Lossless re-encoding only; the pixels stay identical to the captured screen.
                with Image.open(source) as captured:
                    captured.save(image, optimize=True, compress_level=9)
                with Image.open(source) as a, Image.open(image) as b:
                    if a.convert('RGB').tobytes() != b.convert('RGB').tobytes():
                        raise SystemExit(f'Screenshot pixels changed while copying {source}')
            verdict = 'accepted' if not check['problems'] else 'NOT accepted: ' + '; '.join(check['problems'])
            if check['problems']:
                failures.append(f'{environment} {ref}: {verdict}')
            r = check['result']
            lines.append(f'| `{ref}` | `{commit[:8]}` | `{record["archive_sha256"][:16]}…` | {r["Trx_total"]} | '
                         f'{r["Trx_passed"]} | {r["Trx_failed"]} ({check["upstream_failed"]}) | '
                         f'{check["added"]} ({check["added_failed"]} failed) | {verdict} | '
                         f'[desktop](reports/compliance/{environment}/{image.name}) |')
        lines.append('')
        for ref, _ in [(UPSTREAM, None)] + [tuple(r) for r in refs]:
            name = ref.replace('/', '_') + '.png'
            lines += [f'{title}: `{ref}`', '', f'![{ref} – {environment}](reports/compliance/{environment}/{name})', '']
    header = ['mRemoteNG full test suite compliance', '',
              'Complete, unfiltered `mRemoteNGTests` runs for every security branch, built and tested on the owned',
              'Windows lab client in its signed-in desktop session (session 1). Each run is compared test by test',
              'with the unchanged upstream base `v1.78.2-dev` in the same environment. Accepted means: the build',
              'succeeds, no test is aborted, errors or times out, every failure also fails upstream, every upstream',
              'test runs, the machine policy matches the environment and an unmodified desktop screenshot exists.',
              'Upstream itself fails the same tests (mainly CSV deserialization, STA-thread and UI timing tests).', '',
              'Reproduce with the commands in [README.md](README.md), section "Full test suite". Raw TRX files, logs,',
              'hashes and host timestamps stay in the ignored `work/full-suite/` directory.', '']
    if failures:
        header += ['**Not all runs are accepted:**', ''] + [f'- {f}' for f in failures] + ['']
    text = '\n'.join(header + lines)
    (REPO / 'COMPLIANCE.md').write_text(text)
    digest = hashlib.sha256(text.encode()).hexdigest()
    print(('NOT ACCEPTED ' if failures else 'ALL ACCEPTED ') + digest)
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1]))
