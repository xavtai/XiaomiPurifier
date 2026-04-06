@echo off
cd /d D:\UsersClaude\Xavier\Claude_Projects\Personal\XiaomiPurifier

:: === Duplicate check: exit if Flask is already running ===
netstat -ano | findstr ":5050.*LISTENING" >nul 2>nul
if %errorlevel%==0 (
  echo Flask is already running on port 5050. Nothing to do.
  timeout /t 3 /nobreak >nul
  exit /b 0
)

echo Starting Air Purifier Dashboard...
echo.

:: Load API keys from .env
for /f "usebackq tokens=1,* delims==" %%a in (".env") do (
  if not "%%a"=="" if not "%%a"==" " (
    set "%%a=%%b"
  )
)

:: === SSH tunnel: clear stale VPS tunnel, then start ===
echo Clearing stale VPS tunnel...
ssh -o ConnectTimeout=5 root@152.42.168.105 "fuser -k 8101/tcp 2>/dev/null" >nul 2>nul
taskkill /f /im ssh.exe >nul 2>nul
timeout /t 2 /nobreak >nul
start /B cmd /c ":loop & ssh -R 8101:localhost:5050 -N -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -o ExitOnForwardFailure=yes root@152.42.168.105 & timeout /t 5 /nobreak >nul & goto loop"
echo [OK] SSH tunnel started

echo.
echo  Local:  http://localhost:5050
echo  Remote: https://app.xavbuilds.com/purifier/
echo  Close this window to stop Flask.
echo.

:: === Start Flask (foreground) ===
where python >nul 2>nul
if %errorlevel%==0 (
  python app.py
) else (
  "%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe" app.py
)
