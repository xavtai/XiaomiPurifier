"""
Flask + SSH tunnel watchdog for Air Purifier Dashboard.
Runs silently (no console window with .pyw extension).
Checks health every 15s, restarts if down. Prevents duplicates.
"""
import subprocess, time, os, sys, socket, urllib.request

os.chdir(r"D:\UsersClaude\Xavier\Claude_Projects\XiaomiPurifier")

LOG = os.path.join(os.path.dirname(__file__), "watchdog.log")
ENV_FILE = os.path.join(os.path.dirname(__file__), ".env")
APP_PY = os.path.join(os.path.dirname(__file__), "app.py")
PYTHON = sys.executable  # Use the same python that's running this script
VPS = "root@152.42.168.105"
CHECK_INTERVAL = 15  # seconds between health checks
RESTART_DELAY = 10
MAX_CRASHES = 5
BACKOFF_DELAY = 300  # 5 minutes


def log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}\n"
    try:
        with open(LOG, "a") as f:
            f.write(line)
    except Exception:
        pass


def load_env():
    """Load .env file into os.environ."""
    if not os.path.exists(ENV_FILE):
        return
    with open(ENV_FILE) as f:
        for line in f:
            line = line.strip().replace("\r", "")
            if "=" in line and not line.startswith("#"):
                key, _, val = line.partition("=")
                os.environ[key.strip()] = val.strip()


def is_flask_up():
    """Check if Flask is responding on port 5000."""
    try:
        req = urllib.request.urlopen("http://localhost:5000/", timeout=5)
        return req.getcode() == 200
    except Exception:
        return False


def is_port_listening(port=5000):
    """Check if anything is listening on the port."""
    try:
        with socket.create_connection(("localhost", port), timeout=2):
            return True
    except Exception:
        return False


def is_ssh_tunnel_running():
    """Check if an SSH tunnel process exists."""
    try:
        result = subprocess.run(
            ["tasklist", "/fi", "imagename eq ssh.exe"],
            capture_output=True, text=True, timeout=5
        )
        return "ssh.exe" in result.stdout
    except Exception:
        return False


def start_flask():
    """Start Flask app in background."""
    log("Starting Flask")
    env = os.environ.copy()
    proc = subprocess.Popen(
        [PYTHON, APP_PY],
        cwd=os.path.dirname(__file__),
        env=env,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    return proc


def start_ssh_tunnel():
    """Start SSH reverse tunnel in background."""
    log("Starting SSH tunnel")
    proc = subprocess.Popen(
        [
            "ssh", "-R", "8100:localhost:5000", "-N",
            "-o", "ServerAliveInterval=30",
            "-o", "ServerAliveCountMax=3",
            "-o", "ExitOnForwardFailure=yes",
            VPS,
        ],
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    return proc


def main():
    load_env()
    log("Watchdog started")

    flask_proc = None
    ssh_proc = None
    crash_count = 0

    while True:
        # --- SSH tunnel ---
        if ssh_proc is None or ssh_proc.poll() is not None:
            if not is_ssh_tunnel_running():
                ssh_proc = start_ssh_tunnel()
            # else: tunnel running externally, nothing to do

        # --- Flask ---
        if is_flask_up():
            # All good — reset crash counter
            crash_count = 0
        elif is_port_listening():
            # Port is open but not responding HTTP 200 — might be starting up
            pass
        else:
            # Flask is down
            crash_count += 1
            log(f"Flask down (crash #{crash_count})")

            # Clean up dead process
            if flask_proc and flask_proc.poll() is not None:
                flask_proc = None

            # Don't start if something else owns port 5000
            if not is_port_listening():
                if crash_count >= MAX_CRASHES:
                    log(f"Too many crashes ({crash_count}). Backing off {BACKOFF_DELAY}s")
                    time.sleep(BACKOFF_DELAY)
                    crash_count = 0
                else:
                    time.sleep(RESTART_DELAY)

                flask_proc = start_flask()
                # Give Flask time to bind port
                time.sleep(8)

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
