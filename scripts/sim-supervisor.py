"""Own the local router and application process groups."""
import fcntl
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time


def reachable(port):
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=0.2):
            return True
    except OSError:
        return False


def stop(process, signals):
    if process is None:
        return
    for sig, seconds in signals:
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            break
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            process.poll()
            try:
                os.killpg(process.pid, 0)
            except ProcessLookupError:
                return
            time.sleep(0.05)
    process.wait(timeout=2)


def run(folder, port, executable, command):
    stopping = False

    def request_stop(_signal, _frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    router = child = None
    with (folder / 'router.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(f'[ERROR] ポート {port} のZenohルーターは起動中です。', file=sys.stderr)
            return 2
        if reachable(port):
            print(f'[ERROR] 127.0.0.1:{port} は使用中です。', file=sys.stderr)
            return 2
        try:
            env = dict(os.environ, ZENOH_ROUTER_CONFIG_URI=str(folder / 'router.json5'))
            with (folder / 'router.log').open('w') as log:
                router = subprocess.Popen([executable], env=env, stdout=log,
                                          stderr=subprocess.STDOUT, start_new_session=True)
            deadline = time.monotonic() + 8
            while not stopping and router.poll() is None and time.monotonic() < deadline:
                if reachable(port):
                    break
                time.sleep(0.1)
            else:
                if stopping:
                    return 130
                print(f'[ERROR] Zenohを起動できません。ログ: {folder / "router.log"}', file=sys.stderr)
                return 2
            print(f'Zenoh 準備完了: 127.0.0.1:{port} (ROS_DOMAIN_ID={os.environ["ROS_DOMAIN_ID"]})', flush=True)
            child = subprocess.Popen(command, start_new_session=True)
            while not stopping and child.poll() is None:
                if router.poll() is not None:
                    print(f'[ERROR] Zenohが終了しました。ログ: {folder / "router.log"}', file=sys.stderr)
                    return 2
                time.sleep(0.1)
            return 0 if stopping else child.returncode
        finally:
            try:
                stop(child, ((signal.SIGINT, 6), (signal.SIGTERM, 2), (signal.SIGKILL, 2)))
            finally:
                stop(router, ((signal.SIGTERM, 2), (signal.SIGKILL, 2)))


if __name__ == '__main__':
    sys.exit(run(Path(sys.argv[1]), int(sys.argv[2]), sys.argv[3], sys.argv[4:]))
