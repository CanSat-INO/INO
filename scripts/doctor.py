"""Read-only clone/environment diagnostic; never installs or starts a simulation."""
from __future__ import annotations
import argparse,json,os,shutil,subprocess,sys
from pathlib import Path
sys.dont_write_bytecode=True
from install_ros2 import os_release,validate_os
ROOT=Path(__file__).resolve().parents[1]


def command(argv,env=None,timeout=20):
    try:
        result=subprocess.run(argv,env=env,capture_output=True,text=True,timeout=timeout)
        return result.returncode==0,(result.stdout+result.stderr).strip()
    except (OSError,subprocess.TimeoutExpired) as exc:return False,str(exc)


def clean_env():
    env=os.environ.copy();venv=env.pop('VIRTUAL_ENV',None);env.pop('PYTHONHOME',None)
    if venv:env['PATH']=os.pathsep.join(p for p in env.get('PATH','').split(os.pathsep) if p!=venv+'/bin')
    return env


def diagnose(lab_only=False,ros_only=False):
    rows=[]
    def add(name,ok,detail,warn=False):rows.append({'name':name,'status':'OK' if ok else ('WARN' if warn else 'FAIL'),'detail':str(detail)})
    distro=None
    try:
        info=os_release();distro=validate_os(info);add('Ubuntu',True,info.get('PRETTY_NAME',distro))
    except (OSError,RuntimeError) as exc:add('Ubuntu',False,exc)
    add('Python',sys.version_info[:2]==({'jazzy': (3,12), 'lyrical': (3,14)}.get(distro)),sys.version.split()[0])
    required=['tools/module_test_lab/app.py','tools/module_test_lab/launch_ino.sh','requirements-gui.txt']
    if not lab_only:required+=['ros2_ws/src/ino_camera_sim/assets/meshes/deployed.obj','ros2_ws/src/ino_camera_sim/assets/meshes/folded.obj','ros2_ws/src/ino_mission_sim/tools/run_mission.py','cansat/sil/build_controller.py']
    missing=[f for f in required if not (ROOT/f).is_file()]
    add('Checkout files',not missing,', '.join(missing) if missing else 'required source and model files present')
    if not ros_only:
        python=ROOT/'.venv/bin/python';add('GUI venv',python.is_file(),str(python))
        if python.is_file():
            env=clean_env();env['QT_QPA_PLATFORM']='offscreen'
            ok,detail=command([str(python),'-c','import PySide6; from PySide6.QtWidgets import QApplication; a=QApplication([]); print(PySide6.__version__)'],env)
            add('PySide6 / Qt',ok,detail)
            if ok:add('Tested GUI version',detail.splitlines()[-1]=='6.12.0','expected 6.12.0; installed '+detail.splitlines()[-1],warn=True)
            ok,path=command([str(python),'-c',"from pathlib import Path; import PySide6; print(Path(PySide6.__file__).parent/'Qt/plugins/platforms/libqxcb.so')"],env)
            if ok and Path(path).is_file():
                ok,detail=command(['ldd',path]);missing=[line.strip() for line in detail.splitlines() if 'not found' in line]
                add('Qt X11 libraries',ok and not missing,'; '.join(missing) if missing else 'all linked libraries found')
        display=bool(os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'))
        add('GUI display',display,'DISPLAY='+os.environ.get('DISPLAY','')+'; WAYLAND_DISPLAY='+os.environ.get('WAYLAND_DISPLAY',''),warn=True)
        add('Japanese input (optional)',shutil.which('fcitx5') is not None,'Fcitx5/Mozc is optional; setup --with-ime installs tools without changing your profile',warn=True)
    if not lab_only and distro:
        setup=Path(f'/opt/ros/{distro}/setup.bash');add(f'ROS {distro}',setup.is_file(),setup)
        if setup.is_file():
            probe="""import json,cv2,numpy,scipy,yaml,PIL,matplotlib,tkinter,rclpy,cv_bridge
from ament_index_python.packages import get_package_prefix
import importlib,os
transport,msgs=(15,"msgs") if os.environ["ROS_DISTRO"]=="lyrical" else (13,"msgs10")
importlib.import_module(f"gz.transport{transport}")
importlib.import_module(f"gz.{msgs}")
names=['ros_gz_sim','ros_gz_bridge','rtabmap_odom','rtabmap_slam','rmw_zenoh_cpp','rviz2','tf2_ros']
print(json.dumps({name:get_package_prefix(name) for name in names}))
"""
            ok,detail=command(['/bin/bash','-c','source "$1" && exec /usr/bin/python3 -c "$2"','ino-doctor',str(setup),probe],clean_env(),timeout=30)
            add('ROS / Gazebo / SLAM libraries',ok,detail)
            ok,detail=command(['/bin/bash','-c','source "$1" && command -v ros2 && gz sim --versions','ino-doctor',str(setup)],clean_env())
            add('ROS / Gazebo commands',ok,detail)
        add('C++ compiler',shutil.which('g++') is not None,'g++ is required for native SIL')
        add('colcon',shutil.which('colcon') is not None,'colcon is used for package builds; source launchers do not need a build')
        if shutil.which('glxinfo') and (os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')):
            ok,detail=command(['glxinfo','-B'],timeout=10)
            renderer='; '.join(line.strip() for line in detail.splitlines() if 'renderer' in line.lower())
            add('OpenGL diagnostic',ok,renderer or detail,warn=True)
    return rows


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);m=p.add_mutually_exclusive_group();m.add_argument('--lab-only',action='store_true');m.add_argument('--ros-only',action='store_true');p.add_argument('--json',action='store_true');a=p.parse_args(argv)
    rows=diagnose(a.lab_only,a.ros_only);passed=not any(r['status']=='FAIL' for r in rows)
    if a.json:print(json.dumps({'passed':passed,'root':str(ROOT),'checks':rows},ensure_ascii=False,indent=2))
    else:
        for row in rows:print('['+row['status']+'] '+row['name']+': '+row['detail'])
        print('Ready. Use start-module-test-lab.bat or bash tools/module_test_lab/launch_ino.sh.' if passed else 'Some prerequisites are missing. Run bash scripts/setup.sh; see docs/setup/README.md.')
        print('Read-only checks do not prove Gazebo rendering or real hardware behavior.')
    return 0 if passed else 1

if __name__=='__main__':raise SystemExit(main())
