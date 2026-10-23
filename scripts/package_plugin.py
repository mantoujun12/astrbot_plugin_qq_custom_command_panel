#!/usr/bin/env python3
"""打包 AstrBot 插件 Release zip。

只把 AstrBot 在安装 / 运行 / 展示插件时真正会读取的内容打进 zip，
外加分发插件源码时必须随附的 LICENSE（AGPL-3.0）文本：

| 文件 / 目录           | 用途                                             |
| --------------------- | ------------------------------------------------ |
| metadata.yaml         | 插件元数据（名称 / 版本 / 作者 / 视图列表）      |
| main.py               | 插件入口模块                                     |
| _conf_schema.json     | WebUI 插件配置 schema                            |
| requirements.txt      | 运行时依赖清单（插件管理器据此 pip install）     |
| logo.png              | WebUI 插件图标                                   |
| README.md             | 插件详情页展示的说明                             |
| LICENSE               | AGPL-3.0 文本，AstrBot 不读但要随源码分发        |
| core/                 | main.py 依赖的插件自身 Python 包                 |
| .astrbot-plugin/      | WebUI metadata / config 的 i18n 翻译             |
| pages/（或 views/）   | 插件可视化视图静态产物                           |

仓库里的 tests/、web/、.github/、pyproject.toml、CHANGELOG.md 等
都不会被打进 zip。

用法：
    python scripts/package_plugin.py                 # 输出到 dist/
    python scripts/package_plugin.py -o out          # 指定输出目录
    python scripts/package_plugin.py -o out/x.zip    # 指定输出文件
    python scripts/package_plugin.py -v v0.5.0       # 覆盖包内 metadata.yaml 的版本号
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import zipfile
from collections.abc import Sequence
from pathlib import Path

__all__ = ["PLUGIN_DIRS", "PLUGIN_FILES", "build_package", "main"]

REPO_ROOT = Path(__file__).resolve().parent.parent

# 打包的顶层文件，存在才收录。
# 除 LICENSE 外的条目都是 AstrBot 读取的内容；LICENSE 是分发源码时必须随附的
# AGPL-3.0 文本，AstrBot 自己不读。
# 元数据只支持 metadata.yaml（与 build_package 读版本号的文件名保持一致）。
PLUGIN_FILES: tuple[str, ...] = (
    "metadata.yaml",
    "main.py",
    "_conf_schema.json",
    "requirements.txt",
    "logo.png",
    "README.md",
    "LICENSE",
)
# AstrBot 会读取的顶层目录，存在才打包（pages 与 views 互为别名）
PLUGIN_DIRS: tuple[str, ...] = (
    "core",
    ".astrbot-plugin",
    "pages",
    "views",
)
# 运行 / 构建缓存，不属于插件源码，打包时剔除
EXCLUDED_DIR_NAMES: frozenset[str] = frozenset({"__pycache__"})
EXCLUDED_SUFFIXES: tuple[str, ...] = (".pyc", ".pyo")

# 固定 zip 内文件时间戳，保证同一份源码每次打出的包内容一致（可复现构建）
ZIP_TIMESTAMP: tuple[int, int, int, int, int, int] = (1980, 1, 1, 0, 0, 0)


def _scalar_pattern(key: str) -> re.Pattern[str]:
    """匹配 metadata.yaml 顶层的标量字段，值两侧的引号必须成对"""
    return re.compile(
        rf"""^(?P<prefix>{re.escape(key)}:[ \t]*)(?P<quote>["']?)"""
        r"""(?P<value>[^"'\s#]+)(?P=quote)""",
        re.MULTILINE,
    )


def _read_metadata_text(metadata_path: Path) -> str:
    """按 UTF-8 读取 metadata.yaml（保留原始换行），读取失败时以 SystemExit 终止"""
    try:
        with metadata_path.open("r", encoding="utf-8", newline="") as handle:
            return handle.read()
    except OSError as exc:
        raise SystemExit(f"无法读取 {metadata_path}：{exc}") from exc


def _find_scalar(text: str, key: str, source: Path | str) -> re.Match[str]:
    """定位顶层标量字段；缺失或重复出现时直接报错，避免改错位置"""
    matches = list(_scalar_pattern(key).finditer(text))
    if not matches:
        raise SystemExit(f"{source} 中缺少 {key} 字段")
    if len(matches) > 1:
        raise SystemExit(f"{source} 中 {key} 字段出现多次，无法确定该用哪一个")
    return matches[0]


def _read_scalar(metadata_path: Path, key: str) -> str:
    """从 metadata.yaml 读取一个标量字段（不引入 PyYAML 依赖）"""
    text = _read_metadata_text(metadata_path)
    return _find_scalar(text, key, metadata_path)["value"]


def _replace_scalar(text: str, key: str, value: str, source: Path | str) -> str:
    """只替换标量值本身，保留其余内容（引号、注释、换行风格）"""
    match = _find_scalar(text, key, source)
    return f"{text[: match.start('value')]}{value}{text[match.end('value') :]}"


def _iter_plugin_entries(root: Path) -> list[tuple[Path, str]]:
    """收集要打包的文件，返回 (源文件绝对路径, zip 内相对路径) 列表"""
    entries: list[tuple[Path, str]] = []

    for filename in PLUGIN_FILES:
        path = root / filename
        if path.is_file():
            entries.append((path, filename))

    for dirname in PLUGIN_DIRS:
        base = root / dirname
        if not base.is_dir():
            continue
        for child in sorted(base.rglob("*")):
            if not child.is_file():
                continue
            rel_parts = child.relative_to(root).parts
            if any(part in EXCLUDED_DIR_NAMES for part in rel_parts):
                continue
            if child.suffix in EXCLUDED_SUFFIXES:
                continue
            entries.append((child, child.relative_to(root).as_posix()))

    return entries


def build_package(
    output: Path,
    *,
    version: str | None = None,
    root: Path = REPO_ROOT,
) -> Path:
    """把插件打包成 zip，返回生成的 zip 路径。

    Args:
        output: 输出目录，或以 ``.zip`` 结尾的输出文件路径。
        version: 覆盖包内 metadata.yaml 里的版本号（同时用于压缩包与顶层目录名）；
            省略时读取 metadata.yaml。
        root: 插件仓库根目录，默认取本脚本所在仓库根。

    Returns:
        生成的 zip 文件路径。
    """
    metadata_path = root / "metadata.yaml"
    if not metadata_path.is_file():
        raise SystemExit(f"未找到插件元数据：{metadata_path}")
    if not (root / "main.py").is_file():
        raise SystemExit(f"未找到插件入口模块：{root / 'main.py'}")

    metadata_text = _read_metadata_text(metadata_path)
    name = _find_scalar(metadata_text, "name", metadata_path)["value"]
    version = (version or _find_scalar(metadata_text, "version", metadata_path)["value"]).strip()
    if not version:
        raise SystemExit("版本号不能为空")
    folder = f"{name}-{version}"
    packaged_metadata = _replace_scalar(metadata_text, "version", version, metadata_path)

    zip_path = output if output.suffix == ".zip" else output / f"{folder}.zip"
    zip_path.parent.mkdir(parents=True, exist_ok=True)

    entries = _iter_plugin_entries(root)
    if not entries:
        raise SystemExit("没有找到任何可打包的插件文件")

    with zipfile.ZipFile(zip_path, "w") as archive:
        for src, rel in entries:
            info = zipfile.ZipInfo(f"{folder}/{rel}", date_time=ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            if rel == "metadata.yaml":
                archive.writestr(info, packaged_metadata.encode("utf-8"))
                continue
            with src.open("rb") as source, archive.open(info, "w") as target:
                shutil.copyfileobj(source, target)

    # 产物自检：包内版本必须与压缩包 / 顶层目录名用的版本一致，
    # 避免发出文件名是新版本、安装后却仍上报旧版本的包
    with zipfile.ZipFile(zip_path) as archive:
        packaged_text = archive.read(f"{folder}/metadata.yaml").decode("utf-8")
    packaged_version = _find_scalar(
        packaged_text, "version", f"{zip_path} 中的 {folder}/metadata.yaml"
    )["value"]
    if packaged_version != version:
        zip_path.unlink(missing_ok=True)
        raise SystemExit(
            f"打包校验失败：包内 metadata.yaml 的 version 为 {packaged_version!r}，"
            f"预期 {version!r}；已删除 {zip_path}"
        )

    return zip_path


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="打包 AstrBot 插件 zip")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=REPO_ROOT / "dist",
        help="输出目录，或以 .zip 结尾的输出文件（默认：dist/）",
    )
    parser.add_argument(
        "-v",
        "--version",
        default=None,
        help="覆盖包内 metadata.yaml 中的版本号（同时用于压缩包与顶层目录名）",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """脚本入口，返回进程退出码"""
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    zip_path = build_package(args.output, version=args.version)
    print(zip_path.as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
