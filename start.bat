@echo off
:: Manual recovery launcher for Purifier Dashboard.
:: Idempotent: checks Flask AND tunnel independently, starts whichever is missing.
:: Safe to double-click anytime — will NEVER break a working setup.

cd /d D:\UsersClaude\Xavier\Claude_Projects\Personal\XiaomiPurifier

set FLASK_UP=0
set TUNNEL_UP=0

:: Check Flask — real HTTP request, not just port listening
for /f %%c in ('curl -s -o nul -w "%%{http_code}" --max-time 3 http://127.0.0.1:5050/') do set FLASK_CODE=%%c
if "%FLASK_CODE%"=="200" set FLASK_UP=1

:: Check tunnel — real curl through tunnel from VPS side (catches zombie tunnels)
:: Zombie case: ssh.exe exists but forwarding is broken. Only trust actual data flow.
for /f %%c in ('ssh -o ConnectTimeout=3 -o BatchMode=yes root@152.42.168.105 "curl -m 3 -s -o /dev/null -w %%{http_code} http://127.0.0.1:8101/" 2^>nul') do set TUNNEL_CODE=%%c
if "%TUNNEL_CODE%"=="200" set TUNNEL_UP=1

echo.
echo === Air Purifier Dashboard ===
if %FLASK_UP%==1 (echo   Flask:  UP) else (echo   Flask:  DOWN)
if %TUNNEL_UP%==1 (echo   Tunnel: UP) else (echo   Tunnel: DOWN)
echo.

if %FLASK_UP%==1 if %TUNNEL_UP%==1 (
  echo Both already running. Nothing to do.
  echo.
  echo   Local:  http://localhost:5050
  echo   Remote: https://app.xavbuilds.com/purifier/
  timeout /t 5 /nobreak >nul
  exit /b 0
)

:: === Start tunnel if needed ===
if %TUNNEL_UP%==0 (
  echo Starting SSH tunnel...
  :: Kill any zombie ssh.exe and stale VPS-side sshd holding port 8101
  taskkill /f /im ssh.exe >nul 2>nul
  ssh -o ConnectTimeout=5 root@152.42.168.105 "fuser -k 8101/tcp 2>/dev/null" >nul 2>nul
  timeout /t 2 /nobreak >nul
  start "" /B "D:\UsersClaude\Xavier\Claude_Projects\Personal\XiaomiPurifier\ssh-tunnel.bat"
  echo [OK] SSH tunnel launched via ssh-tunnel.bat
  echo.
)

:: === Start Flask if needed ===
if %FLASK_UP%==0 (
  echo Loading .env...
  for /f "usebackq tokens=1,* delims==" %%a in (".env") do (
    if not "%%a"=="" if not "%%a"==" " (
      set "%%a=%%b"
    )
  )
  echo Starting Flask...
  echo.
  echo   Local:  http://localhost:5050
  echo   Remote: https://app.xavbuilds.com/purifier/
  echo   Close this window to stop Flask.
  echo.
  where python >nul 2>nul
  if %errorlevel%==0 (
    python app.py
  ) else (
    "%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe" app.py
  )
) else (
  echo Flask already running — tunnel started in background.
  echo.
  echo   Local:  http://localhost:5050
  echo   Remote: https://app.xavbuilds.com/purifier/
  echo.
  echo This window will close in 10 seconds.
  timeout /t 10 /nobreak >nul
)
