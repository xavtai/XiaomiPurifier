"""
Flask + SSH tunnel watchdog for Air Purifier Dashboard.
Runs silently (no console window with .pyw extension).
Checks health every 15s, restarts if down. Prevents duplicates.
"""
import subprocess, time, os, sys, socket, urllib.request, urllib.error

os.chdir(r"D:\UsersClaude\Xavier\Claude_Projects\Personal\XiaomiPurifier")

LOG = os.path.join(os.path.dirname(__file__), "watchdog.log")
ENV_FILE = os.path.join(os.path.dirname(__file__), ".env")
APP_PY = os.path.join(os.path.dirname(__file__), "app.py")
PYTHON = sys.executable
VPS = "root@152.42.168.105"
CHECK_INTERVAL = 15
RESTART_DELAY = 10
MAX_CRASHES = 5
BACKOFF_DELAY = 300
_NO_WIN = subprocess.CREATE_NO_WINDOW


def log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(LOG, "a") as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass


def rotate_log():
    """Keep only last 500 lines of watchdog.log."""
    try:
        with open(LOG) as f:
            lines = f.readlines()
        if len(lines) > 500:
            with open(LOG, "w") as f:
                f.writelines(lines[-500:])
    except Exception:
        pass


def load_env():
    if not os.path.exists(ENV_FILE):
        return
    with open(ENV_FILE) as f:
        for line in f:
            line = line.strip().replace("\r", "")
            if "=" in line and not line.startswith("#"):
                key, _, val = line.partition("=")
                os.environ[key.strip()] = val.strip()


def is_flask_up():
    try:
        req = urllib.request.urlopen("http://localhost:5050/", timeout=5)
        return req.getcode() == 200
    except Exception:
        return False


def is_port_listening(port=5050):
    try:
        with socket.create_connection(("localhost", port), timeout=2):
            return True
    except Exception:
        return False


def is_tunnel_healthy():
    """Check tunnel via the public remote URL (avoids SSH subprocess issues from pythonw)."""
    try:
        req = urllib.request.Request("https://app.xavbuilds.com/purifier/",
                                     method="HEAD")
        resp = urllib.request.urlopen(req, timeout=10)
        return resp.status == 200
    except urllib.error.HTTPError as e:
        return e.code == 401  # basic auth challenge = tunnel is working
    except Exception:
        return False


def kill_local_ssh():
    """Kill all local ssh.exe processes."""
    try:
        subprocess.run(
            ["taskkill", "/f", "/im", "ssh.exe"],
            capture_output=True, timeout=5,
            creationflags=_NO_WIN,
        )
    except Exception:
        pass


def start_flask():
    log("Starting Flask")
    return subprocess.Popen(
        [PYTHON, APP_PY],
        cwd=os.path.dirname(__file__),
        env=os.environ.copy(),
        creationflags=_NO_WIN,
    )


def main():
    load_env()
    rotate_log()
    log("Watchdog started")

    flask_proc = None
    crash_count = 0
    tunnel_check_counter = 0

    while True:
        # --- SSH tunnel health nudge ---
        # SSH tunnel is managed by ssh-tunnel.bat (launched by start-silent.vbs).
        # Watchdog only nudges it: every 4th cycle (~60s), check public URL.
        # If unhealthy, kill ssh.exe so the batch file's :loop reconnects within 5s.
        tunnel_check_counter += 1
        if tunnel_check_counter >= 4:
            tunnel_check_counter = 0
            if not is_tunnel_healthy():
                log("Tunnel unhealthy — killing ssh.exe to trigger batch reconnect")
                kill_local_ssh()

        # --- Flask ---
        if is_flask_up():
            crash_count = 0
        elif is_port_listening():
            pass  # Starting up or another app on the port
        else:
            crash_count += 1
            log(f"Flask down (crash #{crash_count})")

            if flask_proc and flask_proc.poll() is not None:
                flask_proc = None

            if not is_port_listening():
                if crash_count >= MAX_CRASHES:
                    log(f"Too many crashes ({crash_count}). Backing off {BACKOFF_DELAY}s")
                    time.sleep(BACKOFF_DELAY)
                    crash_count = 0
                else:
                    time.sleep(RESTART_DELAY)

                flask_proc = start_flask()
                time.sleep(8)

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
