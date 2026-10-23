"""scripts/package_plugin.py 的离线测试。

验证打包脚本只收录 AstrBot 会读取的文件（外加必须随源码分发的 LICENSE），
并剔除测试 / 构建产物。脚本不是包，用 importlib 按文件路径加载。
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "package_plugin.py"


def _load_package_script():
    """按文件路径加载打包脚本模块"""
    spec = importlib.util.spec_from_file_location("package_plugin", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


package_plugin = _load_package_script()


def test_build_package_only_includes_astrbot_files(tmp_path: Path) -> None:
    """从真实仓库打包：只包含 AstrBot 读取的文件，且单一顶层目录"""
    zip_path = package_plugin.build_package(tmp_path)
    assert zip_path.is_file()
    assert zip_path.parent == tmp_path

    with zipfile.ZipFile(zip_path) as archive:
        names = archive.namelist()

    top_levels = {name.split("/", 1)[0] for name in names}
    assert top_levels == {f"astrbot_plugin_qq_custom_command_panel-{_repo_version()}"}

    prefix = top_levels.pop() + "/"
    assert f"{prefix}metadata.yaml" in names
    assert f"{prefix}main.py" in names
    assert f"{prefix}_conf_schema.json" in names
    assert f"{prefix}requirements.txt" in names
    assert f"{prefix}core/web_api.py" in names
    assert f"{prefix}.astrbot-plugin/i18n/zh-CN.json" in names
    assert f"{prefix}.astrbot-plugin/i18n/ru-RU.json" in names
    assert f"{prefix}.astrbot-plugin/i18n/ja-JP.json" in names
    assert f"{prefix}core/i18n/ru-RU.json" in names
    assert f"{prefix}core/i18n/ja-JP.json" in names
    assert f"{prefix}pages/dashboard/index.html" in names
    # 分发源码必须随附 AGPL-3.0 文本
    assert f"{prefix}LICENSE" in names

    relative = {name[len(prefix) :] for name in names}
    for excluded in (
        "pyproject.toml",
        "CHANGELOG.md",
        "requirements-dev.txt",
        "AGENTS.md",
    ):
        assert excluded not in relative
    assert not any(name.startswith(("tests/", "web/", ".github/", "scripts/")) for name in relative)
    assert not any(part == "__pycache__" for name in relative for part in name.split("/"))
    assert not any(name.endswith((".pyc", ".pyo")) for name in relative)


def test_build_package_from_custom_root(tmp_path: Path) -> None:
    """最小插件目录：缺失的可选文件被跳过，缓存产物被剔除"""
    root = tmp_path / "plugin"
    (root / "core" / "__pycache__").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "metadata.yaml").write_text("name: demo_plugin\nversion: v1.2.3\n", encoding="utf-8")
    (root / "main.py").write_text("", encoding="utf-8")
    (root / "core" / "app.py").write_text("", encoding="utf-8")
    (root / "core" / "__pycache__" / "app.pyc").write_bytes(b"")
    (root / "tests" / "test_app.py").write_text("", encoding="utf-8")

    zip_path = package_plugin.build_package(tmp_path / "out", root=root)
    assert zip_path == tmp_path / "out" / "demo_plugin-v1.2.3.zip"

    with zipfile.ZipFile(zip_path) as archive:
        names = set(archive.namelist())

    assert names == {
        "demo_plugin-v1.2.3/metadata.yaml",
        "demo_plugin-v1.2.3/main.py",
        "demo_plugin-v1.2.3/core/app.py",
    }


def test_build_package_version_override_and_file_output(tmp_path: Path) -> None:
    """版本号可覆盖，输出参数以 .zip 结尾时直接作为 zip 路径"""
    root = tmp_path / "plugin"
    root.mkdir()
    (root / "metadata.yaml").write_bytes(b"name: demo_plugin\nversion: v1.2.3\n")
    (root / "main.py").write_text("", encoding="utf-8")

    zip_path = package_plugin.build_package(tmp_path / "custom.zip", version="v9.9.9", root=root)
    assert zip_path == tmp_path / "custom.zip"

    with zipfile.ZipFile(zip_path) as archive:
        assert set(archive.namelist()) == {
            "demo_plugin-v9.9.9/metadata.yaml",
            "demo_plugin-v9.9.9/main.py",
        }
        packaged_metadata = archive.read("demo_plugin-v9.9.9/metadata.yaml").decode("utf-8")

    # 覆盖版本号必须写进包内元数据，而不是只改压缩包 / 目录名
    assert packaged_metadata == "name: demo_plugin\nversion: v9.9.9\n"
    # 打包不会改动仓库里的源文件
    assert (root / "metadata.yaml").read_text(encoding="utf-8") == (
        "name: demo_plugin\nversion: v1.2.3\n"
    )


def test_build_package_version_override_preserves_metadata_format(tmp_path: Path) -> None:
    """覆盖版本号只替换值本身，保留引号、行尾注释、CRLF 与其余字段"""
    root = tmp_path / "plugin"
    root.mkdir()
    original = 'name: demo_plugin\r\nversion: "v1.2.3"  # 当前版本\r\n\r\nauthor: someone\r\n'
    (root / "metadata.yaml").write_bytes(original.encode("utf-8"))
    (root / "main.py").write_text("", encoding="utf-8")

    zip_path = package_plugin.build_package(tmp_path / "out", version="v9.9.9", root=root)

    with zipfile.ZipFile(zip_path) as archive:
        packaged_metadata = archive.read("demo_plugin-v9.9.9/metadata.yaml").decode("utf-8")

    assert packaged_metadata == (
        'name: demo_plugin\r\nversion: "v9.9.9"  # 当前版本\r\n\r\nauthor: someone\r\n'
    )


def test_build_package_rejects_packaged_version_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """打包后校验包内版本；不一致时删除产物并报错"""
    root = tmp_path / "plugin"
    root.mkdir()
    (root / "metadata.yaml").write_text("name: demo_plugin\nversion: v1.2.3\n", encoding="utf-8")
    (root / "main.py").write_text("", encoding="utf-8")

    # 模拟改写失效：压缩包名用新版本，但包内仍保留旧版本
    monkeypatch.setattr(
        package_plugin,
        "_replace_scalar",
        lambda text, key, value, source: text,
    )

    output = tmp_path / "custom.zip"
    with pytest.raises(SystemExit, match="打包校验失败"):
        package_plugin.build_package(output, version="v9.9.9", root=root)

    assert not output.exists()


def test_build_package_rejects_duplicate_version_field(tmp_path: Path) -> None:
    """metadata.yaml 里版本号出现多次时拒绝打包，避免改错位置"""
    root = tmp_path / "plugin"
    root.mkdir()
    (root / "metadata.yaml").write_text(
        "name: demo_plugin\nversion: v1.2.3\nversion: v2.3.4\n",
        encoding="utf-8",
    )
    (root / "main.py").write_text("", encoding="utf-8")

    with pytest.raises(SystemExit, match="version 字段出现多次"):
        package_plugin.build_package(tmp_path / "out", root=root)


def test_build_package_requires_version_field(tmp_path: Path) -> None:
    """metadata.yaml 缺少版本号时直接报错"""
    root = tmp_path / "plugin"
    root.mkdir()
    (root / "metadata.yaml").write_text("name: demo_plugin\n", encoding="utf-8")
    (root / "main.py").write_text("", encoding="utf-8")

    with pytest.raises(SystemExit, match="缺少 version 字段"):
        package_plugin.build_package(tmp_path / "out", root=root)


def test_build_package_rejects_blank_version_override(tmp_path: Path) -> None:
    """-v 只给了空白字符时按空版本号报错，不生成文件名异常的包"""
    root = tmp_path / "plugin"
    root.mkdir()
    (root / "metadata.yaml").write_text("name: demo_plugin\nversion: v1.2.3\n", encoding="utf-8")
    (root / "main.py").write_text("", encoding="utf-8")

    with pytest.raises(SystemExit, match="版本号不能为空"):
        package_plugin.build_package(tmp_path / "out", version="   ", root=root)


def test_build_package_requires_metadata(tmp_path: Path) -> None:
    """缺少 metadata.yaml 时直接报错"""
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(SystemExit):
        package_plugin.build_package(tmp_path / "out", root=empty)


def test_metadata_yml_is_not_supported(tmp_path: Path) -> None:
    """元数据文件名以 metadata.yaml 为准：metadata.yml 既不被接受也不被打包"""
    only_yml = tmp_path / "only_yml"
    only_yml.mkdir()
    (only_yml / "metadata.yml").write_text("name: demo\nversion: v1.0.0\n", encoding="utf-8")
    (only_yml / "main.py").write_text("", encoding="utf-8")
    with pytest.raises(SystemExit):
        package_plugin.build_package(tmp_path / "out", root=only_yml)

    both = tmp_path / "both"
    both.mkdir()
    (both / "metadata.yaml").write_text("name: demo\nversion: v1.0.0\n", encoding="utf-8")
    (both / "metadata.yml").write_text("name: demo\nversion: v2.0.0\n", encoding="utf-8")
    (both / "main.py").write_text("", encoding="utf-8")

    zip_path = package_plugin.build_package(tmp_path / "out", root=both)
    with zipfile.ZipFile(zip_path) as archive:
        # 版本号取自 metadata.yaml，且 metadata.yml 不进入包内
        assert set(archive.namelist()) == {
            "demo-v1.0.0/metadata.yaml",
            "demo-v1.0.0/main.py",
        }


def test_main_prints_zip_path_and_overrides_metadata_version(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """CLI 入口：返回 0、打印 zip 路径，且 -v 同时改写包内版本号"""
    assert package_plugin.main(["-o", str(tmp_path), "-v", "v9.9.9"]) == 0
    printed = capsys.readouterr().out.strip()
    assert printed

    zip_path = Path(printed)
    assert zip_path.is_file()
    name = package_plugin._read_scalar(REPO_ROOT / "metadata.yaml", "name")
    folder = f"{name}-v9.9.9"
    assert zip_path == tmp_path / f"{folder}.zip"

    with zipfile.ZipFile(zip_path) as archive:
        metadata = archive.read(f"{folder}/metadata.yaml").decode("utf-8")
    assert "version: v9.9.9" in metadata.splitlines()


def test_packaged_zip_is_importable_as_plugin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """模拟 AstrBot 安装流程：解压 zip -> 按 metadata.name 落目录 -> 导入入口模块。

    打包结果必须自洽：解压后不依赖仓库工作区即可作为 `data.plugins.<name>.main` 导入。
    """
    zip_path = package_plugin.build_package(tmp_path / "dist")

    install_root = tmp_path / "fake_data" / "plugins"
    install_root.mkdir(parents=True)
    extract_root = tmp_path / "extract"
    with zipfile.ZipFile(zip_path) as archive:
        assert archive.testzip() is None, "zip CRC 校验失败"
        archive.extractall(extract_root)

    name = package_plugin._read_scalar(REPO_ROOT / "metadata.yaml", "name")
    plugin_dir = install_root / name
    next(extract_root.iterdir()).rename(plugin_dir)

    # AstrBot 通过 data.plugins.<root_dir_name> 定位插件，这里用 fake_data 模拟命名空间包
    (tmp_path / "fake_data" / "__init__.py").write_text("", encoding="utf-8")
    (install_root / "__init__.py").write_text("", encoding="utf-8")

    monkeypatch.syspath_prepend(str(tmp_path))
    module_name = f"fake_data.plugins.{name}.main"
    try:
        module = importlib.import_module(module_name)
    finally:
        for key in [k for k in sys.modules if k == "fake_data" or k.startswith("fake_data.")]:
            del sys.modules[key]

    assert module.PLUGIN_NAME == name
    assert module.QQCommandPanelPlugin.__name__ == "QQCommandPanelPlugin"


def _repo_version() -> str:
    """从仓库 metadata.yaml 读取版本号，避免测试硬编码版本"""
    return package_plugin._read_scalar(REPO_ROOT / "metadata.yaml", "version")
