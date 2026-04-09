' Launch Air Purifier Dashboard silently on Windows startup
' Checks Flask AND SSH tunnel independently — launches whichever is missing

' --- Check Flask ---
Set http = CreateObject("MSXML2.ServerXMLHTTP.6.0")
flaskUp = False
On Error Resume Next
http.setTimeouts 3000, 3000, 3000, 3000
http.Open "GET", "http://localhost:5050/", False
http.Send
If Err.Number = 0 Then flaskUp = (http.Status = 200)
On Error GoTo 0

' --- Check SSH tunnel (any ssh.exe is good enough) ---
tunnelUp = False
Set wmi = GetObject("winmgmts:\\.\root\cimv2")
Set sshProcs = wmi.ExecQuery("SELECT * FROM Win32_Process WHERE Name='ssh.exe'")
If sshProcs.Count > 0 Then tunnelUp = True

' --- Both up? Nothing to do ---
If flaskUp And tunnelUp Then WScript.Quit

Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "D:\UsersClaude\Xavier\Claude_Projects\Personal\XiaomiPurifier"

If Not flaskUp Then
  WshShell.Run """C:\Users\Xavie\AppData\Local\Python\pythoncore-3.14-64\pythonw.exe"" ""D:\UsersClaude\Xavier\Claude_Projects\Personal\XiaomiPurifier\watchdog.pyw""", 0, False
End If

If Not tunnelUp Then
  WshShell.Run """D:\UsersClaude\Xavier\Claude_Projects\Personal\XiaomiPurifier\ssh-tunnel.bat""", 0, False
End If
