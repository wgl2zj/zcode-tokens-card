' 无控制台启动 ZCode 用量悬浮窗(双击运行)
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = "D:\ai\tokens"
sh.Run "pythonw main.py", 0, False
