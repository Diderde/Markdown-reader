# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-2.0-or-later
"""bootstrap.py 环境自举的单元测试（SSRF 校验、用户询问与主流程，不联网）。"""

from __future__ import annotations

from pathlib import Path

import pytest

import bootstrap


@pytest.fixture(autouse=True)
def isolate_bootstrap_root(tmp_path, monkeypatch):
    """所有用例都在临时目录里跑：否则 write() 会把 environment_report.txt 写进仓库根。"""
    monkeypatch.setattr(bootstrap, "ROOT", tmp_path)
    monkeypatch.setattr(bootstrap, "VENV", tmp_path / ".venv")


class TestValidatePublicHttps:
    def test_accepts_official_pypa_url(self):
        url = "https://bootstrap.pypa.io/get-pip.py"
        assert bootstrap.validate_public_https(url) == url

    def test_rejects_non_https(self):
        with pytest.raises(ValueError, match="https"):
            bootstrap.validate_public_https("http://bootstrap.pypa.io/get-pip.py")

    def test_rejects_unknown_host(self):
        with pytest.raises(ValueError, match="白名单"):
            bootstrap.validate_public_https("https://evil.example.com/get-pip.py")

    def test_rejects_localhost(self):
        with pytest.raises(ValueError, match="受限主机"):
            bootstrap.validate_public_https("https://localhost/get-pip.py")

    def test_rejects_host_resolving_to_loopback(self, monkeypatch):
        import socket

        info = (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))
        monkeypatch.setattr(
            bootstrap.socket, "getaddrinfo", lambda *a, **k: [info]
        )
        # 主机在白名单内但解析到环回地址 → 拒绝（防 DNS 重绑定）
        with pytest.raises(ValueError, match="受限网络"):
            bootstrap.validate_public_https("https://bootstrap.pypa.io/get-pip.py")

    def test_accepts_whitelisted_public_resolution(self, monkeypatch):
        import socket

        info = (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("2.18.236.20", 443))
        monkeypatch.setattr(bootstrap.socket, "getaddrinfo", lambda *a, **k: [info])
        assert bootstrap.validate_public_https("https://bootstrap.pypa.io/get-pip.py")


class TestAskContinue:
    def test_yes_answers(self, monkeypatch):
        for answer in ("y", "YES", "是", "S"):
            monkeypatch.setattr("builtins.input", lambda _p="", a=answer: a)
            assert bootstrap.ask_continue("继续？") is True

    def test_no_and_empty_default_reject(self, monkeypatch):
        for answer in ("n", "no", "否", ""):
            monkeypatch.setattr("builtins.input", lambda _p="", a=answer: a)
            assert bootstrap.ask_continue("继续？") is False

    def test_assume_yes_skips_prompt(self, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda _p="": (_ for _ in ()).throw(AssertionError("不应询问")))
        assert bootstrap.ask_continue("继续？", assume_yes=True) is True

    def test_eof_rejects(self, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda _p="": (_ for _ in ()).throw(EOFError()))
        assert bootstrap.ask_continue("继续？") is False

    def test_invalid_answer_then_valid(self, monkeypatch):
        answers = iter(["maybe", "y"])
        monkeypatch.setattr("builtins.input", lambda _p="": next(answers))
        assert bootstrap.ask_continue("继续？") is True


class TestVersionGate:
    def test_version_at_least(self):
        assert bootstrap._version_at_least("1.0.0", (1, 0)) is True
        assert bootstrap._version_at_least("1.2.3", (1, 0)) is True
        assert bootstrap._version_at_least("0.25.2", (1, 0)) is False
        assert bootstrap._version_at_least("1.0", (1, 0, 0)) is True  # 缺位补零
        assert bootstrap._version_at_least("1.0.2", (1, 0, 2)) is True
        assert bootstrap._version_at_least("1.0.1", (1, 0, 2)) is False  # 逐段比较

    def test_imports_ok_requires_flet_1(self, tmp_path, monkeypatch):
        """0.x 旧版 flet 能导入但版本不达标——应用基于 1.0 API，必须门禁拦截。"""
        outputs = iter(["OK 0.25.2", "OK 1.0.0"])

        def fake_run(*args, **kwargs):
            out = next(outputs)
            done = type("R", (), {"stdout": out, "returncode": 0})
            return done

        monkeypatch.setattr(bootstrap.subprocess, "run", fake_run)
        ok, message = bootstrap.imports_ok("py")
        assert ok is False and "1.0" in message
        ok, message = bootstrap.imports_ok("py")
        assert ok is True and "1.0.0" in message


class TestMainPaths:
    """main() 三条决策路径：快路径启动 / 拒绝安装 / 同意后安装启动。"""

    @staticmethod
    def _fake_root(tmp_path: Path) -> None:
        (tmp_path / "main.py").write_text("print('app')", encoding="utf-8")
        bootstrap.ROOT = tmp_path
        bootstrap.VENV = tmp_path / ".venv"

    def test_fast_path_launches_healthy_venv(self, tmp_path, monkeypatch):
        self._fake_root(tmp_path)
        venv_py = bootstrap.venv_python()  # 平台正确路径（Win: Scripts，*nix: bin）
        venv_py.parent.mkdir(parents=True, exist_ok=True)
        venv_py.write_text("", encoding="utf-8")  # 让 is_file() 守卫通过
        monkeypatch.setattr(bootstrap, "imports_ok", lambda py: (True, ""))
        monkeypatch.setattr(
            bootstrap, "check_dependencies", lambda py: (True, {"python": "3.13.11"})
        )
        launched = []
        monkeypatch.setattr(
            bootstrap, "launch", lambda runtime, extra=None: launched.append((runtime, extra)) or 0
        )
        assert bootstrap.main([]) == 0
        assert len(launched) == 1 and launched[0][1] == []

    def test_declined_prompt_returns_1(self, tmp_path, monkeypatch):
        self._fake_root(tmp_path)
        monkeypatch.setattr(bootstrap, "venv_python", lambda: tmp_path / "absent" / "python.exe")
        monkeypatch.setattr(bootstrap, "ask_continue", lambda q, assume_yes=False: False)
        assert bootstrap.main() == 1

    def test_accepted_prompt_installs_and_launches(self, tmp_path, monkeypatch):
        self._fake_root(tmp_path)
        monkeypatch.setattr(bootstrap, "venv_python", lambda: tmp_path / "absent" / "python.exe")
        monkeypatch.setattr(bootstrap, "ask_continue", lambda q, assume_yes=False: True)
        monkeypatch.setattr(
            bootstrap,
            "search_usable_pythons",
            lambda: [(tmp_path / "fakepython.exe", {"version": [3, 13, 0]})],
        )
        calls: list = []
        monkeypatch.setattr(
            bootstrap, "prepare_with", lambda base: calls.append("prepare") or tmp_path / "venvpython.exe"
        )
        monkeypatch.setattr(
            bootstrap, "launch", lambda runtime, extra=None: calls.append(("launch", extra)) or 0
        )
        assert bootstrap.main(["--narrow"]) == 0
        assert calls == ["prepare", ("launch", ["--narrow"])]  # 附加参数透传给 main.py
