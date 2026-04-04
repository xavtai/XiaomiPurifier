@echo off
cd /d D:\UsersClaude\Xavier\Claude_Projects\XiaomiPurifier

:: === Duplicate check: exit if Flask is already running ===
netstat -ano | findstr ":5000.*LISTENING" >nul 2>nul
if %errorlevel%==0 (
  echo Flask is already running on port 5000. Nothing to do.
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

:: === SSH tunnel: only start if not already running ===
tasklist /fi "imagename eq ssh.exe" 2>nul | findstr /i "ssh.exe" >nul 2>nul
if %errorlevel% neq 0 (
  start /B cmd /c ":loop & ssh -R 8100:localhost:5000 -N -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -o ExitOnForwardFailure=yes root@152.42.168.105 & timeout /t 5 /nobreak >nul & goto loop"
  echo [OK] SSH tunnel started
) else (
  echo [OK] SSH tunnel already running
)

echo.
echo  Local:  http://localhost:5000
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
