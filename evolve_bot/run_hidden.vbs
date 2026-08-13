' Launches a PowerShell script with zero visible window - not "hide it
' after it flashes" (what -WindowStyle Hidden alone does, unreliably,
' since PowerShell still creates the console window briefly before it
' processes that argument), but never creates the window at all.
' WScript.Shell.Run's third argument (0 = hidden window style) controls
' this at the actual process-creation level.
'
' Usage: wscript.exe run_hidden.vbs "<path to .ps1>"
Set objShell = CreateObject("WScript.Shell")
scriptPath = WScript.Arguments(0)
objShell.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -File """ & scriptPath & """", 0, False
