"""core.paths.resolve_plugin_data_dir 的单元测试 (无需真实 AstrBot)

覆盖解析优先级: StarTools → context.get_data_dir → context.data_dir →
AstrBot 路径工具 → 相对兜底, 并确认最终目录始终遵守
`data/plugin_data/<plugin_name>` 约定。
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import astrbot.api.star as star_api
import pytest

from core.paths import PLUGIN_NAME, resolve_plugin_data_dir

RELATIVE_FALLBACK = Path("data") / "plugin_data" / PLUGIN_NAME


@pytest.fixture
def no_star_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    """强制 StarTools 不可用, 保证测试走到后续分支"""
    monkeypatch.delattr(star_api, "StarTools", raising=False)
    monkeypatch.setitem(sys.modules, "astrbot.core.star.star_tools", None)


@pytest.fixture
def no_astrbot_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """强制 astrbot_path 模块不可用 (sys.modules 置 None 会让导入抛 ImportError)"""
    monkeypatch.setitem(sys.modules, "astrbot.core.utils.astrbot_path", None)


def _install_fake_astrbot_path(
    monkeypatch: pytest.MonkeyPatch,
    *,
    plugin_data_path: Path | None = None,
    data_path: Path | None = None,
) -> None:
    """注入假的 astrbot.core.utils.astrbot_path 模块 (只暴露指定辅助函数)"""
    leaf = types.ModuleType("astrbot.core.utils.astrbot_path")
    if plugin_data_path is not None:
        leaf.get_astrbot_plugin_data_path = lambda: str(plugin_data_path)  # type: ignore[attr-defined]
    if data_path is not None:
        leaf.get_astrbot_data_path = lambda: str(data_path)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "astrbot.core.utils.astrbot_path", leaf)


# ---------------------------------------------------------------------------
# 来源 1: StarTools.get_data_dir (官方 API)
# ---------------------------------------------------------------------------


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

    calls: list[str] = []

    def fake_get_data_dir(plugin_name: str) -> Path:
        calls.append(plugin_name)
        return tmp_path

    context = types.SimpleNamespace(get_data_dir=fake_get_data_dir)
    assert resolve_plugin_data_dir(context) == tmp_path
    assert calls == [PLUGIN_NAME]


# ---------------------------------------------------------------------------
# 来源 2: context.get_data_dir (必须显式传 plugin_name)
# ---------------------------------------------------------------------------


def test_uses_context_get_data_dir_with_plugin_name(
    no_star_tools: None,
    no_astrbot_path: None,
    tmp_path: pytest.Path,
) -> None:
    calls: list[str] = []

    def get_data_dir(plugin_name: str) -> Path:
        calls.append(plugin_name)
        return tmp_path

    context = types.SimpleNamespace(get_data_dir=get_data_dir)
    assert resolve_plugin_data_dir(context) == tmp_path
    # 关键: 必须以 plugin_name 作为参数调用, 而不是无参调用
    assert calls == [PLUGIN_NAME]


def test_passes_custom_plugin_name_to_context(
    no_star_tools: None,
    no_astrbot_path: None,
    tmp_path: pytest.Path,
) -> None:
    calls: list[str] = []

    def get_data_dir(plugin_name: str) -> Path:
        calls.append(plugin_name)
        return tmp_path

    context = types.SimpleNamespace(get_data_dir=get_data_dir)
    assert resolve_plugin_data_dir(context, "another_plugin") == tmp_path
    assert calls == ["another_plugin"]


# ---------------------------------------------------------------------------
# 来源 3: context.data_dir (数据根)
# ---------------------------------------------------------------------------


def test_uses_context_data_dir_attribute(
    no_star_tools: None,
    no_astrbot_path: None,
    tmp_path: pytest.Path,
) -> None:
    """context.data_dir 被视为数据根, 按约定拼出 plugin_data/<plugin_name>"""
    context = types.SimpleNamespace(data_dir=tmp_path)
    assert resolve_plugin_data_dir(context) == tmp_path / "plugin_data" / PLUGIN_NAME


def test_uses_context_data_dir_callable(
    no_star_tools: None,
    no_astrbot_path: None,
    tmp_path: pytest.Path,
) -> None:
    context = types.SimpleNamespace(data_dir=lambda: tmp_path)
    assert resolve_plugin_data_dir(context) == tmp_path / "plugin_data" / PLUGIN_NAME


def test_context_get_data_dir_failure_falls_to_context_data_dir(
    no_star_tools: None,
    no_astrbot_path: None,
    tmp_path: pytest.Path,
) -> None:
    def broken_get_data_dir(plugin_name: str) -> Path:
        raise RuntimeError("boom")

    context = types.SimpleNamespace(get_data_dir=broken_get_data_dir, data_dir=tmp_path)
    assert resolve_plugin_data_dir(context) == tmp_path / "plugin_data" / PLUGIN_NAME


# ---------------------------------------------------------------------------
# 来源 4/5: AstrBot 官方路径工具
# ---------------------------------------------------------------------------


def test_uses_astrbot_plugin_data_path(
    no_star_tools: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pytest.Path,
) -> None:
    _install_fake_astrbot_path(monkeypatch, plugin_data_path=tmp_path)
    assert resolve_plugin_data_dir(None) == tmp_path / PLUGIN_NAME


def test_uses_astrbot_data_path_when_plugin_helper_missing(
    no_star_tools: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pytest.Path,
) -> None:
    """插件路径工具缺失时, 用数据根工具兜底 (仍落在 AstrBot 配置的数据根内)"""
    _install_fake_astrbot_path(monkeypatch, data_path=tmp_path)
    assert resolve_plugin_data_dir(None) == tmp_path / "plugin_data" / PLUGIN_NAME


# ---------------------------------------------------------------------------
# 最后兜底: 相对 data/plugin_data/<plugin_name>
# ---------------------------------------------------------------------------


def test_context_failure_falls_through_to_relative(
    no_star_tools: None,
    no_astrbot_path: None,
) -> None:
    def broken_get_data_dir(plugin_name: str) -> Path:
        raise RuntimeError("boom")

    context = types.SimpleNamespace(get_data_dir=broken_get_data_dir)
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
