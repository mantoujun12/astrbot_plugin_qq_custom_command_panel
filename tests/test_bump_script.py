"""scripts/bump_version.py 的离线测试。

覆盖版本号解析 / 递增、三处文件的读写（引号与换行风格保留、失败时不留下改了一半
的仓库）、``--check`` 校验与交互式流程。另外校验真实仓库当前的三处版本号确实一致
（release.yml 打 tag 的前置条件）。脚本不是包，用 importlib 按文件路径加载。
"""

from __future__ import annotations

import builtins
import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "bump_version.py"

METADATA = "metadata.yaml"
PATHS = "core/paths.py"
PACKAGE = "web/dashboard/package.json"

METADATA_TEMPLATE = """name: astrbot_plugin_qq_custom_command_panel
display_name: QQ 自定义指令面板
version: {version}
author: mantoujun12
"""

PATHS_TEMPLATE = '''"""插件持久化目录解析"""

from __future__ import annotations

PLUGIN_NAME = "astrbot_plugin_qq_custom_command_panel"
PLUGIN_VERSION = "{version}"

__all__ = ["PLUGIN_NAME", "PLUGIN_VERSION"]
'''

PACKAGE_TEMPLATE = """{{
  "name": "dashboard",
  "private": true,
  "version": "{version}",
  "type": "module"
}}
"""


def _load_bump_script():
    """按文件路径加载版本号脚本模块

    执行前先注册进 sys.modules：脚本里的 dataclass 要按 ``__module__`` 反查模块
    （importlib 文档里的标准加载姿势），缺了会在装饰器里报 NoneType。
    """
    spec = importlib.util.spec_from_file_location("bump_version", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        del sys.modules[spec.name]
        raise
    return module


bump = _load_bump_script()


def _target(relpath: str):
    """按相对路径取 VERSION_FILES 里的目标描述"""
    return next(target for target in bump.VERSION_FILES if target.relpath == relpath)


def _write(root: Path, relpath: str, text: str) -> Path:
    """按字节写文件，避免测试自身做换行转换"""
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))
    return path


def _read(root: Path, relpath: str) -> str:
    return (root / relpath).read_bytes().decode("utf-8")


class _FakeStdin:
    """假 stdin：测试只关心 isatty 的结果"""

    def __init__(self, tty: bool) -> None:
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty


def _set_stdin(monkeypatch: pytest.MonkeyPatch, *, tty: bool) -> None:
    monkeypatch.setattr(sys, "stdin", _FakeStdin(tty))


def _feed(monkeypatch: pytest.MonkeyPatch, *answers: str) -> None:
    """按顺序喂给 input()；用完后抛 EOFError，模拟输入结束"""
    queue = list(answers)

    def fake_input(prompt: str = "") -> str:
        if not queue:
            raise EOFError
        return queue.pop(0)

    monkeypatch.setattr(builtins, "input", fake_input)


@pytest.fixture
def plugin_root(tmp_path: Path) -> Path:
    """造一份最小插件目录：三个版本号文件 + 一个无关文件"""
    root = tmp_path / "plugin"
    _write(root, METADATA, METADATA_TEMPLATE.format(version="v0.5.0"))
    _write(root, PATHS, PATHS_TEMPLATE.format(version="v0.5.0"))
    _write(root, PACKAGE, PACKAGE_TEMPLATE.format(version="0.5.0"))
    _write(root, "main.py", "# 无关文件\n")
    return root


# ---------- 版本号解析 / 递增 ----------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("v0.5.0", (0, 5, 0)),
        ("0.5.0", (0, 5, 0)),
        ("  v1.2.30  ", (1, 2, 30)),
        ("v10.0.0", (10, 0, 0)),
    ],
)
def test_parse_version_accepts_bare_and_v_prefixed(
    text: str, expected: tuple[int, int, int]
) -> None:
    assert bump.parse_version(text) == expected


@pytest.mark.parametrize(
    "text",
    ["", "0.5", "0.5.0.1", "v0.5.0-beta.1", "v0.5.0+build", "1.2.3rc1", "0.x.0", "v"],
)
def test_parse_version_rejects_invalid(text: str) -> None:
    with pytest.raises(bump.BumpError):
        bump.parse_version(text)


def test_format_version() -> None:
    assert bump.format_version((0, 6, 0)) == "v0.6.0"
    assert bump.format_version((0, 6, 0), v_prefix=False) == "0.6.0"


