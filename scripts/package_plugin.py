#!/usr/bin/env python3
"""打包 AstrBot 插件 Release zip。

只把 AstrBot 在安装 / 运行 / 展示插件时真正会读取的内容打进 zip：

| 文件 / 目录           | AstrBot 用途                                     |
| --------------------- | ------------------------------------------------ |
| metadata.yaml         | 插件元数据（名称 / 版本 / 作者 / 视图列表）      |
| main.py               | 插件入口模块                                     |
| _conf_schema.json     | WebUI 插件配置 schema                            |
| requirements.txt      | 运行时依赖清单（插件管理器据此 pip install）     |
| logo.png              | WebUI 插件图标                                   |
| README.md             | 插件详情页展示的说明                             |
| core/                 | main.py 依赖的插件自身 Python 包                 |
| .astrbot-plugin/      | WebUI metadata / config 的 i18n 翻译             |
| pages/（或 views/）   | 插件可视化视图静态产物                           |

仓库里的 tests/、web/、.github/、pyproject.toml、LICENSE、CHANGELOG.md 等
都不是 AstrBot 读取的内容，不会被打进 zip。

用法：
    python scripts/package_plugin.py                 # 输出到 dist/
    python scripts/package_plugin.py -o out          # 指定输出目录
    python scripts/package_plugin.py -o out/x.zip    # 指定输出文件
    python scripts/package_plugin.py -v v0.5.0       # 覆盖版本号
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

# AstrBot 会读取的顶层文件，存在才打包
PLUGIN_FILES: tuple[str, ...] = (
    "metadata.yaml",
    "metadata.yml",
    "main.py",
    "_conf_schema.json",
    "requirements.txt",
    "logo.png",
    "README.md",
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


def _read_scalar(metadata_path: Path, key: str) -> str:
    """从 metadata.yaml 读取一个标量字段（不引入 PyYAML 依赖）"""
    try:
        text = metadata_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SystemExit(f"无法读取 {metadata_path}：{exc}") from exc

    pattern = rf"""^{re.escape(key)}:[ \t]*["']?([^"'\s#]+)["']?"""
    match = re.search(pattern, text, re.MULTILINE)
    if match is None:
        raise SystemExit(f"{metadata_path} 中缺少 {key} 字段")
    return match.group(1)


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
        version: 覆盖 metadata.yaml 里的版本号；省略时读取 metadata.yaml。
        root: 插件仓库根目录，默认取本脚本所在仓库根。

    Returns:
        生成的 zip 文件路径。
    """
    metadata_path = root / "metadata.yaml"
    if not metadata_path.is_file():
        raise SystemExit(f"未找到插件元数据：{metadata_path}")
    if not (root / "main.py").is_file():
        raise SystemExit(f"未找到插件入口模块：{root / 'main.py'}")

    name = _read_scalar(metadata_path, "name")
    version = version or _read_scalar(metadata_path, "version")
    folder = f"{name}-{version}"

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
            with src.open("rb") as source, archive.open(info, "w") as target:
                shutil.copyfileobj(source, target)

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
        help="覆盖 metadata.yaml 中的版本号",
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
