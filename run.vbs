' Launch ZCode usage float card without a console window.
' NOTE: keep this file ASCII-only. wscript reads .vbs as ANSI (GBK here);
' UTF-8 Chinese comments break parsing ("missing object" errors).
' NOTE: absolute pythonw via %LOCALAPPDATA% expansion - plain "pythonw" on
' PATH may resolve to another venv without PySide6 (hermes venv pitfall).
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = "D:\ai\tokens"
pyw = sh.ExpandEnvironmentStrings("%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe")
sh.Run """" & pyw & """ main.py", 0, False
