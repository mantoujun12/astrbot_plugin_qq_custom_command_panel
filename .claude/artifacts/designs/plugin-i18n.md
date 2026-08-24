# Plugin i18n (Internationalization) Support Spec

> Status: ALIGNED
> Author: mantoujun12
> Last updated: 2026-08-24

## Background

The astrbot_plugin_qq_custom_command_panel plugin currently ships with all user-facing strings (logger output, command replies, schema hints) hardcoded in Simplified Chinese. Non-Chinese speaking AstrBot users and QQ Official Bot operators cannot read the debug-command responses or diagnose sync failures from logs. This feature adds a lightweight, zero-dependency i18n layer so the plugin can ship bilingual (zh-CN + en-US) output, with the language configurable in the AstrBot WebUI via the existing `_conf_schema.json` mechanism.

## In scope
- Add a new `core/i18n.py` module providing a `Translator` class with JSON-based translation loading, runtime language switching, a `t(key, **kwargs)` callable, and zh-CN fallback behavior when a key is missing in the active language.
- Ship two translation resource files under `locales/`: `zh-CN.json` and `en-US.json`, covering all current hardcoded user-facing messages (logger prefix content, debug-command plain_result responses, PanelSyncer/QQClient/StateStore error strings, etc.).
- Extend `_conf_schema.json` with a `language` dropdown item (`zh-CN` / `en-US`, default `zh-CN`).
- Wire the chosen language from `AstrBotConfig` into `PanelSyncer`, which owns the `Translator` instance, and expose the translator through main.py so all modules share the same instance.
- Replace the existing hardcoded Chinese strings in `main.py`, `core/config.py`, `core/panel_syncer.py`, `core/qq_client.py`, `core/state.py`, and `core/command_collector.py` with `translator.t(...)` calls, preserving positional/keyword interpolation (`{foo}` style tokens).
- Preserve the fixed logger tag `[qq-command-panel]` literally; only the human-readable message portion is translated.
- Backward compatibility: when `language` is unset, the plugin defaults to `zh-CN` (identical behavior to pre-i18n versions).

## Out of scope
- Translating user-provided `selected_commands` entries (name + desc); those are authored by the user and written verbatim to the QQ panel.
- Dynamic hot-reload of language without a re-sync / reload step of the plugin or a `/qq_panel_resync`.
- Per-platform, per-user, or per-guild language overrides (single global language).
- Introducing third-party i18n libraries such as `gettext`, `Babel`, `Flask-Babel`, `python-i18n`; plugin `requirements.txt` is not changed.
- Adding languages beyond zh-CN and en-US in this delivery.
- Translating raw QQ API error payloads returned by `api.bot.qq.com`; those remain as-is.
- Translating the AstrBot-side WebUI schema description/hint text fields (AstrBot renders those to admins; translations for those are explicitly NOT applied to `_conf_schema.json` description/hint strings — those stay as single-language Chinese admin-facing copy per the AstrBot schema rendering contract). Schema `description`/`hint` strings remain in Chinese; only runtime plugin logs and debug-command replies are translated.

## Assumptions
- `locales/*.json` ship inside the plugin package directory, so we load them relative to `core/i18n.py` via `__file__` → `Path(...).resolve().parent.parent / "locales"`.
- Translation keys use flat dotted strings (`log.sync_started`, `cmd.resync_success`) to avoid nesting complexity.
- Interpolation uses native Python `str.format(**kwargs)` with brace tokens; no pluralization or gender rules are needed for the current message set.
- Logger calls are formatted via a small helper that combines the literal `[qq-command-panel]` prefix with the translated body, so callers keep `logger.info(f"{i18n.log_t(...)}")` or a thin wrapper. To avoid wrapping the astrbot logger API, we instead always use explicit concatenation: `logger.info(f"[qq-command-panel] {translator.t('key', ...)}")` and translate only the body. The existing code already includes the `[qq-command-panel]` prefix verbatim in f-strings, so we preserve that literal prefix as-is and only translate the trailing message.

## Solution
Minimal zero-dependency i18n layer:

