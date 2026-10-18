# core/aria2_process.py
"""Lifecycle of the aria2c process FelfelDM starts.

Why this exists
---------------
aria2 has no ``pid-file`` option (it only logs "Unknown option"), and the
old code started it with ``--daemon``, which forks away and leaves the app
with no way to learn the real PID. ``_stop_own_aria2`` therefore always hit
"No PID file found" and aria2 kept running after the app quit.

What this does instead
----------------------
* aria2c is started in the foreground as our own child (no ``--daemon``),
  so its PID is known; we write the PID file ourselves.
* ``--stop-with-process=<our pid>`` makes aria2 exit on its own when the app
  dies for any reason (crash, SIGKILL, closed terminal).
* ``stop()`` only ever touches aria2 processes that are ours: the child we
  spawned, the PID in our file, or an orphan started by an older version
  with *our* ``--conf-path``. Other aria2 instances (e.g. one the user runs
  in a terminal) are never killed; ``pkill -f aria2c`` used to hit them.
"""

from __future__ import annotations

import atexit
import os
import signal
import subprocess
import time
from typing import List, Optional

CONFIG_DIR = os.path.expanduser("~/.config/felfelDM")
CONF_PATH = os.path.join(CONFIG_DIR, "aria2.conf")
PID_FILE = os.path.join(CONFIG_DIR, "aria2.pid")

_proc: Optional[subprocess.Popen] = None
_atexit_registered = False


def _cmdline(pid: int) -> List[str]:
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            raw = f.read()
    except OSError:
        return []
    return [a.decode("utf-8", "replace") for a in raw.split(b"\0") if a]


def _is_aria2(pid: int, conf_path: Optional[str] = None) -> bool:
    """True if `pid` is an aria2c process (optionally started with conf_path).

    Checking the command line protects against a stale PID file whose number
    has since been reused by an unrelated process.
    """
    args = _cmdline(pid)
    if not args or os.path.basename(args[0]) != "aria2c":
        return False
    if conf_path is not None:
        return f"--conf-path={conf_path}" in args
    return True


def find_own_pids(conf_path: str = CONF_PATH) -> List[int]:
    """aria2c processes of this user started with our config file."""
    pids: List[int] = []
    try:
        entries = os.listdir("/proc")
    except OSError:
        return pids
    uid = os.getuid()
    for name in entries:
        if not name.isdigit():
            continue
        pid = int(name)
        try:
            if os.stat(f"/proc/{pid}").st_uid != uid:
                continue
        except OSError:
            continue
        if _is_aria2(pid, conf_path):
            pids.append(pid)
    return pids


def _write_pid_file(pid: int, pid_file: str) -> None:
    try:
        os.makedirs(os.path.dirname(pid_file), exist_ok=True)
        fd = os.open(pid_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(str(pid))
    except OSError as e:
        print(f"⚠️ Could not write aria2 PID file: {e}")


def spawn(
    conf_path: str = CONF_PATH,
    pid_file: str = PID_FILE,
    parent_pid: Optional[int] = None,
) -> subprocess.Popen:
    """Start aria2c as our child and remember it. Raises FileNotFoundError
    when aria2c is not installed."""
    global _proc, _atexit_registered

    cmd = [
        "aria2c",
        "--enable-rpc",
        f"--conf-path={conf_path}",
        # aria2 quits by itself when we are gone, even after a crash/SIGKILL.
        f"--stop-with-process={parent_pid or os.getpid()}",
    ]
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        # Own session: a Ctrl+C in the launching terminal must not hit it.
        start_new_session=True,
    )
    _proc = proc
    _write_pid_file(proc.pid, pid_file)

    if not _atexit_registered:
        _atexit_registered = True
        atexit.register(stop)
    return proc


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    # A zombie still answers kill(pid, 0); /proc shows it as state Z.
    try:
        with open(f"/proc/{pid}/stat", "rb") as f:
            state = f.read().rsplit(b")", 1)[1].split()[0]
        return state != b"Z"
    except (OSError, IndexError):
        return False


def stop(
    timeout: float = 3.0,
    conf_path: str = CONF_PATH,
    pid_file: str = PID_FILE,
) -> List[int]:
    """Stop every aria2c that belongs to FelfelDM. Returns the PIDs stopped.

    SIGTERM first (aria2 saves its session on a clean exit), SIGKILL for
    anything still alive after `timeout`. Safe to call repeatedly.
    """
    global _proc

    pids = set()
    if _proc is not None and _proc.poll() is None:
        pids.add(_proc.pid)

    try:
        with open(pid_file) as f:
            file_pid = int(f.read().strip())
        if _is_aria2(file_pid):
            pids.add(file_pid)
    except (OSError, ValueError):
        pass

    pids.update(find_own_pids(conf_path))
    pids.discard(os.getpid())

    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _proc is not None:
            _proc.poll()  # reap our child so it is not left as a zombie
        if not any(_alive(p) for p in pids):
            break
        time.sleep(0.1)

    for pid in pids:
        if _alive(pid):
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
    if _proc is not None:
        try:
            _proc.wait(timeout=1.0)
        except Exception:
            pass
        _proc = None

    try:
        os.remove(pid_file)
    except OSError:
        pass
    return sorted(pids)
