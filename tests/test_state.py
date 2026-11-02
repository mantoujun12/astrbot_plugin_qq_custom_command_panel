"""core.state.PanelStateStore 的单元测试（真实文件 IO，用 tmp_path）"""

from __future__ import annotations

import logging

import pytest

from core.state import STATE_FILENAME, PanelStateStore


def test_save_and_load_roundtrip(tmp_path: pytest.Path) -> None:
    store = PanelStateStore(tmp_path)
    state = {
        "pf1": {"c2c": "panel_a", "group": "panel_b"},
        "pf2": {"channel": "panel_c"},
    }
    store.save(state)
    assert store.load() == state


def test_state_file_created_in_data_dir(tmp_path: pytest.Path) -> None:
    store = PanelStateStore(tmp_path / "nested" / "data")
    store.save({"pf": {"c2c": "p1"}})
    assert (tmp_path / "nested" / "data" / STATE_FILENAME).exists()


@pytest.mark.parametrize(
    "raw",
    ["- just\n- a\n- list\n", "{not valid yaml: [["],
    ids=["non-dict", "corrupt"],
)
def test_load_invalid_document_returns_empty(tmp_path: pytest.Path, raw: str) -> None:
    (tmp_path / STATE_FILENAME).write_text(raw, encoding="utf-8")
    assert PanelStateStore(tmp_path).load() == {}


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("123:\n  456: 789\n", {"123": {"456": "789"}}),
        ("pf:\n  c2c: p1\n  group:\n", {"pf": {"c2c": "p1"}}),
        ("bad:\n  - nope\nok:\n  c2c: p1\n", {"ok": {"c2c": "p1"}}),
    ],
    ids=["non-string", "falsy", "non-dict-entry"],
)
def test_load_normalizes_entries(
    tmp_path: pytest.Path,
    raw: str,
    expected: dict[str, dict[str, str]],
) -> None:
    (tmp_path / STATE_FILENAME).write_text(raw, encoding="utf-8")
    assert PanelStateStore(tmp_path).load() == expected


def test_save_overwrites_previous_state(tmp_path: pytest.Path) -> None:
    store = PanelStateStore(tmp_path)
    store.save({"pf": {"c2c": "old"}})
    store.save({"pf": {"group": "new"}})
    assert store.load() == {"pf": {"group": "new"}}


def test_empty_lifecycle(tmp_path: pytest.Path) -> None:
    store = PanelStateStore(tmp_path)
    store.clear()  # 文件不存在时也不应抛异常
    assert store.load() == {}

    store.save({})
    assert store.load() == {}

    store.save({"pf": {"c2c": "p1"}})
    assert store.state_file.exists()
    store.clear()
    assert not store.state_file.exists()
    assert store.load() == {}


def test_save_failure_logs_and_cleans_temp_file(
    tmp_path: pytest.Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    (tmp_path / STATE_FILENAME).mkdir()
    store = PanelStateStore(tmp_path)

    with caplog.at_level(logging.ERROR):
        store.save({"pf": {"c2c": "p1"}})

    assert "保存面板状态失败" in caplog.text
    assert not store.state_file.with_suffix(".yaml.tmp").exists()


def test_clear_failure_is_logged(
    tmp_path: pytest.Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    (tmp_path / STATE_FILENAME).mkdir()
    store = PanelStateStore(tmp_path)

    with caplog.at_level(logging.WARNING):
        store.clear()

    assert "清理面板状态失败" in caplog.text
