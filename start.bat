@echo off
:: Manual recovery launcher for Purifier Dashboard.
:: Idempotent: checks Flask AND tunnel independently, starts whichever is missing.
:: Safe to double-click anytime — will NEVER break a working setup.

cd /d D:\UsersClaude\Xavier\Claude_Projects\Personal\XiaomiPurifier

set FLASK_UP=0
set TUNNEL_UP=0

:: Check Flask
netstat -ano | findstr ":5050.*LISTENING" >nul 2>nul
if %errorlevel%==0 set FLASK_UP=1

:: Check tunnel (any ssh.exe process counts)
tasklist /fi "imagename eq ssh.exe" 2>nul | findstr /i "ssh.exe" >nul
if %errorlevel%==0 set TUNNEL_UP=1

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
  ssh -o ConnectTimeout=5 root@152.42.168.105 "fuser -k 8101/tcp 2>/dev/null" >nul 2>nul
  timeout /t 2 /nobreak >nul
  start /B cmd /c ":loop & ssh -R 8101:localhost:5050 -N -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -o ExitOnForwardFailure=yes root@152.42.168.105 & timeout /t 5 /nobreak >nul & goto loop"
  echo [OK] SSH tunnel launched
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
