#!/usr/bin/env python3
"""升级插件版本号。

metadata.yaml 是插件的唯一版本源，`.github/workflows/release.yml` 在打 tag 前会校验
其余文件与它一致，因此版本号必须一起修改：

- metadata.yaml：`version: v0.6.0` —— 唯一版本源，AstrBot 与发布流程都读它
- core/paths.py：`PLUGIN_VERSION = "v0.6.0"` —— 插件运行期上报的版本（@register / 视图）
- web/dashboard/package.json：`"version": "0.6.0"` —— npm 侧版本号，不带 v 前缀

CHANGELOG.md 的 `[Unreleased]` 段落与前端 mock 假数据不在这里改：前者需要人来写发布说明，
后者只是本地 dev 的假数据，不是版本源。

用法：
    python scripts/bump_version.py                  # 交互式选择 patch / minor / major / 自定义
    python scripts/bump_version.py patch            # 递增 patch（minor / major 同理）
    python scripts/bump_version.py 0.6.0            # 指定版本（v 前缀可省略）
    python scripts/bump_version.py --dry-run minor  # 只预览，不写文件
    python scripts/bump_version.py -y patch         # 跳过写入前的确认
    python scripts/bump_version.py --check          # 只校验三个文件的版本号是否一致
    python scripts/bump_version.py --force 0.4.0    # 允许降级到更低的版本号

退出码：0 成功（含 --check 通过）、1 出错或被取消。stdin 不是终端时必须显式
给出版本号，且不会再询问确认。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "BUMP_KINDS",
    "VERSION_FILES",
    "BumpError",
    "Version",
    "VersionEdit",
    "VersionFile",
    "apply_version",
    "format_version",
    "main",
    "next_version",
    "parse_version",
    "plan_changes",
    "read_version",
    "read_versions",
]

REPO_ROOT = Path(__file__).resolve().parent.parent

# 唯一版本源：其余文件的版本号都必须跟它一致
VERSION_SOURCE = "metadata.yaml"

# (major, minor, patch)
Version = tuple[int, int, int]

# vX.Y.Z / X.Y.Z。与 release.yml 的校验保持一致：不接受预发布 / 构建后缀，
# 因为 AstrBot 与发布 tag 都只认三段式版本号
_VERSION_RE = re.compile(r"^v?(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)$")


class BumpError(Exception):
    """版本号处理失败：版本不合法、文件缺失、找不到版本号或匹配到多处"""


@dataclass(frozen=True)
class VersionFile:
    """一个跟随插件版本号的文件。

    pattern 里的命名组 ``version`` 只覆盖版本号本身，写回时仅替换这段区间，
    因此文件其余内容（缩进 / 引号 / 换行风格）原样保留。
    """

    relpath: str
    pattern: re.Pattern[str]
    # 该文件里的版本号是否带 v 前缀（metadata.yaml / core/paths.py 带，npm 不带）
    v_prefix: bool
    # 供报错提示期望的写法，如 `version: v0.6.0`
    hint: str


VERSION_FILES: tuple[VersionFile, ...] = (
    VersionFile(
        relpath=VERSION_SOURCE,
        pattern=re.compile(r"""^version:[ \t]*["']?(?P<version>[^"'\s#]+)""", re.MULTILINE),
        v_prefix=True,
        hint="version: v0.6.0",
    ),
    VersionFile(
        relpath="core/paths.py",
        pattern=re.compile(
            r"""^PLUGIN_VERSION[ \t]*=[ \t]*["']?(?P<version>[^"'\s#]+)""", re.MULTILINE
        ),
        v_prefix=True,
        hint='PLUGIN_VERSION = "v0.6.0"',
    ),
    VersionFile(
        relpath="web/dashboard/package.json",
        pattern=re.compile(
            r"""^[ \t]*"version"[ \t]*:[ \t]*"?(?P<version>[^"\s,]+)""", re.MULTILINE
        ),
        v_prefix=False,
        hint='"version": "0.6.0"',
    ),
)

BUMP_KINDS: tuple[str, ...] = ("patch", "minor", "major")

_CANCEL_HINT = "已取消，未修改任何文件。"


