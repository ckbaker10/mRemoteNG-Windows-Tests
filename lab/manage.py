"""Local KVM evaluation lab. Secrets and machine state stay in ignored work/."""
import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import time
import struct
import xml.etree.ElementTree as ET

ROOT = Path(os.environ.get('MRNG_LAB_ROOT', Path(__file__).resolve().parents[1] / 'work' / 'windows-lab')).resolve()
NS = 'urn:schemas-microsoft-com:unattend'
ET.register_namespace('', NS)
ET.register_namespace('wcm', 'http://schemas.microsoft.com/WMIConfig/2002/State')


def node(parent, tag, value=None, **attributes):
    item = ET.SubElement(parent, '{'+NS+'}'+tag, attributes)
    if value is not None:
        item.text = str(value)
    return item


def component(settings, name):
    return node(settings, 'component', name=name, processorArchitecture='amd64',
                publicKeyToken='31bf3856ad364e35', language='neutral', versionScope='nonSxS')


def prepare(name):
    ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    target = ROOT / name
    target.mkdir(mode=0o700, exist_ok=True)
    if (target / 'installed.marker').exists():
        if not all((target / item).exists() for item in ('disk.qcow2', 'OVMF_VARS.fd', 'credentials.json')):
            raise RuntimeError('Installed machine state is incomplete; refusing to reprovision it')
        return target
    credentials = target / 'credentials.json'
    if not credentials.exists():
        with open(credentials, 'x', opener=lambda path, flags: os.open(path, flags, 0o600)) as stream:
            json.dump({'username': 'LabAdmin', 'password': secrets.token_urlsafe(28)+'aA1!'}, stream)
    account = json.loads(credentials.read_text())
    seed = target / 'seed'
    seed.mkdir(mode=0o700, exist_ok=True)
    answer = ET.Element('{'+NS+'}unattend')
    settings = node(answer, 'settings', pass_='windowsPE')
    settings.attrib['pass'] = settings.attrib.pop('pass_')
    intl = component(settings, 'Microsoft-Windows-International-Core-WinPE')
    node(node(intl, 'SetupUILanguage'), 'UILanguage', 'en-US')
    for key, value in [('InputLocale','0409:00000409'), ('SystemLocale','en-US'),
                       ('UILanguage','en-US'), ('UserLocale','en-US')]:
        node(intl, key, value)
    setup = component(settings, 'Microsoft-Windows-Setup')
    user = node(setup, 'UserData')
    node(user, 'AcceptEula', 'true')
    node(user, 'FullName', 'mRemoteNG evaluation lab')
    disk = node(node(setup, 'DiskConfiguration'), 'Disk',
                **{'{http://schemas.microsoft.com/WMIConfig/2002/State}action':'add'})
    node(disk, 'DiskID', 0)
    node(disk, 'WillWipeDisk', 'true')
    creates = node(disk, 'CreatePartitions')
    for order, kind, size in [(1,'EFI',260), (2,'MSR',16), (3,'Primary',None)]:
        part = node(creates, 'CreatePartition',
                    **{'{http://schemas.microsoft.com/WMIConfig/2002/State}action':'add'})
        node(part, 'Order', order)
        node(part, 'Type', kind)
        node(part, 'Size' if size else 'Extend', size if size else 'true')
    modifies = node(disk, 'ModifyPartitions')
    for order, (number, fmt, label, letter) in enumerate([(1,'FAT32','System',None),(3,'NTFS','Windows','C')], 1):
        part = node(modifies, 'ModifyPartition',
                    **{'{http://schemas.microsoft.com/WMIConfig/2002/State}action':'add'})
        node(part, 'Order', order)
        node(part, 'PartitionID', number)
        node(part, 'Label', label)
        if letter:
            node(part, 'Letter', letter)
        node(part, 'Format', fmt)
    install = node(node(setup, 'ImageInstall'), 'OSImage')
    node(install, 'WillShowUI', 'OnError')
    metadata = node(node(install, 'InstallFrom'), 'MetaData',
                    **{'{http://schemas.microsoft.com/WMIConfig/2002/State}action':'add'})
    node(metadata, 'Key', '/IMAGE/INDEX')
    node(metadata, 'Value', 2 if name == 'server' else 1)
    location = node(install, 'InstallTo')
    node(location, 'DiskID', 0)
    node(location, 'PartitionID', 3)
    special = node(answer, 'settings', **{'pass':'specialize'})
    shell = component(special, 'Microsoft-Windows-Shell-Setup')
    node(shell, 'ComputerName', 'MRNG-DC' if name == 'server' else 'MRNG-CLIENT')
    node(shell, 'TimeZone', 'W. Europe Standard Time')
    oobe = node(answer, 'settings', **{'pass':'oobeSystem'})
    intl = component(oobe, 'Microsoft-Windows-International-Core')
    for key, value in [('InputLocale', '0409:00000409'), ('SystemLocale', 'en-US'),
                       ('UILanguage', 'en-US'), ('UserLocale', 'en-US')]:
        node(intl, key, value)
    shell = component(oobe, 'Microsoft-Windows-Shell-Setup')
    options = node(shell, 'OOBE')
    for key in ['HideEULAPage','HideOnlineAccountScreens','HideWirelessSetupInOOBE']:
        node(options, key, 'true')
    node(options, 'ProtectYourPC', 3)
    users = node(node(shell, 'UserAccounts'), 'LocalAccounts')
    local = node(users, 'LocalAccount',
                 **{'{http://schemas.microsoft.com/WMIConfig/2002/State}action':'add'})
    node(local, 'Name', account['username'])
    node(local, 'Group', 'Administrators')
    password = node(local, 'Password')
    node(password, 'Value', account['password'])
    node(password, 'PlainText', 'true')
    # Server's built-in Administrator must also have an initial nonempty password.
    if name == 'server':
        admin = node(shell.find('{'+NS+'}UserAccounts'), 'AdministratorPassword')
        node(admin, 'Value', account['password'])
        node(admin, 'PlainText', 'true')
    logon = node(shell, 'AutoLogon')
    node(logon, 'Username', account['username'])
    node(logon, 'Enabled', 'true')
    node(logon, 'LogonCount', 1)
    password = node(logon, 'Password')
    node(password, 'Value', account['password'])
    node(password, 'PlainText', 'true')
    command = node(node(shell, 'FirstLogonCommands'), 'SynchronousCommand',
                   **{'{http://schemas.microsoft.com/WMIConfig/2002/State}action':'add'})
    node(command, 'Order', 1)
    node(command, 'CommandLine', 'powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "'
         "$d=(Get-Volume -FileSystemLabel MRNGLAB).DriveLetter; & ($d+':\\bootstrap.ps1')"+'"')
    for group in [creates, modifies]:
        orders = [int(part.find('{'+NS+'}Order').text) for part in group]
        if orders != list(range(1, len(orders)+1)):
            raise ValueError('Partition action orders must be consecutive, independently of partition IDs')
    ET.ElementTree(answer).write(seed/'autounattend.xml', encoding='utf-8', xml_declaration=True)
    os.chmod(seed/'autounattend.xml', 0o600)
    shutil.copyfile(Path(__file__).with_name('bootstrap.ps1'), seed/'bootstrap.ps1')
    subprocess.run(['xorriso','-as','mkisofs','-quiet','-J','-r','-V','MRNGLAB','-o',str(target/'seed.iso'),str(seed)],check=True)
    os.chmod(target/'seed.iso',0o600)
    if not (target/'disk.qcow2').exists():
        subprocess.run(['qemu-img','create','-f','qcow2',str(target/'disk.qcow2'),'120G'],check=True)
    if not (target/'OVMF_VARS.fd').exists():
        shutil.copyfile('/usr/share/OVMF/OVMF_VARS_4M.ms.fd',target/'OVMF_VARS.fd')
    return target