@pytest.mark.parametrize(
    ("kind", "expected"),
    [("patch", (0, 5, 1)), ("minor", (0, 6, 0)), ("major", (1, 0, 0))],
)
def test_next_version(kind: str, expected: tuple[int, int, int]) -> None:
    assert bump.next_version((0, 5, 0), kind) == expected


def test_next_version_resets_lower_parts() -> None:
    assert bump.next_version((1, 2, 3), "patch") == (1, 2, 4)
    assert bump.next_version((1, 2, 3), "minor") == (1, 3, 0)
    assert bump.next_version((1, 2, 3), "major") == (2, 0, 0)


def test_next_version_rejects_unknown_kind() -> None:
    with pytest.raises(bump.BumpError):
        bump.next_version((0, 5, 0), "premajor")


# ---------- 真实仓库 ----------


def test_repo_version_files_are_consistent() -> None:
    """真实仓库三处版本号一致（release.yml 打 tag 的前置条件）"""
    from core.paths import PLUGIN_VERSION

    versions = bump.read_versions(REPO_ROOT)
    assert list(versions) == [target.relpath for target in bump.VERSION_FILES]
    assert versions[METADATA] == PLUGIN_VERSION
    assert versions[PATHS] == PLUGIN_VERSION
    assert versions[PACKAGE] == bump.format_version(
        bump.parse_version(PLUGIN_VERSION), v_prefix=False
    )


def test_check_passes_on_real_repo(capsys: pytest.CaptureFixture[str]) -> None:
    assert bump.main(["--root", str(REPO_ROOT), "--check"]) == 0
    assert "版本号校验通过" in capsys.readouterr().out


# ---------- 读写 ----------


def test_read_versions_returns_raw_writeup(plugin_root: Path) -> None:
    assert bump.read_versions(plugin_root) == {
        METADATA: "v0.5.0",
        PATHS: "v0.5.0",
        PACKAGE: "0.5.0",
    }


def test_read_version_reports_missing_file(plugin_root: Path) -> None:
    (plugin_root / PATHS).unlink()
    with pytest.raises(bump.BumpError, match="未找到文件"):
        bump.read_version(plugin_root, _target(PATHS))


def test_plan_changes_does_not_touch_files(plugin_root: Path) -> None:
    edits = bump.plan_changes((0, 6, 0), root=plugin_root)
    assert [(edit.relpath, edit.previous, edit.current) for edit in edits] == [
        (METADATA, "v0.5.0", "v0.6.0"),
        (PATHS, "v0.5.0", "v0.6.0"),
        (PACKAGE, "0.5.0", "0.6.0"),
    ]
    assert _read(plugin_root, METADATA) == METADATA_TEMPLATE.format(version="v0.5.0")


def test_apply_version_updates_all_files(plugin_root: Path) -> None:
    """三个文件同时更新，版本号之外的内容一个字节都不动"""
    edits = bump.apply_version((0, 6, 0), root=plugin_root)
    assert [edit.relpath for edit in edits] == [METADATA, PATHS, PACKAGE]
    assert _read(plugin_root, METADATA) == METADATA_TEMPLATE.format(version="v0.6.0")
    assert _read(plugin_root, PATHS) == PATHS_TEMPLATE.format(version="v0.6.0")
    assert _read(plugin_root, PACKAGE) == PACKAGE_TEMPLATE.format(version="0.6.0")
    assert (plugin_root / "main.py").read_text(encoding="utf-8") == "# 无关文件\n"


def test_apply_version_preserves_crlf(plugin_root: Path) -> None:
    """CRLF 文件写回后仍是 CRLF，不整篇变成 LF"""
    _write(plugin_root, METADATA, METADATA_TEMPLATE.format(version="v0.5.0").replace("\n", "\r\n"))
    bump.apply_version((0, 6, 0), root=plugin_root)
    written = _read(plugin_root, METADATA)
    assert written == METADATA_TEMPLATE.format(version="v0.6.0").replace("\n", "\r\n")
    assert b"\n" not in written.replace("\r\n", "").encode("utf-8")