@dataclass(frozen=True)
class VersionEdit:
    """一次版本号替换：目标文件、改前的写法、改后的写法，以及算好的新文件内容"""

    relpath: str
    previous: str
    current: str
    path: Path
    text: str


def parse_version(text: str) -> Version:
    """把 ``v0.6.0`` / ``0.6.0`` 解析成 ``(major, minor, patch)``。

    Raises:
        BumpError: 不是三段式版本号。
    """
    match = _VERSION_RE.match(text.strip())
    if match is None:
        raise BumpError(f"版本号格式不合法：{text!r}（应形如 v0.6.0）")
    return (int(match["major"]), int(match["minor"]), int(match["patch"]))


def format_version(version: Version, *, v_prefix: bool = True) -> str:
    """把 ``(major, minor, patch)`` 格式化成 ``v0.6.0``（``v_prefix=False`` 时为 ``0.6.0``）"""
    text = ".".join(str(part) for part in version)
    return f"v{text}" if v_prefix else text


def next_version(current: Version, kind: str) -> Version:
    """按语义化版本递增 ``current``：``patch`` / ``minor`` / ``major``。

    Raises:
        BumpError: kind 不是上面三种之一。
    """
    major, minor, patch = current
    if kind == "patch":
        return (major, minor, patch + 1)
    if kind == "minor":
        return (major, minor + 1, 0)
    if kind == "major":
        return (major + 1, 0, 0)
    raise BumpError(f"未知的递增方式：{kind!r}（可选：{' / '.join(BUMP_KINDS)}）")


def _read_text(path: Path) -> str:
    """按 UTF-8 读取，且不做换行转换，写回时才能原样保留 CRLF / LF"""
    with path.open("r", encoding="utf-8", newline="") as handle:
        return handle.read()


def _write_text(path: Path, text: str) -> None:
    """按 UTF-8 写回，同样不做换行转换"""
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def _locate(target: VersionFile, text: str) -> re.Match[str]:
    """定位版本号 token；找不到或匹配到多处都直接报错，宁可失败也不改错地方"""
    matches = list(target.pattern.finditer(text))
    if not matches:
        raise BumpError(f"{target.relpath}：找不到版本号（期望形如 {target.hint}）")
    if len(matches) > 1:
        raise BumpError(f"{target.relpath} 里匹配到 {len(matches)} 处版本号，无法确定该改哪一处")
    return matches[0]


def _validate_result(target: VersionFile, text: str, expected: str) -> None:
    """写回前自检：JSON 目标必须仍是合法 JSON，且 version 字段正是新版本号"""
    if not target.relpath.endswith(".json"):
        return
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise BumpError(f"{target.relpath}：改写后不是合法 JSON（{exc}）") from exc
    if not isinstance(payload, dict) or payload.get("version") != expected:
        raise BumpError(f"{target.relpath}：改写后顶层 version 不是 {expected}")


def read_version(root: Path, target: VersionFile) -> str:
    """读取文件里原样的版本号写法（如 ``v0.6.0`` / ``0.6.0``）

    Raises:
        BumpError: 文件不存在，或里面找不到 / 找到多处版本号。
    """
    path = root / target.relpath
    if not path.is_file():
        raise BumpError(f"未找到文件：{path}")
    return _locate(target, _read_text(path))["version"]


def read_versions(root: Path = REPO_ROOT) -> dict[str, str]:
    """读取全部目标文件的版本号，返回 ``{相对路径: 原样写法}``，顺序同 :data:`VERSION_FILES`"""
    return {target.relpath: read_version(root, target) for target in VERSION_FILES}


def plan_changes(version: Version, *, root: Path = REPO_ROOT) -> list[VersionEdit]:
    """在内存里算好各处替换，不落盘。

    任一文件缺失、找不到版本号或改后不合法都会抛错 —— 调用方拿到的要么是完整的一组
    替换，要么什么都没有，不会出现「改了一半」。

    Raises:
        BumpError: 任一目标文件不满足预期。
    """
    edits: list[VersionEdit] = []
    for target in VERSION_FILES:
        path = root / target.relpath
        if not path.is_file():
            raise BumpError(f"未找到文件：{path}")
        text = _read_text(path)
        match = _locate(target, text)
        current = format_version(version, v_prefix=target.v_prefix)
        updated = f"{text[: match.start('version')]}{current}{text[match.end('version') :]}"
        _validate_result(target, updated, current)
        edits.append(
            VersionEdit(
                relpath=target.relpath,
                previous=match["version"],
                current=current,
                path=path,
                text=updated,
            )
        )
    return edits


