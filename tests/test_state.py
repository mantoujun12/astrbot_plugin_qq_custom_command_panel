"""core.state.PanelStateStore 的单元测试 (真实文件 IO, 用 tmp_path)"""

from __future__ import annotations

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


def test_load_missing_file_returns_empty(tmp_path: pytest.Path) -> None:
    assert PanelStateStore(tmp_path).load() == {}


def test_load_non_dict_yaml_returns_empty(tmp_path: pytest.Path) -> None:
    state_file = tmp_path / STATE_FILENAME
    state_file.write_text("- just\n- a\n- list\n", encoding="utf-8")
    assert PanelStateStore(tmp_path).load() == {}


def test_load_normalizes_non_string_values(tmp_path: pytest.Path) -> None:
    state_file = tmp_path / STATE_FILENAME
    state_file.write_text(
        "123:\n  456: 789\n",
        encoding="utf-8",
    )
    store = PanelStateStore(tmp_path)
    # 键/值都被规范化为字符串, 空值被过滤
    assert store.load() == {"123": {"456": "789"}}


def test_load_falsy_values_filtered(tmp_path: pytest.Path) -> None:
    state_file = tmp_path / STATE_FILENAME
    state_file.write_text(
        "pf:\n  c2c: p1\n  group:\n",
        encoding="utf-8",
    )
    store = PanelStateStore(tmp_path)
    assert store.load() == {"pf": {"c2c": "p1"}}


def test_load_corrupt_file_returns_empty(tmp_path: pytest.Path) -> None:
    state_file = tmp_path / STATE_FILENAME
    state_file.write_text(
        "{not valid yaml: [[",
        encoding="utf-8",
    )
    assert PanelStateStore(tmp_path).load() == {}


def test_save_overwrites_previous_state(tmp_path: pytest.Path) -> None:
    store = PanelStateStore(tmp_path)
    store.save({"pf": {"c2c": "old"}})
    store.save({"pf": {"group": "new"}})
    assert store.load() == {"pf": {"group": "new"}}


def test_clear_removes_state_file(tmp_path: pytest.Path) -> None:
    store = PanelStateStore(tmp_path)
    store.save({"pf": {"c2c": "p1"}})
    assert store.state_file.exists()
    store.clear()
    assert not store.state_file.exists()
    assert store.load() == {}


def test_clear_missing_file_is_noop(tmp_path: pytest.Path) -> None:
    store = PanelStateStore(tmp_path)
    store.clear()  # 不应抛异常
    assert store.load() == {}


def test_save_empty_state_roundtrip(tmp_path: pytest.Path) -> None:
    store = PanelStateStore(tmp_path)
    store.save({})
    assert store.load() == {}
