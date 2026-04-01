#!/bin/bash
# Restart Flask + SSH tunnel from bash (used by Claude Code)
# Equivalent of start.bat but for unix shell

cd /d/UsersClaude/Xavier/Claude_Projects/XiaomiPurifier

# Load env vars (inline with nohup to ensure they reach the child process)
IQAIR_KEY=$(grep IQAIR_KEY .env | cut -d= -f2)
WAQI_TOKEN=$(grep WAQI_TOKEN .env | cut -d= -f2)

# Kill existing Flask if running on port 5000
FLASK_PID=$(netstat -ano 2>/dev/null | grep ':5000.*LISTENING' | awk '{print $5}' | head -1)
if [ -n "$FLASK_PID" ]; then
  echo "Killing existing Flask (PID $FLASK_PID)..."
  taskkill //F //PID "$FLASK_PID" 2>/dev/null
  sleep 1
fi

# Kill existing SSH tunnels to VPS
for PID in $(tasklist 2>/dev/null | grep ssh | awk '{print $2}'); do
  # Only kill ssh processes connecting to our VPS
  if wmic process where "ProcessId=$PID" get CommandLine 2>/dev/null | grep -q "152.42.168.105"; then
    echo "Killing existing SSH tunnel (PID $PID)..."
    taskkill //F //PID "$PID" 2>/dev/null
  fi
done
sleep 1

# Start Flask (inline env vars to ensure child process inherits them)
IQAIR_KEY="$IQAIR_KEY" WAQI_TOKEN="$WAQI_TOKEN" nohup python app.py > flask.log 2>&1 &
echo "Flask starting (PID $!)..."

# Wait for Flask to be ready
for i in $(seq 1 10); do
  if curl -s -o /dev/null -w "" --max-time 1 http://localhost:5000/ 2>/dev/null; then
    echo "Flask: UP"
    break
  fi
  sleep 1
done

# Start SSH tunnel with reconnect loop
nohup bash -c 'while true; do
  ssh -R 8100:localhost:5000 -N \
    -o ServerAliveInterval=30 \
    -o ServerAliveCountMax=3 \
    -o ExitOnForwardFailure=yes \
    root@152.42.168.105 2>>ssh_tunnel.log
  echo "$(date) Tunnel died, reconnecting in 5s..." >> ssh_tunnel.log
  sleep 5
done' > /dev/null 2>&1 &
echo "SSH tunnel starting with auto-reconnect..."

# Verify tunnel
sleep 3
REMOTE_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 https://app.xavbuilds.com/purifier/ 2>/dev/null)
if [ "$REMOTE_CODE" = "401" ] || [ "$REMOTE_CODE" = "200" ]; then
  echo "Tunnel: UP"
else
  echo "Tunnel: may still be connecting (got $REMOTE_CODE)"
fi

echo "Done. Local: http://localhost:5000 | Remote: https://app.xavbuilds.com/purifier/"
