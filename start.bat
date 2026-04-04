@echo off
echo Starting Air Purifier Dashboard...
echo.

cd /d D:\UsersClaude\Xavier\Claude_Projects\XiaomiPurifier

:: Load API keys from .env file
for /f "usebackq tokens=1,* delims==" %%a in (".env") do (
  if not "%%a"=="" if not "%%a"==" " (
    set "%%a=%%b"
  )
)

:: Start SSH tunnel with auto-reconnect (runs in background)
start /B cmd /c ":loop & ssh -R 8100:localhost:5000 -N -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -o ExitOnForwardFailure=yes root@152.42.168.105 & timeout /t 5 /nobreak >nul & goto loop"

echo [OK] SSH tunnel started with auto-reconnect
echo.
echo  Local:  http://localhost:5000
echo  Remote: https://app.xavbuilds.com/purifier/
echo.
echo  Close this window to stop everything.
echo.

:: Start Flask (foreground)
where python >nul 2>nul
if %errorlevel%==0 (
  python app.py
) else (
  "%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe" app.py
)