def start(name):
    target = prepare(name)
    pidfile = target/'qemu.pid'
    if pidfile.exists():
        try:
            os.kill(int(pidfile.read_text()), 0)
            raise SystemExit('Machine already running')
        except ProcessLookupError:
            pidfile.unlink()
    tpm = target/'tpm'
    tpm.mkdir(exist_ok=True)
    subprocess.run(['swtpm','socket','--tpm2','--tpmstate','dir='+str(tpm),
                    '--ctrl','type=unixio,path='+str(target/'tpm.sock'),
                    '--pid','file='+str(target/'swtpm.pid'),'--daemon'],check=True)
    port = 55985 if name == 'client' else 55986
    image = ROOT/'media'/('windows11.iso' if name == 'client' else 'server2025.iso')
    args = ['qemu-system-x86_64','-name','mrng-'+name,'-machine','q35,smm=on',
            '-accel','kvm','-cpu','host','-smp','4','-m','12288' if name=='client' else '8192',
            '-drive','if=pflash,format=raw,unit=0,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.ms.fd',
            '-drive','if=pflash,format=raw,unit=1,file='+str(target/'OVMF_VARS.fd'),
            '-global','driver=cfi.pflash01,property=secure,value=on',
            '-drive','file='+str(target/'disk.qcow2')+',format=qcow2,if=ide',
            *([] if (target/'installed.marker').exists() else [
                '-drive','file='+str(image)+',media=cdrom,readonly=on',
                '-drive','file='+str(target/'seed.iso')+',media=cdrom,readonly=on',
                '-boot','once=d,menu=on']),
            '-chardev','socket,id=chrtpm,path='+str(target/'tpm.sock'),
            '-tpmdev','emulator,id=tpm0,chardev=chrtpm','-device','tpm-tis,tpmdev=tpm0',
            '-netdev','user,id=nat,hostfwd=tcp:127.0.0.1:'+str(port)+'-:5985',
            '-device','e1000e,netdev=nat,mac=52:54:00:aa:'+('10' if name=='server' else '20')+':01',
            '-netdev','socket,id=lab,'+('listen' if name=='server' else 'connect')+'=127.0.0.1:55990',
            '-device','e1000e,netdev=lab,mac=52:54:00:aa:'+('10' if name=='server' else '20')+':02',
            '-device','qemu-xhci,id=mrngusb','-device','usb-tablet,bus=mrngusb.0',
            '-vnc','unix:'+str(target/'vnc.sock'),
            '-qmp','unix:'+str(target/'qmp.sock')+',server=on,wait=off',
            '-pidfile',str(pidfile),'-daemonize','-D',str(target/'qemu.log')]
    subprocess.run(args,check=True)
    print(name+' started; management available only on loopback port '+str(port))


