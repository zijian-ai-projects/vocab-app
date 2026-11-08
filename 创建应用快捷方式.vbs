Option Explicit
' Create an icon shortcut only inside this plugin directory; never change the desktop or registry.
Dim shell, fs, root, title, launch, icon, link
Set shell = CreateObject("WScript.Shell")
Set fs = CreateObject("Scripting.FileSystemObject")
root = fs.GetParentFolderName(WScript.ScriptFullName)
title = ChrW(&H80CC) & ChrW(&H5355) & ChrW(&H8BCD)
launch = root & "\" & ChrW(&H542F) & ChrW(&H52A8) & title & ".vbs"
icon = root & "\assets\vocab-card.ico"
If Not fs.FileExists(launch) Or Not fs.FileExists(icon) Then
    WScript.Echo "Missing launcher or icon. Keep this script in the plugin directory."
    WScript.Quit 1
End If
On Error Resume Next
Set link = shell.CreateShortcut(root & "\" & title & ".lnk")
link.TargetPath = shell.ExpandEnvironmentStrings("%WINDIR%") & "\System32\wscript.exe"
link.Arguments = """" & launch & """"
link.WorkingDirectory = root
link.IconLocation = icon & ",0"
link.Description = "VocabCard - vocabulary study"
link.WindowStyle = 1
link.Save
If Err.Number <> 0 Then
    WScript.Echo "Could not create shortcut: " & Err.Description
    WScript.Quit 1
End If
On Error GoTo 0
WScript.Echo "Created VocabCard shortcut in the plugin directory. Double-click it to start."
