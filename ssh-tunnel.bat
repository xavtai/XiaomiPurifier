@echo off
:: Self-reconnecting SSH reverse tunnel for Purifier Dashboard
:: Launched hidden by start-silent.vbs / Task Scheduler logon trigger
:: IMPORTANT: uses 127.0.0.1 (not localhost) — Windows native ssh resolves
:: localhost to ::1 first, and Flask is IPv4-only → tunnel would be zombie.

cd /d D:\UsersClaude\Xavier\Claude_Projects\Personal\XiaomiPurifier

:loop
echo [%date% %time%] Starting ssh tunnel >> ssh-tunnel.log
ssh -R 8101:127.0.0.1:5050 -N ^
    -o ServerAliveInterval=30 ^
    -o ServerAliveCountMax=3 ^
    -o ExitOnForwardFailure=yes ^
    root@152.42.168.105 2>> ssh-tunnel.log
echo [%date% %time%] ssh exited with %errorlevel%, sleeping 5s >> ssh-tunnel.log
timeout /t 5 /nobreak >nul
goto loop
