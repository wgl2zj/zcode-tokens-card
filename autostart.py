"""开机自启动:HKCU Run 键读写,只操作本程序专属条目。

启动命令按运行形态分流:打包(PyInstaller 冻结)模式下 exe 自身即入口;
源码模式复用 run.vbs 的思路,用 pythonw 跑 main.py 保持无控制台窗口。
"""

import sys
from pathlib import Path
import winreg

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE_NAME = "ZCodeTokensCard"


def command() -> str:
    """写入 Run 键的启动命令;路径加引号以容忍空格。"""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    pyw = Path(sys.executable).with_name("pythonw.exe")
    exe = pyw if pyw.exists() else Path(sys.executable)
    main_py = Path(__file__).resolve().parent / "main.py"
    return f'"{exe}" "{main_py}"'


def is_enabled() -> bool:
    """Run 键里存在本程序条目即视为已开启;读取失败按未开启处理。"""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            winreg.QueryValueEx(key, _VALUE_NAME)
            return True
    except FileNotFoundError:
        return False
    except OSError:
        return False


def stored_command() -> str | None:
    """Run 键中本程序条目的当前值;不存在或读取失败返回 None。"""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, _VALUE_NAME)
            return value
    except (FileNotFoundError, OSError):
        return None


def sync() -> bool:
    """路径漂移自愈:条目存在但指向与当前命令不一致时覆盖为新命令。

    条目不存在(用户未开启)时绝不动,避免把自启动偷偷打开;
    读取失败同样保守跳过。返回是否发生了修复。
    """
    stored = stored_command()
    if stored is None or stored == command():
        return False
    enable()
    return True


def enable() -> None:
    """写入/覆盖本程序条目;失败抛 OSError(由 UI 层回弹勾选)。"""
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, _VALUE_NAME, 0, winreg.REG_SZ, command())


def disable() -> None:
    """删除本程序条目;本就未开启时幂等通过,其余失败抛 OSError。"""
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0,
                        winreg.KEY_SET_VALUE) as key:
        try:
            winreg.DeleteValue(key, _VALUE_NAME)
        except FileNotFoundError:
            pass
