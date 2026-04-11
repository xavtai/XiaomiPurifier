#!/bin/bash
# Restart Flask + SSH tunnel from bash (used by Claude Code)
# Equivalent of start.bat but for unix shell

set -euo pipefail

cd /d/UsersClaude/Xavier/Claude_Projects/Personal/XiaomiPurifier

# Lockfile to prevent concurrent runs
LOCKFILE="/tmp/purifier-restart.lock"
if [ -f "$LOCKFILE" ]; then
  LOCK_PID=$(cat "$LOCKFILE" 2>/dev/null)
  if kill -0 "$LOCK_PID" 2>/dev/null; then
    echo "ERROR: Another restart.sh is running (PID $LOCK_PID). Aborting."
    exit 1
  fi
  rm -f "$LOCKFILE"
fi
echo $$ > "$LOCKFILE"
trap 'rm -f "$LOCKFILE"' EXIT

# Load env vars from .env — handles CRLF, quotes, comments, and = in values
IQAIR_KEY=""
WAQI_TOKEN=""
if [ -f .env ]; then
  while IFS= read -r line || [ -n "$line" ]; do
    line=$(echo "$line" | tr -d '\r')              # strip CRLF
    [[ "$line" =~ ^#.*$ || -z "$line" ]] && continue  # skip comments/empty
    key="${line%%=*}"
    val="${line#*=}"
    val="${val%\"}" && val="${val#\"}"              # strip surrounding quotes
    val="${val%\'}" && val="${val#\'}"
    case "$key" in
      IQAIR_KEY)  IQAIR_KEY="$val" ;;
      WAQI_TOKEN) WAQI_TOKEN="$val" ;;
    esac
  done < .env
fi

if [ -z "$IQAIR_KEY" ] || [ -z "$WAQI_TOKEN" ]; then
  echo "WARNING: Missing API keys — outdoor AQI will be disabled"
fi

# Kill existing Flask if running on port 5050
FLASK_PID=$(netstat -ano 2>/dev/null | grep ':5050.*LISTENING' | awk '{print $NF}' | head -1 || true)
if [ -n "${FLASK_PID:-}" ] && [ "${FLASK_PID:-}" != "0" ]; then
  echo "Killing existing Flask (PID $FLASK_PID)..."
  taskkill //F //PID "$FLASK_PID" 2>/dev/null || true
  sleep 2
  # Verify it's actually dead
  if netstat -ano 2>/dev/null | grep -q ':5050.*LISTENING'; then
    echo "ERROR: Port 5050 still in use after kill. Aborting."
    exit 1
  fi
fi

# Kill existing SSH tunnels to VPS (using tasklist + grep, avoiding deprecated wmic)
for PID in $(tasklist 2>/dev/null | grep -i 'ssh\.exe' | awk '{print $2}' || true); do
  # Check command line via PowerShell (wmic is deprecated on Win 11)
  if powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"ProcessId=$PID\" | Select-Object -ExpandProperty CommandLine" 2>/dev/null | grep -q "152.42.168.105"; then
    echo "Killing existing SSH tunnel (PID $PID)..."
    taskkill //F //PID "$PID" 2>/dev/null || true
  fi
done
sleep 1

# Start Flask (inline env vars to ensure child process inherits them)
IQAIR_KEY="$IQAIR_KEY" WAQI_TOKEN="$WAQI_TOKEN" nohup python app.py >> flask.log 2>&1 &
FLASK_NEW_PID=$!
echo "Flask starting (PID $FLASK_NEW_PID)..."

# Wait for Flask to be ready — check HTTP status, not just connection
FLASK_UP=false
for i in $(seq 1 15); do
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 2 http://localhost:5050/ 2>/dev/null) || true
  if [ "$HTTP_CODE" = "200" ]; then
    FLASK_UP=true
    echo "Flask: UP (200)"
    break
  fi
  sleep 1
done
if ! $FLASK_UP; then
  echo "ERROR: Flask failed to start within 15s. Check flask.log"
  tail -5 flask.log 2>/dev/null
  exit 1
fi

# Clear stale tunnel on VPS before starting new one
echo "Clearing stale VPS tunnel..."
ssh -o ConnectTimeout=5 -o BatchMode=yes root@152.42.168.105 "fuser -k 8101/tcp 2>/dev/null" 2>/dev/null || true
sleep 2

# Start SSH tunnel with reconnect loop
nohup bash -c 'while true; do
  ssh -o ConnectTimeout=5 -o BatchMode=yes root@152.42.168.105 "fuser -k 8101/tcp 2>/dev/null" 2>/dev/null
  sleep 1
  ssh -R 8101:127.0.0.1:5050 -N \
    -o ServerAliveInterval=30 \
    -o ServerAliveCountMax=3 \
    -o ExitOnForwardFailure=yes \
    root@152.42.168.105 2>>ssh_tunnel.log
  echo "$(date) Tunnel died, reconnecting in 5s..." >> ssh_tunnel.log
  sleep 5
done' > /dev/null 2>&1 &
echo "SSH tunnel starting with auto-reconnect..."

# Verify tunnel
sleep 4
REMOTE_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 https://app.xavbuilds.com/purifier/ 2>/dev/null || true)
if [ "$REMOTE_CODE" = "401" ] || [ "$REMOTE_CODE" = "200" ]; then
  echo "Tunnel: UP"
else
  echo "Tunnel: may still be connecting (got $REMOTE_CODE)"
fi

echo "Done. Local: http://localhost:5050 | Remote: https://app.xavbuilds.com/purifier/"
