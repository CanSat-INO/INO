"""Own a launch session, including Gazebo's detached native processes.

The lock is never inherited by children. Cleanup matches a unique environment
token, so other ROS/Gazebo sessions and independent teleop windows are untouched.
"""
import fcntl
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]

def main():
    lock=(ROOT/'logs'/os.environ.get('CANSAT_LOCK_NAME','.active.lock')).open('w')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:
        print('A CanSat simulation is already running. Stop it first.',flush=True)
        return 1
    token=uuid.uuid4().hex
    match=('CANSAT_SESSION_ID='+token).encode()
    env=os.environ.copy();env['CANSAT_SESSION_ID']=token
    stopping=False
    def request_stop(signum,frame):
        nonlocal stopping
        stopping=True
    signal.signal(signal.SIGINT,request_stop);signal.signal(signal.SIGTERM,request_stop)
    def owned():
        ids=[]
        for entry in Path('/proc').iterdir():
            if not entry.name.isdigit() or int(entry.name)==os.getpid():continue
            try:
                if match in (entry/'environ').read_bytes().split(b'\0'):ids.append(int(entry.name))
            except (OSError,PermissionError):pass
        return ids
    def send(sig):
        for pid in owned():
            try:os.kill(pid,sig)
            except ProcessLookupError:pass
    proc=subprocess.Popen(sys.argv[1:],env=env,start_new_session=True,close_fds=True)
    try:
        while proc.poll() is None and not stopping:time.sleep(.2)
        code=0 if stopping else proc.returncode
    finally:
        for sig,seconds in [(signal.SIGINT,25),(signal.SIGTERM,6),(signal.SIGKILL,2)]:
            send(sig);end=time.monotonic()+seconds
            while owned() and time.monotonic()<end:
                proc.poll();time.sleep(.2)
            if not owned():break
        try:proc.wait(timeout=2)
        except subprocess.TimeoutExpired:proc.kill();proc.wait()
        lock.close()
    return code

if __name__=='__main__':sys.exit(main())
