"""core.paths.resolve_plugin_data_dir 的单元测试 (无需真实 AstrBot)

覆盖解析优先级: StarTools → context.get_data_dir → astrbot_path → 相对兜底,
并确认最终目录始终遵守 `data/plugin_data/<plugin_name>` 约定。
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import astrbot.api.star as star_api
import pytest

from core.paths import PLUGIN_NAME, resolve_plugin_data_dir

RELATIVE_FALLBACK = Path("data") / "plugin_data" / PLUGIN_NAME


class FakeContext:
    """只暴露 get_data_dir(plugin_name) 的最小 Context 替身"""

    def __init__(self, result: Path | None = None, error: Exception | None = None) -> None:
        self.calls: list[str] = []
        self._result = result
        self._error = error

    def get_data_dir(self, plugin_name: str) -> Path:
        self.calls.append(plugin_name)
        if self._error is not None:
            raise self._error
        assert self._result is not None
        return self._result


@pytest.fixture
def no_star_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    """强制 StarTools 不可用, 保证测试走到后续分支"""
    monkeypatch.delattr(star_api, "StarTools", raising=False)


@pytest.fixture
def no_astrbot_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """强制 astrbot_path 导入失败 (sys.modules 置 None 会让导入抛 ImportError)"""
    monkeypatch.setitem(sys.modules, "astrbot.core.utils.astrbot_path", None)


def _install_fake_astrbot_path(monkeypatch: pytest.MonkeyPatch, data_path: Path) -> None:
    """注入假的 astrbot.core.utils.astrbot_path 模块"""
    leaf = types.ModuleType("astrbot.core.utils.astrbot_path")
    leaf.get_astrbot_plugin_data_path = lambda: str(data_path)  # type: ignore[attr-defined]
    pkg = types.ModuleType("astrbot.core.utils")
    pkg.__path__ = []  # type: ignore[attr-defined]
    pkg.astrbot_path = leaf  # type: ignore[attr-defined]
    core = sys.modules.get("astrbot.core")
    if core is not None:
        monkeypatch.setattr(core, "utils", pkg, raising=False)
    monkeypatch.setitem(sys.modules, "astrbot.core.utils", pkg)
    monkeypatch.setitem(sys.modules, "astrbot.core.utils.astrbot_path", leaf)


def test_uses_star_tools_when_available(
    monkeypatch: pytest.MonkeyPatch,
    no_astrbot_path: None,
    tmp_path: pytest.Path,
) -> None:
    recorded: list[str | None] = []

    class FakeStarTools:
        @classmethod
        def get_data_dir(cls, plugin_name: str | None = None) -> Path:
            recorded.append(plugin_name)
            return tmp_path / "from_star_tools"

    monkeypatch.setattr(star_api, "StarTools", FakeStarTools, raising=False)

    assert resolve_plugin_data_dir(None) == tmp_path / "from_star_tools"
    assert recorded == [PLUGIN_NAME]


def test_uses_context_get_data_dir_with_plugin_name(
    no_star_tools: None,
    no_astrbot_path: None,
    tmp_path: pytest.Path,
) -> None:
    context = FakeContext(result=tmp_path)
    assert resolve_plugin_data_dir(context) == tmp_path
    # 关键: 必须以 plugin_name 作为参数调用, 而不是无参调用
    assert context.calls == [PLUGIN_NAME]


def test_passes_custom_plugin_name_to_context(
    no_star_tools: None,
    no_astrbot_path: None,
    tmp_path: pytest.Path,
) -> None:
    context = FakeContext(result=tmp_path)
    assert resolve_plugin_data_dir(context, "another_plugin") == tmp_path
    assert context.calls == ["another_plugin"]


def test_uses_astrbot_plugin_data_path(
    no_star_tools: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pytest.Path,
) -> None:
    _install_fake_astrbot_path(monkeypatch, tmp_path)
    assert resolve_plugin_data_dir(None) == tmp_path / PLUGIN_NAME


def test_star_tools_failure_falls_through_to_context(
    monkeypatch: pytest.MonkeyPatch,
    no_astrbot_path: None,
    tmp_path: pytest.Path,
) -> None:
    class BoomStarTools:
        @classmethod
        def get_data_dir(cls, plugin_name: str | None = None) -> Path:
            raise RuntimeError("boom")

    monkeypatch.setattr(star_api, "StarTools", BoomStarTools, raising=False)

    context = FakeContext(result=tmp_path)
    assert resolve_plugin_data_dir(context) == tmp_path
    assert context.calls == [PLUGIN_NAME]


def test_context_failure_falls_through_to_relative(
    no_star_tools: None,
    no_astrbot_path: None,
) -> None:
    context = FakeContext(error=RuntimeError("boom"))
    assert resolve_plugin_data_dir(context) == RELATIVE_FALLBACK


def test_relative_fallback_when_no_api_available(
    no_star_tools: None,
    no_astrbot_path: None,
) -> None:
    assert resolve_plugin_data_dir(None) == RELATIVE_FALLBACK


def test_relative_fallback_uses_custom_plugin_name(
    no_star_tools: None,
    no_astrbot_path: None,
) -> None:
    assert resolve_plugin_data_dir(None, "another_plugin") == (
        Path("data") / "plugin_data" / "another_plugin"
    )


def test_relative_fallback_never_targets_bare_data_dir(
    no_star_tools: None,
    no_astrbot_path: None,
) -> None:
    """回归保护: 兜底目录必须包含 plugin_data/<plugin_name>, 不能是裸 data/"""
    resolved = resolve_plugin_data_dir(None)
    assert resolved != Path("data")
    assert resolved.parts[-3:] == ("data", "plugin_data", PLUGIN_NAME)
