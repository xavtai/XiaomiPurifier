# Register the PurifierDashboardLogon scheduled task.
# Triggers start-silent.vbs immediately on user logon (no 7+ min Startup folder delay).
# Runs in user context — no admin required.
# Usage:  powershell -NoProfile -ExecutionPolicy Bypass -File setup-logon-task.ps1

$action = New-ScheduledTaskAction -Execute 'wscript.exe' -Argument '"D:\UsersClaude\Xavier\Claude_Projects\Personal\XiaomiPurifier\start-silent.vbs"'
$trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName "PurifierDashboardLogon" -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force

Write-Host "Task registered. Verify with: schtasks /query /tn PurifierDashboardLogon"
