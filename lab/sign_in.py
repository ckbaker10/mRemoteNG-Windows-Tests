"""Sign in to the selected LabAdmin password field using paced physical keys."""
import json
import argparse
import re
import sys
import time
from manage import ROOT, qmp
from remote import create_session


def press(keys):
    qmp('client', 'input-send-event', {'events': [
        {'type': 'key', 'data': {'down': True, 'key': {'type': 'qcode', 'data': key}}} for key in keys]})
    time.sleep(0.15)
    qmp('client', 'input-send-event', {'events': [
        {'type': 'key', 'data': {'down': False, 'key': {'type': 'qcode', 'data': key}}} for key in reversed(keys)]})
    time.sleep(0.25)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--unlock', action='store_true')
    args = parser.parse_args()
    path = ROOT / 'client' / 'credentials.json'
    if path.stat().st_mode & 0o077:
        raise RuntimeError('Lab credentials must be owner-only')
    account = json.loads(path.read_text())
    if account['username'] not in ('LabAdmin', 'MRNG-CLIENT\\LabAdmin') or not re.fullmatch(r'[A-Za-z0-9_!-]+', account['password']):
        raise RuntimeError('Unexpected local lab identity or keyboard input')
    check = ("$ErrorActionPreference='Stop';$explorer=@(Get-Process explorer -ErrorAction SilentlyContinue|Where-Object SessionId -ne 0);"
             "$locked=@(Get-Process LogonUI -ErrorAction SilentlyContinue|Where-Object SessionId -ne 0);"
             "if($explorer.Count -and -not $locked.Count){throw 'The desktop is already unlocked'};"
             + ("if($explorer.Count){throw 'Use --unlock for an existing locked desktop'};" if not args.unlock else '') +
             "$u=(Get-ItemProperty 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Authentication\\LogonUI').LastLoggedOnSAMUser;"
             "if($u -ne '.\\LabAdmin' -and $u -ne 'MRNG-CLIENT\\LabAdmin'){throw 'Select the local LabAdmin account first'};'Selected local lab account verified'")
    result = create_session('client').run_ps(check)
    if result.status_code:
        raise RuntimeError('Select the local LabAdmin password field; an active desktop must be unlocked manually')
    qmp('client', 'input-send-event', {'events': [
        {'type': 'key', 'data': {'down': False, 'key': {'type': 'qcode', 'data': key}}}
        for key in ('shift', 'shift_r', 'ctrl', 'ctrl_r', 'alt', 'alt_r', 'meta_l', 'meta_r')]})
    for key in ('esc', 'esc', 'ret'):
        press([key])
    time.sleep(2)
    for character in account['password']:
        shifted = character.isupper() or character in '_!'
        key = {'_': 'minus', '-': 'minus', '!': '1'}.get(character, character.lower())
        press((['shift'] if shifted else []) + [key])
    time.sleep(0.5)
    press(['ret'])
    print('Owned local account sign-in submitted without logging credentials')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('Lab sign-in stopped: ' + type(error).__name__, file=sys.stderr)
        sys.exit(1)
