@echo off
echo Starting Air Purifier Dashboard...
echo.

cd /d D:\UsersClaude\Xavier\Claude_Projects\XiaomiPurifier

:: Outdoor AQI — IQAir (Mae Hia, nearest to Hang Dong), WAQI as fallback
set IQAIR_KEY=909478a1-319e-410b-b00b-4f7471062e5f
set WAQI_TOKEN=55d5cb4bfbcc67de8fc923d68e132005af92dfed

:: Start SSH tunnel with auto-reconnect (runs in background)
start /B cmd /c "echo SSH tunnel starting... && :loop && ssh -R 8100:localhost:5000 -N -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -o ExitOnForwardFailure=yes root@152.42.168.105 && echo Tunnel disconnected, reconnecting in 5s... && timeout /t 5 /nobreak >nul && goto loop"

echo [OK] SSH tunnel started with auto-reconnect
echo.

:: Start Flask app (stays in foreground)
echo  Local:  http://localhost:5000
echo  Remote: https://app.xavbuilds.com/purifier/
echo  Login:  admin / ****
echo.
echo  Background polling: every 10 seconds
echo  Close this window to stop everything.
echo.

python app.py
