Option Explicit
Dim shell, fso, folder, command
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
folder = fso.GetParentFolderName(WScript.ScriptFullName)
command = Chr(34) & folder & "\START-SUPERVISOR.cmd" & Chr(34)
shell.Run command, 0, False
