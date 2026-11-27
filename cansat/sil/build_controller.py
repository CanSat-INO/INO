"""Compile a native SIL adapter, not an ESP32 image. No Arduino source rewriting."""
import argparse,hashlib,json,platform,subprocess,shlex
from pathlib import Path

def build(sources, output, includes=(), contract=None):
    sources=[Path(p).resolve() for p in sources];output=Path(output).resolve()
    if not sources or any(p.suffix not in ('.cpp','.cc','.cxx') or not p.is_file() for p in sources):
        raise ValueError('Supply existing host C++ adapters (.cpp/.cc/.cxx), not .ino or ESP32 ELF files')
    output.parent.mkdir(parents=True,exist_ok=True)
    flags=['g++','-std=c++17','-O2','-Wall','-Wextra']
    for include in [*(p.parent for p in sources),*map(Path,includes),*([Path(contract)] if contract else [])]:flags+=['-I',str(include.resolve())]
    digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    dependencies=set(sources)
    for source in sources:
        raw=subprocess.check_output([*flags,'-MM',str(source)],text=True,timeout=30)
        raw=raw.replace('\\\n',' ')
        dependencies.update(Path(p).resolve() for p in shlex.split(raw.split(':',1)[1]))
    before={str(p):digest(p) for p in dependencies}
    command=[*flags,*map(str,sources),'-o',str(output)]
    subprocess.run(command,check=True,timeout=120)
    if before!={str(p):digest(p) for p in dependencies}:
        raise RuntimeError('Controller source/header changed during compilation')
    manifest={'kind':'native_host_sil','hardware_emulated':False,'platform':platform.machine(),
      'sources':{str(p):digest(p) for p in sources},'binary_sha256':digest(output),
      'dependencies':before,'command':command,'compiler':subprocess.check_output(['g++','--version'],text=True).splitlines()[0]}
    if contract:manifest['contract_sha256']=digest(Path(contract)/'sim_port.hpp')
    (output.parent/'manifest.json').write_text(json.dumps(manifest,indent=2))
    return output

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('sources',nargs='+');a.add_argument('--output',required=True)
    a.add_argument('--include',action='append',default=[]);a.add_argument('--contract',required=True)
    args=a.parse_args();print(build(args.sources,args.output,args.include,args.contract))
