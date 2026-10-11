"""core.i18n.Translator 的单元测试"""

from __future__ import annotations

import pytest

from core.i18n import (
    DEFAULT_LANGUAGE,
    LOG_TAG,
    SUPPORTED_LANGUAGES,
    Translator,
)


def make_translator(language: str = DEFAULT_LANGUAGE) -> Translator:
    return Translator("core/i18n", language)


def test_translator_loads_fallback_language() -> None:
    tr = make_translator()
    assert tr.language == DEFAULT_LANGUAGE
    assert tr.t("log.no_scene_enabled") == "未启用任何场景，跳过同步"


def test_translator_formats_kwargs() -> None:
    tr = make_translator()
    result = tr.t("log.update_panel", scope="c2c", panel_id="p1")
    assert result == "更新面板 scope=c2c panel_id=p1"


def test_translator_falls_back_for_missing_active_key() -> None:
    """en-US 缺失的 key 回退到 zh-CN"""
    tr = make_translator("en-US")
    # 用一个 en-US 可能没有的 key — 直接探测 zh-CN 全量 vs en-US 差异不现实,
    # 改为直接测回退机制: 强制清空 active 字典
    tr._active = {}
    assert tr.t("log.no_scene_enabled") == "未启用任何场景，跳过同步"


def test_translator_returns_key_when_not_found() -> None:
    tr = make_translator()
    assert tr.t("nonexistent.key.xyz") == "nonexistent.key.xyz"


def test_translator_switch_language() -> None:
    tr = make_translator("zh-CN")
    tr.set_language("en-US")
    assert tr.language == "en-US"

    tr.set_language("zh-CN")
    assert tr.language == "zh-CN"


def test_translator_unsupported_language_falls_back() -> None:
    tr = make_translator("zh-CN")
    tr.set_language("xx-XX")
    assert tr.language == DEFAULT_LANGUAGE


def test_translator_non_string_language_falls_back() -> None:
    tr = make_translator("zh-CN")
    tr.set_language(None)  # type: ignore[arg-type]
    tr.set_language(123)  # type: ignore[arg-type]
    assert tr.language == DEFAULT_LANGUAGE


def test_translator_format_failure_returns_template() -> None:
    """format kwargs 与模板占位不匹配时, 返回原模板而非抛异常"""
    tr = make_translator()
    result = tr.t("log.update_panel", wrong_kwarg="x")
    assert "更新面板" in result


def test_log_tag_constant() -> None:
    assert LOG_TAG == "[qq-command-panel]"


def test_supported_languages() -> None:
    assert set(SUPPORTED_LANGUAGES) == {"zh-CN", "en-US"}


def test_translator_missing_locale_dir_returns_empty(tmp_path: pytest.Path) -> None:
    tr = Translator(tmp_path / "no_such_dir", DEFAULT_LANGUAGE)
    assert tr.t("log.no_scene_enabled") == "log.no_scene_enabled"
