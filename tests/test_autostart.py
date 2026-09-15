"""autostart 测试:内存假 winreg 锁住读写与失败语义,不碰真实注册表。"""

import re

import pytest

import autostart


class _FakeKey:
    """假键句柄:仅支持 with 语法,数据操作走 FakeWinreg 的模块级函数。"""

    def __init__(self, reg):
        self._reg = reg

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeWinreg:
    """只模拟 autostart 用到的最小 winreg 接口(模块级函数形态)。"""

    HKEY_CURRENT_USER = "HKCU"
    KEY_SET_VALUE = 1
    REG_SZ = "REG_SZ"
    FileNotFoundError = FileNotFoundError

    def __init__(self):
        self.values = {}
        self.fail_on = set()

    def OpenKey(self, root, path, reserved=0, access=0):
        if "open" in self.fail_on:
            raise PermissionError("open denied")
        return _FakeKey(self)

    def CreateKeyEx(self, root, path, reserved, access):
        if "create" in self.fail_on:
            raise PermissionError("create denied")
        return _FakeKey(self)

    def SetValueEx(self, key, name, reserved, type_, value):
        if "set" in self.fail_on:
            raise PermissionError("set denied")
        self.values[name] = value

    def QueryValueEx(self, key, name):
        if name not in self.values:
            raise FileNotFoundError(name)
        return self.values[name], self.REG_SZ

    def DeleteValue(self, key, name):
        if "delete" in self.fail_on:
            raise PermissionError("delete denied")
        if name not in self.values:
            raise FileNotFoundError(name)
        del self.values[name]


@pytest.fixture
def fake_reg(monkeypatch):
    reg = FakeWinreg()
    monkeypatch.setattr(autostart, "winreg", reg)
    return reg


def test_disabled_by_default(fake_reg):
    assert autostart.is_enabled() is False


def test_enable_writes_command(fake_reg):
    autostart.enable()
    assert fake_reg.values == {autostart._VALUE_NAME: autostart.command()}
    assert autostart.is_enabled() is True


def test_disable_removes_value(fake_reg):
    autostart.enable()
    autostart.disable()
    assert autostart.is_enabled() is False


def test_disable_idempotent_when_missing(fake_reg):
    autostart.disable()  # 未开启时删除不报错
    assert autostart.is_enabled() is False


def test_enable_failure_raises(fake_reg):
    fake_reg.fail_on.add("create")
    with pytest.raises(OSError):
        autostart.enable()
    assert autostart.is_enabled() is False


def test_set_failure_raises(fake_reg):
    fake_reg.fail_on.add("set")
    with pytest.raises(OSError):
        autostart.enable()


def test_delete_failure_raises(fake_reg):
    autostart.enable()
    fake_reg.fail_on.add("delete")
    with pytest.raises(OSError):
        autostart.disable()
    assert autostart.is_enabled() is True  # 删除失败不算已关闭


def test_read_failure_treated_as_disabled(fake_reg):
    autostart.enable()
    fake_reg.fail_on.add("open")
    assert autostart.is_enabled() is False


def test_only_own_entry_touched(fake_reg):
    """他人/其他程序的 Run 条目不得被增删改。"""
    fake_reg.values["OtherApp"] = '"C:\\other.exe"'
    autostart.enable()
    autostart.disable()
    assert fake_reg.values == {"OtherApp": '"C:\\other.exe"'}


def test_command_source_mode(fake_reg, monkeypatch):
    """源码模式:pythonw(缺则退回 python) + main.py,双引号包路径。"""
    cmd = autostart.command()
    parts = re.findall(r'"([^"]+)"', cmd)
    assert len(parts) == 2
    assert parts[0].lower().endswith(("pythonw.exe", "python.exe"))
    assert parts[1].endswith("main.py")


def test_command_frozen_mode(monkeypatch):
    """冻结(打包)模式:命令就是 exe 自身。"""
    monkeypatch.setattr(autostart.sys, "frozen", True, raising=False)
    monkeypatch.setattr(autostart.sys, "executable",
                        r"C:\app dir\ZCodeTokensCard.exe")
    assert autostart.command() == '"C:\\app dir\\ZCodeTokensCard.exe"'


# —— sync:启动时路径漂移自愈 ——

def test_sync_noop_when_missing(fake_reg):
    """未开启时 sync 绝不擅自开启。"""
    assert autostart.sync() is False
    assert fake_reg.values == {}


def test_sync_noop_when_up_to_date(fake_reg):
    autostart.enable()
    assert autostart.sync() is False
    assert fake_reg.values == {autostart._VALUE_NAME: autostart.command()}


def test_sync_rewrites_stale_path(fake_reg, monkeypatch):
    """exe/仓库挪位后(此处以源码→冻结形态变化模拟漂移),sync 覆盖为新命令。"""
    autostart.enable()  # 写入源码模式命令
    monkeypatch.setattr(autostart.sys, "frozen", True, raising=False)
    monkeypatch.setattr(autostart.sys, "executable",
                        r"D:\新位置\ZCodeTokensCard.exe")
    assert autostart.command() != autostart.stored_command()
    assert autostart.sync() is True
    assert fake_reg.values == {autostart._VALUE_NAME: autostart.command()}
    assert autostart.is_enabled() is True


def test_sync_read_failure_is_conservative_noop(fake_reg):
    autostart.enable()
    fake_reg.fail_on.add("open")   # 条目在但读不出 → 保守不动
    assert autostart.sync() is False
    assert autostart.is_enabled() is False


def test_stored_command_missing_returns_none(fake_reg):
    assert autostart.stored_command() is None
