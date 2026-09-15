"""config 测试:路径分流与读写往返,全部落在 tmp_path,不碰真实状态文件。"""

from pathlib import Path

import pytest

import config


def test_source_mode_path_is_repo_state(monkeypatch):
    monkeypatch.setattr(config.sys, "frozen", False, raising=False)
    expected = Path(config.__file__).resolve().parent / "state.json"
    assert config.config_path() == expected


def test_frozen_mode_path_under_appdata(monkeypatch, tmp_path):
    monkeypatch.setattr(config.sys, "frozen", True, raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path))
    p = config.config_path()
    assert p == tmp_path / "ZCodeTokensCard" / "state.json"
    assert p.parent.is_dir()  # 冻结模式会建目录


def test_frozen_appdata_missing_falls_back_home(monkeypatch, tmp_path):
    monkeypatch.setattr(config.sys, "frozen", True, raising=False)
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert config.config_path().parent.parent == tmp_path


def test_roundtrip(tmp_path):
    p = tmp_path / "state.json"
    config.save(p, pos_x=5, pos_y=6)
    assert config.load(p) == {"pos_x": 5, "pos_y": 6}


def test_save_merges_not_replaces(tmp_path):
    p = tmp_path / "state.json"
    config.save(p, pos_x=1)
    config.save(p, pos_y=2)
    assert config.load(p) == {"pos_x": 1, "pos_y": 2}


def test_load_missing_returns_empty(tmp_path):
    assert config.load(tmp_path / "absent.json") == {}


def test_load_corrupt_returns_empty(tmp_path):
    p = tmp_path / "state.json"
    p.write_text("not json", "utf-8")
    assert config.load(p) == {}


def test_save_failure_silent(tmp_path):
    # 父目录不存在时写入失败,静默不抛
    config.save(tmp_path / "no_dir" / "state.json", pos_x=1)