1. `core/i18n.py` defines `SUPPORTED_LANGUAGES = ("zh-CN", "en-US")`, `DEFAULT_LANGUAGE = "zh-CN"`, and a `Translator` class:
   - `__init__(self, locales_dir: Path, language: str = DEFAULT_LANGUAGE)` loads `<lang>.json` plus fallback zh-CN.json.
   - `set_language(self, language: str) -> None` validates against SUPPORTED_LANGUAGES and falls back to DEFAULT_LANGUAGE when unknown.
   - `t(self, key: str, **kwargs) -> str` looks up in active dict first, then fallback zh-CN dict, and finally returns the key itself when totally missing (so we never raise on missing translations).
   - Private helper `_load_dict(self, language: str) -> dict[str, str]` does the JSON load with UTF-8 and returns `{}` on failure.
2. `locales/zh-CN.json` contains the current Chinese strings as the source of truth, each mapped to a stable dotted key.
3. `locales/en-US.json` contains the equivalent English strings with matching keys and identical `{token}` placeholders.
4. In `PanelSyncer.__init__`, construct a `Translator` using `<plugin_root>/locales` and the language from `config.get("language", DEFAULT_LANGUAGE)`; expose it via a public attribute `syncer.translator` so callers in main.py can reference it.
5. In `main.py` debug handlers, when replying with `event.plain_result(...)`, call `self._syncer.translator.t(...)` (after the `not self._syncer` early-out which still yields a hardcoded-safe translated message).
6. `_conf_schema.json` appends `"language"` field of `type: "string"`, `options: ["zh-CN", "en-US"]`, `default: "zh-CN"`.

## Edge cases & risks

| Category | Notes |
|---|---|
| Boundary conditions | Missing `locales/` dir or JSON file → `_load_dict` returns `{}`, lookup falls through to key-as-value. Config `language` missing or invalid → `set_language` coerces to `zh-CN`. |
| Failure modes | Malformed JSON → logged warning + empty dict; never abort plugin startup. Interpolation token mismatch → `str.format`-style `KeyError` propagates; caught by surrounding try/except in sync paths. |
| Risks | Incomplete `en-US.json` coverage → users see dotted keys for those strings; mitigated by always keeping zh-CN as fallback. Logger prefix `[qq-command-panel]` accidentally translated → avoided by keeping it literal in the f-string outside `t()`. |
| Mitigation | All strings extracted first into `zh-CN.json` before code changes; the code change pass never rewrites a string inline — it replaces with a `t(key)` call whose key maps to both JSONs. Ruff check/format run before verification. |

## Acceptance criteria
- AC-1 With `language` unset in config, all logger messages and `/qq_panel_*` command plain_result replies match the pre-change Chinese text (byte-for-byte where no interpolation, token-equal where interpolation).
- AC-2 With `"language": "en-US"` set, no Chinese hardcoded text appears in logger output nor in `/qq_panel_resync`, `/qq_panel_fetch`, `/qq_panel_purge`, `/qq_panel_list`, `/qq_panel_platforms`, `/qq_panel_reload_check` command replies.
- AC-3 Setting an unsupported value like `"fr"` for `language` behaves identically to `zh-CN` (no exceptions, no "key" fallback strings in normal paths).
- AC-4 Deleting one key from `en-US.json` still yields the zh-CN value at runtime (no KeyError, no bare dotted key output to users/logs).
- AC-5 `ruff check . --fix` exits 0 and `ruff format --check .` exits 0 after changes.
- AC-6 Both `locales/zh-CN.json` and `locales/en-US.json` are valid JSON with UTF-8 encoding and every key referenced in code exists in both files.

## Open questions
None.

## Core entities (ontology)

| Entity | Type | Key fields | Relationship |
|---|---|---|---|
| Translator | Service class | language, fallback_lang, locales_dir | Instantiated once by PanelSyncer; referenced by main.py command handlers, PanelSyncer, qq_client, state, command_collector |
| Translation map | Value object (JSON dict) | flat key → formatted string | One per SUPPORTED_LANGUAGES; loaded from `locales/<lang>.json` |
| Language setting | Config scalar | "zh-CN" \| "en-US" \| unset | Declared in `_conf_schema.json`, read via `config.get("language", ...)` |

## Interview metadata

- Mode: --spec-only (user asked not to ask questions; self-aligned)
- Waves: 0
- Final ambiguity: ~18% (bounded by explicit scope-cut decisions written into Out of scope)
- Status: PASSED

### Clarity breakdown

| Dimension | Score | Weight | Weighted |
|---|---|---|---|
| Goal | 0.9 | 0.40 | 0.36 |
| Scope | 0.8 | 0.25 | 0.20 |
| AC | 0.9 | 0.25 | 0.225 |
| Context | 0.95 | 0.10 | 0.095 |
| Ambiguity |  |  | 12.0% |