def qmp(name, command, arguments):
    client = socket.socket(socket.AF_UNIX)
    client.connect(str(ROOT/name/'qmp.sock'))
    stream = client.makefile('rwb',buffering=0)
    stream.readline()
    for request in [{'execute':'qmp_capabilities'},{'execute':command,'arguments':arguments}]:
        stream.write(json.dumps(request).encode()+b'\n')
        while True:
            response = json.loads(stream.readline())
            if 'return' in response or 'error' in response:
                if 'error' in response:
                    raise RuntimeError(response['error'])
                break
    return response


def vnc_input(name, key=None, text=None, x=None, y=None):
    client = socket.socket(socket.AF_UNIX)
    client.settimeout(10)
    client.connect(str(ROOT/name/'vnc.sock'))
    def receive(size):
        data = b''
        while len(data)<size:
            chunk=client.recv(size-len(data))
            if not chunk: raise RuntimeError('VNC connection closed')
            data+=chunk
        return data
    receive(12)
    client.sendall(b'RFB 003.008\n')
    security = receive(receive(1)[0])
    if 1 not in security: raise RuntimeError('Expected local no-auth VNC socket')
    client.sendall(b'\x01')
    if receive(4)!=b'\0\0\0\0': raise RuntimeError('VNC negotiation failed')
    client.sendall(b'\x01')
    header = receive(24)
    receive(struct.unpack('!I',header[20:24])[0])
    def send_symbol(symbol, down):
        client.sendall(struct.pack('!BBHI',4,int(down),0,symbol))
    if key is not None:
        special={'ret':0xff0d,'tab':0xff09,'spc':0x20,'escape':0xff1b,
                 'shift':0xffe1,'alt':0xffe9,'f10':0xffc7}
        codes=[special[item] if item in special else ord(item) for item in key.split('+')]
        for code in codes: send_symbol(code,True)
        time.sleep(0.2)
        for code in reversed(codes): send_symbol(code,False)
    elif text is not None:
        shifted={':':';','&':'7','%':'5','$':'4','~':'`','|':'\\','"':"'",'>':'.','<':',',
                 '!':'1','?':'/','(':'9',')':'0','_':'-','+':'=','{':'[','}':']','@':'2','#':'3','^':'6','*':'8'}
        for character in text:
            shift=character in shifted or character.isupper()
            base=shifted.get(character,character.lower() if character.isupper() else character)
            if shift: send_symbol(0xffe1,True)
            send_symbol(ord(base),True)
            time.sleep(0.025)
            send_symbol(ord(base),False)
            if shift: send_symbol(0xffe1,False)
            time.sleep(0.025)
        send_symbol(0xff0d,True)
        time.sleep(0.1)
        send_symbol(0xff0d,False)
    else:
        client.sendall(struct.pack('!BBHH',5,0,x,y))
        time.sleep(0.1)
        client.sendall(struct.pack('!BBHH',5,1,x,y))
        time.sleep(0.2)
        client.sendall(struct.pack('!BBHH',5,0,x,y))
    time.sleep(0.5)
    client.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action',choices=['prepare','start','boot','pause','resume','key','vnc-key','vnc-type','vnc-click','legacy-input','tablet','click','blocks','eject-install','eject-seed','seal','screen','status','powerdown'])
    parser.add_argument('machine',choices=['client','server'])
    parser.add_argument('--key',default='spc')
    parser.add_argument('--text',default='')
    parser.add_argument('--x',type=int,default=900)
    parser.add_argument('--y',type=int,default=636)
    args = parser.parse_args()
    if args.action == 'prepare':
        prepare(args.machine)
    elif args.action == 'start':
        start(args.machine)
    elif args.action == 'pause':
        qmp(args.machine,'stop',{})
    elif args.action == 'resume':
        qmp(args.machine,'cont',{})
    elif args.action == 'key':
        qmp(args.machine,'send-key',{'keys':[{'type':'qcode','data':key} for key in args.key.split('+')]})
    elif args.action == 'vnc-key':
        vnc_input(args.machine,key=args.key)
    elif args.action == 'vnc-type':
        vnc_input(args.machine,text=args.text)
    elif args.action == 'vnc-click':
        vnc_input(args.machine,x=args.x,y=args.y)
    elif args.action == 'legacy-input':
        devices=qmp(args.machine,'qom-list',{'path':'/machine/peripheral-anon'})['return']
        changed=0
        for device in devices:
            if device['type'] in ['child<usb-kbd>','child<usb-tablet>']:
                qmp(args.machine,'qom-set',{'path':'/machine/peripheral-anon/'+device['name'],
                    'property':'realized','value':False})
                changed+=1
        qmp(args.machine,'human-monitor-command',{'command-line':'mouse_set 0'})
        print('Disabled USB input devices:',changed)
    elif args.action == 'tablet':
        qmp(args.machine,'device_add',{'driver':'qemu-xhci','id':'mrngusb'})
        qmp(args.machine,'device_add',{'driver':'usb-tablet','id':'mrngtablet','bus':'mrngusb.0'})
    elif args.action == 'blocks':
        blocks = qmp(args.machine,'query-block',{})['return']
        print([(item['device'],item.get('inserted',{}).get('file')) for item in blocks])
    elif args.action in ('eject-install', 'eject-seed', 'seal'):
        blocks = qmp(args.machine,'query-block',{})['return']
        for item in blocks:
            if item.get('inserted',{}).get('file','').endswith(
                    ('seed.iso', 'server2025.iso', 'windows11.iso') if args.action == 'seal'
                    else ('seed.iso',) if args.action == 'eject-seed' else ('server2025.iso','windows11.iso')):
                qmp(args.machine,'eject',{'device':item['device'],'force':True})
        if args.action == 'seal':
            (ROOT/args.machine/'installed.marker').touch(mode=0o600)
    elif args.action == 'click':
        qmp(args.machine,'input-send-event',{'events':[
            {'type':'abs','data':{'axis':'x','value':int(args.x*32767/1280)}},
            {'type':'abs','data':{'axis':'y','value':int(args.y*32767/800)}},
            {'type':'btn','data':{'down':True,'button':'left'}}]})
        time.sleep(0.1)
        qmp(args.machine,'input-send-event',{'events':[{'type':'btn','data':{'down':False,'button':'left'}}]})
    elif args.action == 'boot':
        qmp(args.machine,'system_reset',{})
        # Send exactly one key at the CD prompt. Repeated keys can interrupt the
        # boot-manager countdown or accidentally interact with Windows Setup.
        from PIL import Image
        for _ in range(90):
            time.sleep(0.5)
            frame = ROOT/args.machine/'boot.ppm'
            qmp(args.machine,'screendump',{'filename':str(frame)})
            picture = Image.open(frame).convert('RGB')
            strip = picture.crop((150, 25, 1000, 70))
            white = sum(1 for red,green,blue in strip.getdata() if min(red,green,blue)>230)
            if white > 300:
                qmp(args.machine,'send-key',{'keys':[{'type':'qcode','data':'spc'}]})
                print('CD boot prompt acknowledged')
                break
    elif args.action == 'screen':
        qmp(args.machine,'screendump',{'filename':str(ROOT/args.machine/'screen.ppm')})
    elif args.action == 'powerdown':
        qmp(args.machine,'system_powerdown',{})
    else:
        print(qmp(args.machine,'query-status',{}))