def apply_version(version: Version, *, root: Path = REPO_ROOT) -> list[VersionEdit]:
    """把版本号写进所有目标文件，返回逐文件的改前 / 改后写法。

    先算好全部替换再统一落盘，并在写完后回读校验。

    Raises:
        BumpError: 任一目标文件不满足预期，或写回后回读结果不符。
    """
    edits = plan_changes(version, root=root)
    for edit in edits:
        _write_text(edit.path, edit.text)
    for target in VERSION_FILES:
        if parse_version(read_version(root, target)) != version:
            raise BumpError(f"{target.relpath}：写回后读到的版本号不是 {format_version(version)}")
    return edits


def _parse_or_none(raw: str) -> Version | None:
    """解析版本号，格式不合法时返回 None（供校验流程逐条汇报问题）"""
    try:
        return parse_version(raw)
    except BumpError:
        return None


def _check_versions(versions: dict[str, str], current: Version) -> int:
    """校验各文件的版本号与 metadata.yaml 一致、写法规范；返回进程退出码"""
    problems: list[str] = []
    by_relpath = {target.relpath: target for target in VERSION_FILES}
    for relpath, raw in versions.items():
        expected_raw = format_version(current, v_prefix=by_relpath[relpath].v_prefix)
        version = _parse_or_none(raw)
        if version is None:
            problems.append(f"{relpath}：{raw} 不是合法版本号")
        elif version != current:
            problems.append(
                f"{relpath}：{raw} 与 {VERSION_SOURCE} 的 {format_version(current)} 不一致"
            )
        elif raw != expected_raw:
            problems.append(f"{relpath}：{raw} 应写成 {expected_raw}")

    if problems:
        print(f"版本号校验未通过（以 {VERSION_SOURCE} 为准）：", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1
    print(f"版本号校验通过：{format_version(current)}")
    return 0


def _stdin_is_interactive() -> bool:
    """stdin 是否为终端；管道 / CI 下不能停下来等人输入"""
    try:
        return sys.stdin.isatty()
    except (AttributeError, ValueError):
        return False


def _prompt(text: str) -> str:
    """读一行输入并去掉首尾空白；EOF / Ctrl+C 视为取消，返回空串"""
    try:
        return input(text).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return ""


def _prompt_custom_version() -> Version | None:
    """询问自定义版本号；返回 None 表示取消"""
    while True:
        answer = _prompt("请输入版本号（如 0.6.0）：")
        if not answer:
            return None
        try:
            return parse_version(answer)
        except BumpError as exc:
            print(f"  {exc}", file=sys.stderr)


def _prompt_version(current: Version) -> Version | None:
    """交互式询问目标版本号；返回 None 表示取消。

    除了菜单里的序号，也可以直接输入版本号，省掉一次选择。
    """
    print(f"当前版本：{format_version(current)}")
    for index, kind in enumerate(BUMP_KINDS, start=1):
        target = format_version(next_version(current, kind))
        print(f"  {index}) {kind:<5} {format_version(current)} → {target}")
    custom_index = len(BUMP_KINDS) + 1
    print(f"  {custom_index}) 自定义")

    while True:
        answer = _prompt(f"请选择 [1-{custom_index}]（也可直接输入版本号）：")
        if not answer:
            return None
        if answer.isdigit():
            index = int(answer)
            if 1 <= index <= len(BUMP_KINDS):
                return next_version(current, BUMP_KINDS[index - 1])
            if index == custom_index:
                return _prompt_custom_version()
        try:
            return parse_version(answer)
        except BumpError as exc:
            print(f"  {exc}", file=sys.stderr)


def _confirm(question: str) -> bool:
    """确认提示；直接回车按「否」处理，避免误改文件"""
    return _prompt(f"{question}[y/N] ").lower() in {"y", "yes"}


def _print_edits(edits: Sequence[VersionEdit], header: str) -> None:
    """按列对齐打印逐文件的版本号变化"""
    width = max(len(edit.relpath) for edit in edits)
    print(header)
    for edit in edits:
        print(f"  {edit.relpath.ljust(width)}  {edit.previous} → {edit.current}")


def _parse_target(raw: str, current: Version) -> Version:
    """把命令行参数解析成目标版本：``patch`` / ``minor`` / ``major`` 或 ``X.Y.Z``"""
    text = raw.strip()
    if text in BUMP_KINDS:
        return next_version(current, text)
    try:
        return parse_version(text)
    except BumpError as exc:
        kinds = " / ".join(BUMP_KINDS)
        raise BumpError(
            f"无法识别的版本号或递增方式：{text!r}（应为 X.Y.Z / vX.Y.Z，或 {kinds}）"
        ) from exc


def _resolve_target(args: argparse.Namespace, current: Version) -> Version | None:
    """确定目标版本号：命令行参数优先，否则交互式询问；返回 None 表示用户取消"""
    if args.version is not None:
        return _parse_target(args.version, current)
    if not _stdin_is_interactive():
        raise BumpError(
            "没有指定版本号，且当前输入不是交互式终端：请显式传入 X.Y.Z 或 patch / minor / major"
        )
    return _prompt_version(current)


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="升级插件版本号（metadata.yaml / core/paths.py / web/dashboard/package.json）",
        epilog="省略版本参数时进入交互式询问。",
    )
    parser.add_argument(
        "version",
        nargs="?",
        default=None,
        help="X.Y.Z / vX.Y.Z，或 patch / minor / major；省略时交互式询问",
    )
    parser.add_argument(
        "--check", action="store_true", help="只校验各文件的版本号是否一致，不做修改"
    )
    parser.add_argument("--dry-run", action="store_true", help="只预览将要写入的内容，不修改文件")
    parser.add_argument("-y", "--yes", action="store_true", help="跳过写入前的确认")
    parser.add_argument("--force", action="store_true", help="允许改成比当前更低的版本号")
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help="插件仓库根目录（默认：本脚本所在的仓库）",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """脚本入口，返回进程退出码"""
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    root: Path = args.root

    try:
        versions = read_versions(root)
        current = parse_version(versions[VERSION_SOURCE])
    except BumpError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1

    if args.check:
        return _check_versions(versions, current)

    try:
        target = _resolve_target(args, current)
    except BumpError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1

    if target is None:
        print(_CANCEL_HINT)
        return 1

    if target == current:
        drifted = [relpath for relpath, raw in versions.items() if _parse_or_none(raw) != current]
        if not drifted:
            print(f"当前版本已经是 {format_version(current)}，无需修改。")
            return 0
        print(
            f"注意：{'、'.join(drifted)} 与 {VERSION_SOURCE} 不一致，"
            f"本次会把它们对齐到 {format_version(current)}。",
            file=sys.stderr,
        )
    elif target < current and not args.force:
        print(
            f"错误：目标版本 {format_version(target)} 低于当前版本 {format_version(current)}，"
            "确实要降级请加 --force。",
            file=sys.stderr,
        )
        return 1

    try:
        edits = plan_changes(target, root=root)
    except BumpError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1

    headline = f"{format_version(current)} → {format_version(target)}"
    if args.dry_run:
        _print_edits(edits, f"预览（--dry-run，未写入任何文件）：{headline}")
        return 0

    if not args.yes and _stdin_is_interactive():
        _print_edits(edits, f"将要修改：{headline}")
        if not _confirm("确认写入？"):
            print(_CANCEL_HINT)
            return 1

    try:
        apply_version(target, root=root)
    except BumpError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1

    _print_edits(edits, f"已更新版本：{headline}")
    print()
    print(
        f"下一步：整理 CHANGELOG.md 的 [Unreleased] 段落，提交后推送到 master —— "
        f"{VERSION_SOURCE} 变更会触发 release.yml 打 tag 并发布。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
