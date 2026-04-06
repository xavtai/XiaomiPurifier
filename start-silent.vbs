' Start Air Purifier Dashboard watchdog silently on Windows startup
' Checks if already running first to prevent duplicates

Set http = CreateObject("MSXML2.ServerXMLHTTP.6.0")
On Error Resume Next
http.setTimeouts 3000, 3000, 3000, 3000
http.Open "GET", "http://localhost:5050/", False
http.Send
statusCode = http.Status
On Error GoTo 0

If statusCode = 200 Then
  ' Already running — do nothing
  WScript.Quit
End If

' Not running — launch watchdog.pyw (runs silently, no console)
Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "D:\UsersClaude\Xavier\Claude_Projects\Personal\XiaomiPurifier"
WshShell.Run """C:\Users\Xavie\AppData\Local\Python\pythoncore-3.14-64\pythonw.exe"" ""D:\UsersClaude\Xavier\Claude_Projects\Personal\XiaomiPurifier\watchdog.pyw""", 0, False