@pytest.mark.parametrize("quote", ['"', "'"])
def test_apply_version_keeps_writeup_style(plugin_root: Path, quote: str) -> None:
    """引号、缩进、行尾注释原样保留，只换版本号本身"""
    _write(plugin_root, METADATA, f"name: demo\nversion:   {quote}v0.5.0{quote}  # 注释\n")
    bump.apply_version((0, 6, 0), root=plugin_root)
    assert _read(plugin_root, METADATA) == f"name: demo\nversion:   {quote}v0.6.0{quote}  # 注释\n"


def test_apply_version_normalizes_writeup(plugin_root: Path) -> None:
    """写回时统一成规范写法：metadata 带 v 前缀，npm 不带"""
    _write(plugin_root, METADATA, "name: demo\nversion: 0.5.0\n")
    _write(plugin_root, PACKAGE, PACKAGE_TEMPLATE.format(version="v0.5.0"))
    bump.apply_version((0, 6, 0), root=plugin_root)
    assert _read(plugin_root, METADATA).splitlines()[1] == "version: v0.6.0"
    assert json.loads(_read(plugin_root, PACKAGE))["version"] == "0.6.0"


def test_plan_changes_reports_missing_file(plugin_root: Path) -> None:
    (plugin_root / PACKAGE).unlink()
    with pytest.raises(bump.BumpError, match="未找到文件"):
        bump.plan_changes((0, 6, 0), root=plugin_root)


def test_plan_changes_reports_missing_version(plugin_root: Path) -> None:
    _write(plugin_root, PATHS, 'PLUGIN_NAME = "demo"\n')
    with pytest.raises(bump.BumpError, match="找不到版本号"):
        bump.plan_changes((0, 6, 0), root=plugin_root)


def test_plan_changes_reports_ambiguous_version(plugin_root: Path) -> None:
    """同一文件里有多处 version 时宁可报错，也不猜着改"""
    _write(
        plugin_root,
        PACKAGE,
        '{\n  "version": "0.5.0",\n  "engines": {\n    "version": "22"\n  }\n}\n',
    )
    with pytest.raises(bump.BumpError, match="匹配到 2 处"):
        bump.plan_changes((0, 6, 0), root=plugin_root)


def test_plan_changes_rejects_broken_json(plugin_root: Path) -> None:
    _write(plugin_root, PACKAGE, '{\n  "version": "0.5.0",\n}\n')
    with pytest.raises(bump.BumpError, match="不是合法 JSON"):
        bump.plan_changes((0, 6, 0), root=plugin_root)


def test_plan_changes_rejects_nested_only_json_version(plugin_root: Path) -> None:
    """只匹配到嵌套字段（顶层没有 version）时不能悄悄改错"""
    _write(
        plugin_root,
        PACKAGE,
        '{\n  "name": "dashboard",\n  "engines": {\n    "version": "22"\n  }\n}\n',
    )
    with pytest.raises(bump.BumpError, match="顶层 version"):
        bump.plan_changes((0, 6, 0), root=plugin_root)


def test_apply_version_failure_leaves_earlier_files_untouched(plugin_root: Path) -> None:
    """后一个文件坏掉时前面的文件也不能被改掉 —— 三处必须一起变"""
    _write(plugin_root, PACKAGE, '{\n  "name": "dashboard"\n}\n')
    with pytest.raises(bump.BumpError):
        bump.apply_version((0, 6, 0), root=plugin_root)
    assert _read(plugin_root, METADATA) == METADATA_TEMPLATE.format(version="v0.5.0")
    assert _read(plugin_root, PATHS) == PATHS_TEMPLATE.format(version="v0.5.0")


