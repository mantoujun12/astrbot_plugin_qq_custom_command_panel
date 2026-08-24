"""轻量级国际化 (i18n) 支持

零第三方依赖: 直接加载 locales 目录下 JSON 文件,
提供模块级单例 `translator` + 便捷函数 `t`。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from astrbot.api import logger

SUPPORTED_LANGUAGES: tuple[str, ...] = ("zh-CN", "en-US")
DEFAULT_LANGUAGE: str = "zh-CN"
LOG_TAG: str = "[qq-command-panel]"

_instance: Translator | None = None


class Translator:
    """JSON 翻译加载器 + 带 zh-CN 回退的 key 查找"""

    def __init__(
        self,
        locales_dir: Path | str,
        language: str = DEFAULT_LANGUAGE,
    ) -> None:
        self.locales_dir = Path(locales_dir)
        self._fallback_lang = DEFAULT_LANGUAGE
        self._active: dict[str, str] = {}
        self._fallback: dict[str, str] = {}
        self._language: str = DEFAULT_LANGUAGE
        # fallback 字典先加载好, 保证后续 set_language 失败时仍可用
        self._fallback = self._load_dict(self._fallback_lang)
        self.set_language(language)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def language(self) -> str:
        """当前生效的语言"""
        return self._language

    def set_language(self, language: str | None) -> None:
        """切换语言, 未识别时回退到 DEFAULT_LANGUAGE 并记录 warning"""
        target = (language or DEFAULT_LANGUAGE).strip()
        if target not in SUPPORTED_LANGUAGES:
            logger.warning(
                f"{LOG_TAG} unsupported language={target!r}, fallback to {DEFAULT_LANGUAGE}"
            )
            target = DEFAULT_LANGUAGE
        if target == self._fallback_lang:
            self._active = self._fallback
        else:
            loaded = self._load_dict(target)
            if not loaded:
                logger.warning(
                    f"{LOG_TAG} no translations loaded for {target}, fallback to {DEFAULT_LANGUAGE}"
                )
                self._active = self._fallback
                target = DEFAULT_LANGUAGE
            else:
                self._active = loaded
        self._language = target

    def t(self, key: str, **kwargs: Any) -> str:
        """按 key 查找翻译, 未找到时回退到 zh-CN, 再未找到则原样返回 key"""
        template = self._active.get(key)
        if template is None:
            template = self._fallback.get(key)
        if template is None:
            return key
        if not kwargs:
            return template
        try:
            return template.format(**kwargs)
        except Exception as exc:
            logger.debug(f"{LOG_TAG} i18n format failed key={key} kwargs={kwargs}: {exc}")
            return template

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_dict(self, language: str) -> dict[str, str]:
        """加载一个语言的 JSON 文件, 任何失败都返回 {} 并记录 warning"""
        path = self.locales_dir / f"{language}.json"
        if not path.exists():
            logger.warning(f"{LOG_TAG} locale file not found: {path}")
            return {}
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            logger.warning(f"{LOG_TAG} load locale {path} failed: {exc}")
            return {}
        if not isinstance(data, dict):
            logger.warning(f"{LOG_TAG} locale {path} is not a JSON object, ignored")
            return {}
        cleaned: dict[str, str] = {}
        for k, v in data.items():
            if isinstance(v, str):
                cleaned[str(k)] = v
        return cleaned


# ----------------------------------------------------------------------
# 模块级便捷 API (单例模式)
# ----------------------------------------------------------------------


def initialize(
    locales_dir: Path | str,
    language: str = DEFAULT_LANGUAGE,
) -> Translator:
    """初始化(或重置)模块级单例, 返回新实例"""
    global _instance
    _instance = Translator(locales_dir, language)
    return _instance


def get_instance() -> Translator:
    """获取已初始化的单例, 未初始化时先创建一个默认 zh-CN 实例

    兜底使用, 避免尚未初始化时其他模块直接调用 `t` 抛异常
    """
    global _instance
    if _instance is None:
        default_dir = Path(__file__).resolve().parent.parent / "locales"
        _instance = Translator(default_dir, DEFAULT_LANGUAGE)
    return _instance


def t(key: str, **kwargs: Any) -> str:
    """便捷翻译函数, 等价于 get_instance().t(key, **kwargs)"""
    return get_instance().t(key, **kwargs)


__all__ = [
    "DEFAULT_LANGUAGE",
    "LOG_TAG",
    "SUPPORTED_LANGUAGES",
    "Translator",
    "get_instance",
    "initialize",
    "t",
]
