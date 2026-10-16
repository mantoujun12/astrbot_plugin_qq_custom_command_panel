"""机器人 v2 配置的纯数据存储与迁移。

本模块只处理 ``robot_config.json`` 的读写、校验，以及新旧配置的运行时合并，
不接触 Web API、日志或 AstrBot 运行时对象，方便离线测试。

新版配置按机器人维度组织：

```
{
  "version": 1,
  "robots": [...]
}
```

其中每条机器人包含平台凭证与四个场景的面板条目；旧的 schema 配置
（``qq_platforms`` + 全局 ``scenes`` + ``selected_commands``）继续作为兼容层，
运行时按 appid 与新配置合并，新版优先。

``version`` 是配置修订号，成功写入时递增，用于拒绝过期页面覆盖较新的配置。
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from .config import (
    PANEL_ITEM_DESC_MAX,
    PANEL_ITEM_NAME_MAX,
    PANEL_MAX_ITEMS,
    PLATFORM_TYPES,
    SCENES,
    get_enabled_scenes,
    get_platform_entries,
    get_selected_commands,
    mask_secret,
)

ROBOT_CONFIG_FILENAME = "robot_config.json"
"""新版机器人配置的落盘文件名。"""


class RobotConfigError(ValueError):
    """机器人配置读取失败时抛出的异常。"""


def empty_robot_config() -> dict[str, Any]:
    """返回空的新版机器人配置结构。"""
    return {"version": 1, "robots": []}


def _config_path(data_dir: str | Path) -> Path:
    """把数据目录解析成新版配置文件的 Path。"""
    return Path(data_dir) / ROBOT_CONFIG_FILENAME


def _empty_scenes() -> dict[str, dict[str, Any]]:
    """构造四个场景的默认禁用结构。"""
    return {scene: {"enabled": False, "items": []} for scene in SCENES}


def load_robot_config(data_dir: str | Path) -> dict[str, Any]:
    """从 ``data_dir`` 读取新版机器人配置。

    - 文件不存在时返回空结构；
    - 读取或 JSON 解析失败必须抛 :class:`RobotConfigError`，不允许静默回退空配置。
    """
    path = _config_path(data_dir)
    if not path.exists():
        return empty_robot_config()

    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise RobotConfigError(f"无法读取机器人配置文件 {path}：{exc}") from exc

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RobotConfigError(f"机器人配置文件不是有效的 JSON：{exc}") from exc

    if not isinstance(payload, dict):
        raise RobotConfigError("机器人配置文件顶层必须是对象")
    version = payload.get("version", 1)
    if type(version) is not int or version < 1:
        raise RobotConfigError("机器人配置文件 version 必须是正整数")
    if not isinstance(payload.get("robots", []), list):
        raise RobotConfigError("机器人配置文件 robots 必须是列表")

    return payload


def save_robot_config(data_dir: str | Path, payload: dict[str, Any]) -> Path:
    """原子写入新版机器人配置，并返回落盘路径。

    JSON 先写入同目录临时文件，再用 ``Path.replace`` 覆盖目标文件，
    避免进程中断留下半截配置。
    """
    target = _config_path(data_dir)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")

    try:
        temp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temp.replace(target)
    except OSError as exc:
        raise RobotConfigError(f"无法保存机器人配置 {target}：{exc}") from exc
    finally:
        if temp.exists():
            try:
                temp.unlink()
            except OSError:
                pass

    return target


def _existing_robot_secrets(existing: dict[str, Any]) -> dict[str, str]:
    """按 appid 收集现有机器人 secret，供空 secret 沿用。"""
    secrets: dict[str, str] = {}
    robots = existing.get("robots")
    if not isinstance(robots, list):
        return secrets
    for robot in robots:
        if not isinstance(robot, dict):
            continue
        appid = str(robot.get("appid") or "").strip()
        secret = str(robot.get("secret") or "").strip()
        if appid and secret:
            secrets.setdefault(appid, secret)
    return secrets


def _validate_scenes(
    scenes: Any,
    *,
    robot_index: int,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """校验并归一四个场景，返回 (scenes, errors)。"""
    errors: list[str] = []
    normalized = _empty_scenes()
    if not isinstance(scenes, dict):
        return normalized, [f"robots[{robot_index}].scenes：必须是对象"]

    for scene in SCENES:
        raw_scene = scenes.get(scene)
        if raw_scene is None:
            errors.append(f"robots[{robot_index}].scenes.{scene}：缺少场景配置")
            continue
        if not isinstance(raw_scene, dict):
            errors.append(f"robots[{robot_index}].scenes.{scene}：必须是对象")
            continue

        enabled = raw_scene.get("enabled", False)
        if not isinstance(enabled, bool):
            errors.append(f"robots[{robot_index}].scenes.{scene}.enabled：必须是布尔值")
            continue

        raw_items = raw_scene.get("items", [])
        if not isinstance(raw_items, list):
            errors.append(f"robots[{robot_index}].scenes.{scene}.items：必须是列表")
            continue
        if len(raw_items) > PANEL_MAX_ITEMS:
            errors.append(f"robots[{robot_index}].scenes.{scene}.items：最多 {PANEL_MAX_ITEMS} 条")
            continue
        if enabled and not raw_items:
            errors.append(f"robots[{robot_index}].scenes.{scene}.items：启用时至少需要 1 条")
            continue

        items: list[dict[str, str]] = []
        item_errors: list[str] = []
        for item_index, raw_item in enumerate(raw_items):
            if not isinstance(raw_item, dict):
                item_errors.append(
                    f"robots[{robot_index}].scenes.{scene}.items[{item_index}]：必须是对象"
                )
                continue
            raw_name = raw_item.get("name")
            name = raw_name.strip() if isinstance(raw_name, str) else ""
            if not name:
                item_errors.append(
                    f"robots[{robot_index}].scenes.{scene}.items[{item_index}].name：不能为空"
                )
                continue
            if len(name) > PANEL_ITEM_NAME_MAX:
                item_errors.append(
                    f"robots[{robot_index}].scenes.{scene}.items[{item_index}].name："
                    f"最多 {PANEL_ITEM_NAME_MAX} 个字符"
                )
                continue
            raw_desc = raw_item.get("desc", "")
            if raw_desc is None:
                desc = ""
            elif isinstance(raw_desc, str):
                desc = raw_desc.strip()
            else:
                item_errors.append(
                    f"robots[{robot_index}].scenes.{scene}.items[{item_index}].desc：必须是字符串"
                )
                continue
            if len(desc) > PANEL_ITEM_DESC_MAX:
                item_errors.append(
                    f"robots[{robot_index}].scenes.{scene}.items[{item_index}].desc："
                    f"最多 {PANEL_ITEM_DESC_MAX} 个字符"
                )
                continue
            items.append({"name": name, "desc": desc})

        if item_errors:
            errors.extend(item_errors)
            continue

        normalized[scene] = {"enabled": enabled, "items": items}

    return normalized, errors


def validate_robot_config(
    existing: dict[str, Any],
    payload: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """校验并归一新版机器人配置提交。

    返回 ``(normalized_config, errors)``；``errors`` 非空时调用方不应落库。
    appid 在整份配置内唯一；已有机器人的 secret 提交空字符串时沿用 ``existing``
    中按 appid 匹配的明文，新机器人则必须填写。
    """
    errors: list[str] = []
    if not isinstance(payload, dict):
        return empty_robot_config(), ["payload：必须是对象"]

    raw_robots = payload.get("robots", [])
    if not isinstance(raw_robots, list):
        return empty_robot_config(), ["robots：必须是列表"]

    secret_by_appid = _existing_robot_secrets(existing)
    robots: list[dict[str, Any]] = []
    seen_appids: set[str] = set()
    seen_ids: set[str] = set()

    for index, raw_robot in enumerate(raw_robots):
        if not isinstance(raw_robot, dict):
            errors.append(f"robots[{index}]：必须是对象")
            continue

        appid = str(raw_robot.get("appid") or "").strip()
        if not appid:
            errors.append(f"robots[{index}].appid：不能为空")
            continue
        if appid in seen_appids:
            errors.append(f"robots[{index}].appid：{appid} 重复")
            continue
        seen_appids.add(appid)

        raw_name = raw_robot.get("name")
        name = raw_name.strip() if isinstance(raw_name, str) else ""
        if not name:
            errors.append(f"robots[{index}].name：不能为空")
            continue
        if len(name) > PANEL_ITEM_NAME_MAX:
            errors.append(f"robots[{index}].name：最多 {PANEL_ITEM_NAME_MAX} 个字符")
            continue

        platform = str(raw_robot.get("platform") or "").strip()
        if platform not in PLATFORM_TYPES:
            errors.append(f"robots[{index}].platform：不支持的类型 {platform}")
            continue

        secret = str(raw_robot.get("secret") or "").strip()
        if not secret:
            secret = secret_by_appid.get(appid, "")
        if not secret:
            errors.append(f"robots[{index}].secret：新机器人必须填写 secret")
            continue

        scenes, scene_errors = _validate_scenes(raw_robot.get("scenes"), robot_index=index)
        if scene_errors:
            errors.extend(scene_errors)
            continue

        robot_id = raw_robot.get("id")
        if isinstance(robot_id, str) and robot_id.strip():
            normalized_id = robot_id.strip()
        else:
            normalized_id = str(uuid.uuid4())
        if normalized_id in seen_ids:
            errors.append(f"robots[{index}].id：{normalized_id} 重复")
            continue
        seen_ids.add(normalized_id)

        robots.append(
            {
                "id": normalized_id,
                "name": name,
                "appid": appid,
                "secret": secret,
                "platform": platform,
                "scenes": scenes,
            }
        )

    if errors:
        return empty_robot_config(), errors
    return {"version": 1, "robots": robots}, []


def export_robot_config(config: dict[str, Any]) -> dict[str, Any]:
    """导出可安全返回前端的新版配置，secret 只回掩码与是否已设置。"""
    robots: list[dict[str, Any]] = []
    raw_robots = config.get("robots")
    if not isinstance(raw_robots, list):
        return empty_robot_config()

    for raw_robot in raw_robots:
        if not isinstance(raw_robot, dict):
            continue
        appid = str(raw_robot.get("appid") or "").strip()
        if not appid:
            continue
        secret = str(raw_robot.get("secret") or "").strip()
        scenes = raw_robot.get("scenes")
        scenes_out = scenes if isinstance(scenes, dict) else {}
        robots.append(
            {
                "id": str(raw_robot.get("id") or ""),
                "name": str(raw_robot.get("name") or ""),
                "appid": appid,
                "platform": str(raw_robot.get("platform") or ""),
                "secret_masked": mask_secret(secret),
                "secret_set": bool(secret),
                "scenes": scenes_out,
            }
        )

    version = config.get("version", 1)
    if type(version) is not int or version < 1:
        version = 1
    return {"version": version, "robots": robots}


def get_runtime_robots(config: dict[str, Any]) -> list[dict[str, Any]]:
    """把单份新版配置转换成运行时机器人列表。"""
    runtime: list[dict[str, Any]] = []
    raw_robots = config.get("robots")
    if not isinstance(raw_robots, list):
        return runtime

    for robot in raw_robots:
        if not isinstance(robot, dict):
            continue
        appid = str(robot.get("appid") or "").strip()
        if not appid:
            continue
        scenes: dict[str, list[dict[str, str]]] = {scene: [] for scene in SCENES}
        raw_scenes = robot.get("scenes")
        if isinstance(raw_scenes, dict):
            for scene in SCENES:
                raw_scene = raw_scenes.get(scene)
                if not isinstance(raw_scene, dict) or not raw_scene.get("enabled"):
                    continue
                raw_items = raw_scene.get("items")
                if not isinstance(raw_items, list):
                    continue
                scenes[scene] = [
                    {
                        "name": str(item.get("name") or ""),
                        "desc": str(item.get("desc") or ""),
                    }
                    for item in raw_items
                    if isinstance(item, dict) and str(item.get("name") or "").strip()
                ]
        runtime.append(
            {
                "id": str(robot.get("id") or ""),
                "name": str(robot.get("name") or ""),
                "appid": appid,
                "secret": str(robot.get("secret") or ""),
                "platform": str(robot.get("platform") or ""),
                "source": "v2",
                "scenes": scenes,
            }
        )
    return runtime


def _legacy_runtime_robots(legacy_config: dict[str, Any]) -> list[dict[str, Any]]:
    """把旧 schema 配置转换成运行时机器人列表。"""
    enabled_scenes = get_enabled_scenes(legacy_config)
    selected_commands = get_selected_commands(legacy_config)
    runtime: list[dict[str, Any]] = []
    for entry in get_platform_entries(legacy_config):
        scenes: dict[str, list[dict[str, str]]] = {scene: [] for scene in SCENES}
        for scene in enabled_scenes:
            scenes[scene] = [
                {"name": item["name"], "desc": item["desc"]} for item in selected_commands
            ]
        runtime.append(
            {
                "id": entry["pf_id"],
                "name": entry["name"],
                "appid": entry["appid"],
                "secret": entry["secret"],
                "platform": entry["platform"],
                "source": "legacy",
                "scenes": scenes,
            }
        )
    return runtime


def build_runtime_robots(
    legacy_config: dict[str, Any],
    robot_config: dict[str, Any],
) -> list[dict[str, Any]]:
    """合并新旧配置为统一运行时机器人列表。

    新版按 appid 优先；未命中的旧 schema 机器人继续使用自身的全局场景与
    ``selected_commands``。
    """
    v2_robots = get_runtime_robots(robot_config)
    v2_appids = {robot["appid"] for robot in v2_robots}
    legacy_robots = [
        robot for robot in _legacy_runtime_robots(legacy_config) if robot["appid"] not in v2_appids
    ]
    runtime = [*v2_robots, *legacy_robots]
    seen_ids: set[str] = set()
    for robot in runtime:
        robot_id = str(robot.get("id") or robot.get("appid") or "")
        if robot_id in seen_ids:
            raise RobotConfigError(f"运行时机器人 id 重复：{robot_id}")
        seen_ids.add(robot_id)
    return runtime


def legacy_to_robot_drafts(legacy_config: dict[str, Any]) -> list[dict[str, Any]]:
    """把旧 schema 机器人转换成新版配置草稿。

    为每个启用场景准备同样的 ``selected_commands`` 条目，并保留 secret。
    草稿可直接作为新建机器人时的初始值，未包含稳定 id。
    """
    enabled_scenes = get_enabled_scenes(legacy_config)
    selected_commands = get_selected_commands(legacy_config)
    drafts: list[dict[str, Any]] = []
    for entry in get_platform_entries(legacy_config):
        scenes: dict[str, dict[str, Any]] = {}
        for scene in SCENES:
            enabled = scene in enabled_scenes
            scenes[scene] = {
                "enabled": enabled,
                "items": (
                    [{"name": item["name"], "desc": item["desc"]} for item in selected_commands]
                    if enabled
                    else []
                ),
            }
        drafts.append(
            {
                "name": entry["name"],
                "appid": entry["appid"],
                "secret": entry["secret"],
                "platform": entry["platform"],
                "scenes": scenes,
            }
        )
    return drafts


__all__ = [
    "ROBOT_CONFIG_FILENAME",
    "RobotConfigError",
    "build_runtime_robots",
    "empty_robot_config",
    "export_robot_config",
    "get_runtime_robots",
    "legacy_to_robot_drafts",
    "load_robot_config",
    "save_robot_config",
    "validate_robot_config",
]
