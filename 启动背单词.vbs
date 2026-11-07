Set sh = CreateObject("WScript.Shell")
here = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = here
pyw = "D:\software\anaconda\pythonw.exe"
If Not CreateObject("Scripting.FileSystemObject").FileExists(pyw) Then pyw = "D:\software\anaconda\python.exe"
sh.Run """" & pyw & """ """ & here & "\app\main.py""", 0, False
