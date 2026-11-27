"""Router + launch, both children of the existing ownership-token supervisor."""
from ament_index_python.packages import get_package_prefix
import argparse
import signal
import subprocess
from pathlib import Path
import time
from ground_world import ROOT


if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--config',required=True);a.add_argument('--out',required=True);a.add_argument('--headless',action='store_true');args=a.parse_args()
    router=subprocess.Popen([str(Path(get_package_prefix('rmw_zenoh_cpp')) / 'lib/rmw_zenoh_cpp/rmw_zenohd')])
    time.sleep(.5)
    if router.poll() is not None:raise RuntimeError('Ground router port 17645 unavailable')
    cmd=['ros2','launch',str(ROOT/'launch/ground.launch.py'),f'config:={args.config}',f'runtime:={args.out}',
         f'gui:={str(not args.headless).lower()}',f'rviz:={str(not args.headless).lower()}']
    launch=subprocess.Popen(cmd)
    try:launch.wait()
    except KeyboardInterrupt:pass
    finally:
        for proc in (launch,router):
            if proc.poll() is None:
                proc.send_signal(signal.SIGINT)
                try:proc.wait(timeout=8)
                except subprocess.TimeoutExpired:proc.terminate()
