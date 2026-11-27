"""Ubuntu ROS 2 bootstrap using a checksum-pinned official apt source.

Does not edit shell profiles, replace existing ROS repositories, upgrade the OS,
restart services, install Windows components or modify system time.
"""
from __future__ import annotations
import argparse,hashlib,os,shlex,subprocess,tempfile,urllib.request
from pathlib import Path

VERSION='1.3.0'
DEB='ros2-apt-source_1.3.0.noble_all.deb'
URL='https://github.com/ros-infrastructure/ros-apt-source/releases/download/'+VERSION+'/'+DEB
SHA256='f31d84adf5054c7d60ded0e82c0f776a77ea33af53d08f40b9ad7c94cca55296'


def os_release(path=Path('/etc/os-release')):
    data={}
    for line in path.read_text().splitlines():
        if '=' in line:
            key,value=line.split('=',1);data[key]=value.strip().strip('"')
    return data


def validate_os(info):
    distro = {'24.04': 'jazzy', '26.04': 'lyrical'}.get(info.get('VERSION_ID'))
    if info.get('ID') != 'ubuntu' or distro is None:
        raise RuntimeError('Use Ubuntu 24.04 (Jazzy) or 26.04 (Lyrical). No package changes were made.')
    return distro


def source_present(root=Path('/etc/apt')):
    files=[root/'sources.list',*(root/'sources.list.d').glob('*.list'),*(root/'sources.list.d').glob('*.sources')]
    target='packages.ros.org/ros2/ubuntu'
    for path in files:
        if not path.is_file():continue
        text=path.read_text(errors='replace')
        if path.suffix!='.sources':
            if any(line.strip().startswith('deb ') and target in line for line in text.splitlines()):return True
        else:
            for block in text.split('\n\n'):
                fields={}
                for line in block.splitlines():
                    if line.lstrip().startswith('#'):continue
                    if ':' in line:
                        key,value=line.split(':',1);fields[key.lower()]=value.strip()
                if fields.get('enabled','yes').lower()!='no' and 'deb' in fields.get('types','').split() and target in fields.get('uris',''):return True
    return False


def verified(data, checksum=SHA256):
    if hashlib.sha256(data).hexdigest()!=checksum:raise RuntimeError('Official apt-source SHA256 mismatch; package will not be installed')
    return data


def main(argv=None):
    a=argparse.ArgumentParser(description=__doc__);a.add_argument('--dry-run',action='store_true');args=a.parse_args(argv)
    distro = validate_os(os_release())
    deb, checksum = DEB, SHA256
    if distro == 'lyrical':
        deb = DEB.replace('noble', 'resolute')
        checksum = 'e70bc980395f4a3b366b9c5e7f8f9b4d63a4064fb115f6ff3bc52f7faa02ef69'
    url = URL.rsplit('/', 1)[0] + '/' + deb
    arch=subprocess.check_output(['dpkg','--print-architecture'],text=True).strip()
    if arch not in ('amd64','arm64'):raise RuntimeError('Supported ROS Ubuntu architectures: amd64 / arm64')
    sudo=[] if os.geteuid()==0 else ['sudo']
    def run(command):
        command=[*sudo,*command];print('+ '+shlex.join(command),flush=True)
        if not args.dry_run:subprocess.run(command,check=True)
    run(['apt-get','update'])
    if not source_present():
        run(['apt-get','install','-y','ca-certificates','software-properties-common'])
        run(['add-apt-repository','-y','universe'])
        print('Official ROS apt source: '+url+'\nSHA256: '+checksum,flush=True)
        if args.dry_run:print('+ download, verify SHA256, then apt-get install verified local .deb')
        else:
            request=urllib.request.Request(url,headers={'User-Agent':'CanSat-INO-setup'})
            with urllib.request.urlopen(request,timeout=60) as response:data=verified(response.read(), checksum)
            with tempfile.TemporaryDirectory(prefix='ino-ros-source-') as folder:
                os.chmod(folder,0o755);target=Path(folder)/deb;target.write_bytes(data);target.chmod(0o644)
                package=subprocess.check_output(['dpkg-deb','-f',str(target),'Package'],text=True).strip()
                if package!='ros2-apt-source':raise RuntimeError('Unexpected .deb package name')
                run(['apt-get','install','-y',str(target)])
        run(['apt-get','update'])
    else:print('Existing official ROS source retained; no apt source files replaced.',flush=True)
    run(['apt-get','install','-y',f'ros-{distro}-ros-base'])
    print(f'ROS {distro} setup plan complete.' if args.dry_run else f'ROS {distro} installed.')
    return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except (RuntimeError,OSError,subprocess.CalledProcessError) as exc:raise SystemExit('[ERROR] '+str(exc))