def test_apply_version_verifies_written_files(
    plugin_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """写盘没生效时必须报错，不能当成改成功了"""
    monkeypatch.setattr(bump, "_write_text", lambda path, text: None)
    with pytest.raises(bump.BumpError, match="写回后读到的版本号"):
        bump.apply_version((0, 6, 0), root=plugin_root)


# ---------- 命令行 ----------


def test_main_bumps_by_kind(plugin_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert bump.main(["--root", str(plugin_root), "-y", "minor"]) == 0
    out = capsys.readouterr().out
    assert "已更新版本：v0.5.0 → v0.6.0" in out
    assert "CHANGELOG.md" in out
    assert bump.read_versions(plugin_root) == {
        METADATA: "v0.6.0",
        PATHS: "v0.6.0",
        PACKAGE: "0.6.0",
    }


def test_main_bumps_to_explicit_version(plugin_root: Path) -> None:
    assert bump.main(["--root", str(plugin_root), "-y", "v1.0.0"]) == 0
    assert bump.read_versions(plugin_root)[METADATA] == "v1.0.0"


def test_main_dry_run_does_not_write(plugin_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert bump.main(["--root", str(plugin_root), "--dry-run", "patch"]) == 0
    out = capsys.readouterr().out
    assert "--dry-run" in out
    assert "v0.5.0 → v0.5.1" in out
    assert bump.read_versions(plugin_root)[METADATA] == "v0.5.0"


def test_main_check_passes(plugin_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert bump.main(["--root", str(plugin_root), "--check"]) == 0
    assert "版本号校验通过：v0.5.0" in capsys.readouterr().out


def test_main_check_reports_mismatch(plugin_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write(plugin_root, PACKAGE, PACKAGE_TEMPLATE.format(version="0.4.0"))
    assert bump.main(["--root", str(plugin_root), "--check"]) == 1
    err = capsys.readouterr().err
    assert PACKAGE in err
    assert "不一致" in err


def test_main_check_reports_sloppy_writeup(
    plugin_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """metadata 少写 v 前缀时 release.yml 会失败，这里要提前拦住"""
    _write(plugin_root, METADATA, "name: demo\nversion: 0.5.0\n")
    assert bump.main(["--root", str(plugin_root), "--check"]) == 1
    assert "应写成 v0.5.0" in capsys.readouterr().err


def test_main_check_reports_invalid_version(
    plugin_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(plugin_root, PATHS, 'PLUGIN_VERSION = "abc"\n')
    assert bump.main(["--root", str(plugin_root), "--check"]) == 1
    assert "不是合法版本号" in capsys.readouterr().err


def test_main_reports_unreadable_version_source(
    plugin_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(plugin_root, METADATA, "name: demo\nversion: abc\n")
    assert bump.main(["--root", str(plugin_root), "-y", "patch"]) == 1
    assert "错误：" in capsys.readouterr().err


def test_main_rejects_unknown_version_argument(
    plugin_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert bump.main(["--root", str(plugin_root), "-y", "0.6"]) == 1
    assert "无法识别的版本号或递增方式" in capsys.readouterr().err


def test_main_rejects_downgrade_without_force(
    plugin_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert bump.main(["--root", str(plugin_root), "-y", "0.4.0"]) == 1
    assert "--force" in capsys.readouterr().err
    assert bump.read_versions(plugin_root)[METADATA] == "v0.5.0"


def test_main_allows_downgrade_with_force(plugin_root: Path) -> None:
    assert bump.main(["--root", str(plugin_root), "-y", "--force", "0.4.0"]) == 0
    assert bump.read_versions(plugin_root)[METADATA] == "v0.4.0"


def test_main_is_a_noop_at_current_version(
    plugin_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert bump.main(["--root", str(plugin_root), "-y", "v0.5.0"]) == 0
    assert "无需修改" in capsys.readouterr().out


def test_main_repairs_drift_at_current_version(
    plugin_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """版本没变但有文件漂移时把它们对齐，并在 stderr 说明原因"""
    _write(plugin_root, PATHS, 'PLUGIN_VERSION = "v0.4.0"\n')
    assert bump.main(["--root", str(plugin_root), "-y", "v0.5.0"]) == 0
    assert "不一致" in capsys.readouterr().err
    assert bump.read_versions(plugin_root) == {
        METADATA: "v0.5.0",
        PATHS: "v0.5.0",
        PACKAGE: "0.5.0",
    }


def test_main_reports_plan_failure(plugin_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (plugin_root / PACKAGE).unlink()
    assert bump.main(["--root", str(plugin_root), "-y", "patch"]) == 1
    assert "未找到文件" in capsys.readouterr().err


def test_main_reports_unplannable_change(
    plugin_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """版本号读得出来但改不了（JSON 坏掉）时也要干净退出"""
    _write(plugin_root, PACKAGE, '{\n  "version": "0.5.0",\n}\n')
    assert bump.main(["--root", str(plugin_root), "-y", "patch"]) == 1
    assert "不是合法 JSON" in capsys.readouterr().err


def test_main_reports_write_failure(
    plugin_root: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """写盘没生效时报错退出，不打印「已更新版本」"""
    monkeypatch.setattr(bump, "_write_text", lambda path, text: None)
    assert bump.main(["--root", str(plugin_root), "-y", "patch"]) == 1
    captured = capsys.readouterr()
    assert "写回后读到的版本号" in captured.err
    assert "已更新版本" not in captured.out


def test_main_requires_version_when_not_interactive(
    plugin_root: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_stdin(monkeypatch, tty=False)
    assert bump.main(["--root", str(plugin_root)]) == 1
    assert "不是交互式终端" in capsys.readouterr().err
    assert bump.read_versions(plugin_root)[METADATA] == "v0.5.0"


# ---------- 交互式 ----------


def test_stdin_is_interactive_detects_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_stdin(monkeypatch, tty=True)
    assert bump._stdin_is_interactive() is True
    _set_stdin(monkeypatch, tty=False)
    assert bump._stdin_is_interactive() is False


def test_stdin_is_interactive_tolerates_odd_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    """stdin 没有 isatty 或已关闭时按非交互处理，不能让脚本崩在探测上"""
    monkeypatch.setattr(sys, "stdin", object())
    assert bump._stdin_is_interactive() is False

    class _ClosedStdin:
        def isatty(self) -> bool:
            raise ValueError("I/O operation on closed file")

    monkeypatch.setattr(sys, "stdin", _ClosedStdin())
    assert bump._stdin_is_interactive() is False


def test_main_interactive_selects_kind(
    plugin_root: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_stdin(monkeypatch, tty=True)
    _feed(monkeypatch, "2", "y")
    assert bump.main(["--root", str(plugin_root)]) == 0
    out = capsys.readouterr().out
    assert "当前版本：v0.5.0" in out
    assert "已更新版本：v0.5.0 → v0.6.0" in out
    assert bump.read_versions(plugin_root)[METADATA] == "v0.6.0"


def test_main_interactive_accepts_typed_version(
    plugin_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """菜单里直接敲版本号也行，省掉一次选择"""
    _set_stdin(monkeypatch, tty=True)
    _feed(monkeypatch, "2.0.0", "yes")
    assert bump.main(["--root", str(plugin_root)]) == 0
    assert bump.read_versions(plugin_root)[METADATA] == "v2.0.0"


def test_main_interactive_asks_for_custom_version(
    plugin_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_stdin(monkeypatch, tty=True)
    _feed(monkeypatch, "4", "0.7.5", "y")
    assert bump.main(["--root", str(plugin_root)]) == 0
    assert bump.read_versions(plugin_root)[METADATA] == "v0.7.5"


def test_main_interactive_retries_bad_input(
    plugin_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """序号超范围 / 版本号写错都重新问，不直接退出"""
    _set_stdin(monkeypatch, tty=True)
    _feed(monkeypatch, "9", "nonsense", "4", "0.7", "0.7.5", "y")
    assert bump.main(["--root", str(plugin_root)]) == 0
    assert bump.read_versions(plugin_root)[METADATA] == "v0.7.5"


def test_main_interactive_cancel_at_selection(
    plugin_root: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_stdin(monkeypatch, tty=True)
    _feed(monkeypatch)
    assert bump.main(["--root", str(plugin_root)]) == 1
    assert "已取消" in capsys.readouterr().out
    assert bump.read_versions(plugin_root)[METADATA] == "v0.5.0"


def test_main_interactive_cancel_at_custom_version(
    plugin_root: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_stdin(monkeypatch, tty=True)
    _feed(monkeypatch, "4", "")
    assert bump.main(["--root", str(plugin_root)]) == 1
    assert "已取消" in capsys.readouterr().out


def test_main_interactive_declines_confirmation(
    plugin_root: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_stdin(monkeypatch, tty=True)
    _feed(monkeypatch, "1", "n")
    assert bump.main(["--root", str(plugin_root)]) == 1
    out = capsys.readouterr().out
    assert "将要修改：v0.5.0 → v0.5.1" in out
    assert "已取消" in out
    assert bump.read_versions(plugin_root)[METADATA] == "v0.5.0"


def test_main_interactive_empty_confirmation_means_no(
    plugin_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """确认提示默认是否，回车即取消"""
    _set_stdin(monkeypatch, tty=True)
    _feed(monkeypatch, "1", "")
    assert bump.main(["--root", str(plugin_root)]) == 1
    assert bump.read_versions(plugin_root)[METADATA] == "v0.5.0"
