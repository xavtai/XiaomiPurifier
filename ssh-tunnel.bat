@echo off
:: Self-reconnecting SSH reverse tunnel for Purifier Dashboard
:: Launched hidden by start-silent.vbs at Windows startup
:: Runs in its own cmd.exe process so SSH has a valid console

:loop
ssh -R 8101:localhost:5050 -N ^
    -o ServerAliveInterval=30 ^
    -o ServerAliveCountMax=3 ^
    -o ExitOnForwardFailure=yes ^
    root@152.42.168.105
timeout /t 5 /nobreak >nul
goto loop
