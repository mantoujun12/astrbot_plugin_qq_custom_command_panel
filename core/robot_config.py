"""机器人 v2 配置的纯数据存储与迁移。

只处理 ``robot_config.json`` 的读写、校验与新旧配置的运行时合并，不接触 Web API、
日志或 AstrBot 运行时对象，方便离线测试。结构为 ``{"version": 1, "robots": [...]}``，
每条机器人包含平台凭证与四个场景的面板条目；旧的 schema 配置（``qq_platforms`` 与
全局 ``scenes`` + ``selected_commands``）作为兼容层，运行时按 appid 合并，新版优先。
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
from .i18n import t

ROBOT_CONFIG_FILENAME = "robot_config.json"


class RobotConfigError(ValueError):
    """读取、校验、保存新版配置失败，或运行时合并出现冲突时抛出。"""


def empty_robot_config() -> dict[str, Any]:
    return {"version": 1, "robots": []}


def _config_path(data_dir: str | Path) -> Path:
    return Path(data_dir) / ROBOT_CONFIG_FILENAME


def _empty_scenes() -> dict[str, dict[str, Any]]:
    return {scene: {"enabled": False, "items": []} for scene in SCENES}


def load_robot_config(data_dir: str | Path) -> dict[str, Any]:
    """从 ``data_dir`` 读取新版机器人配置。

    文件不存在时返回空结构；读取或解析失败抛 :class:`RobotConfigError`，不静默回退空配置。
    """
    path = _config_path(data_dir)
    if not path.exists():
        return empty_robot_config()

    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise RobotConfigError(t("robot.error.read_failed", path=path, exc=exc)) from exc

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RobotConfigError(t("robot.error.invalid_json", exc=exc)) from exc

    if not isinstance(payload, dict):
        raise RobotConfigError(t("robot.error.top_level_object"))
    version = payload.get("version", 1)
    if type(version) is not int or version < 1:
        raise RobotConfigError(t("robot.error.version_invalid"))
    if not isinstance(payload.get("robots", []), list):
        raise RobotConfigError(t("robot.error.robots_type"))

    # 复用写入路径的归一化结果，但保留原文件中的 revision，避免乐观并发检查被重置。
    normalized, errors = validate_robot_config(empty_robot_config(), payload)
    if errors:
        raise RobotConfigError("\n".join(errors))
    normalized["version"] = version

    return normalized


def save_robot_config(data_dir: str | Path, payload: dict[str, Any]) -> Path:
    """原子写入新版机器人配置并返回落盘路径，避免进程中断留下半截配置。"""
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
        raise RobotConfigError(t("robot.error.save_failed", path=target, exc=exc)) from exc
    finally:
        if temp.exists():
            try:
                temp.unlink()
            except OSError:
                pass

    return target


def _existing_robot_secrets(existing: dict[str, Any]) -> dict[str, str]:
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
    errors: list[str] = []
    normalized = _empty_scenes()
    if not isinstance(scenes, dict):
        path = f"robots[{robot_index}].scenes"
        return normalized, [t("robot.error.scenes_type", path=path)]

    for scene in scenes:
        if scene not in SCENES:
            errors.append(
                t(
                    "robot.error.scene_unknown",
                    path=f"robots[{robot_index}].scenes.{scene}",
                    scene=scene,
                )
            )

    for scene in SCENES:
        scene_path = f"robots[{robot_index}].scenes.{scene}"
        raw_scene = scenes.get(scene)
        if raw_scene is None:
            errors.append(t("robot.error.scene_missing", path=scene_path))
            continue
        if not isinstance(raw_scene, dict):
            errors.append(t("robot.error.scene_type", path=scene_path))
            continue

        enabled = raw_scene.get("enabled", False)
        if not isinstance(enabled, bool):
            errors.append(t("robot.error.scene_enabled_type", path=f"{scene_path}.enabled"))
            continue

        raw_items = raw_scene.get("items", [])
        if not isinstance(raw_items, list):
            errors.append(t("robot.error.scene_items_type", path=f"{scene_path}.items"))
            continue
        if len(raw_items) > PANEL_MAX_ITEMS:
            errors.append(
                t(
                    "robot.error.scene_items_limit",
                    path=f"{scene_path}.items",
                    limit=PANEL_MAX_ITEMS,
                )
            )
            continue
        if enabled and not raw_items:
            errors.append(t("robot.error.scene_items_empty", path=f"{scene_path}.items"))
            continue

        items: list[dict[str, str]] = []
        item_errors: list[str] = []
        for item_index, raw_item in enumerate(raw_items):
            item_path = f"{scene_path}.items[{item_index}]"
            if not isinstance(raw_item, dict):
                item_errors.append(t("robot.error.item_type", path=item_path))
                continue
            raw_name = raw_item.get("name")
            name = raw_name.strip() if isinstance(raw_name, str) else ""
            if not name:
                item_errors.append(t("robot.error.item_name_required", path=f"{item_path}.name"))
                continue
            if len(name) > PANEL_ITEM_NAME_MAX:
                item_errors.append(
                    t(
                        "robot.error.item_name_too_long",
                        path=f"{item_path}.name",
                        limit=PANEL_ITEM_NAME_MAX,
                    )
                )
                continue
            raw_desc = raw_item.get("desc", "")
            if raw_desc is None:
                desc = ""
            elif isinstance(raw_desc, str):
                desc = raw_desc.strip()
            else:
                item_errors.append(t("robot.error.item_desc_type", path=f"{item_path}.desc"))
                continue
            if len(desc) > PANEL_ITEM_DESC_MAX:
                item_errors.append(
                    t(
                        "robot.error.item_desc_too_long",
                        path=f"{item_path}.desc",
                        limit=PANEL_ITEM_DESC_MAX,
                    )
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
    """校验并归一新版机器人配置提交，返回 ``(normalized_config, errors)``。

    ``errors`` 非空时调用方不应落库；appid 在整份配置内唯一，已有机器人提交空 secret
    时沿用以 appid 匹配的 ``existing`` 明文，新机器人必须填写。
    """
    errors: list[str] = []
    if not isinstance(payload, dict):
        return empty_robot_config(), [t("robot.error.payload_type")]

    raw_robots = payload.get("robots", [])
    if not isinstance(raw_robots, list):
        return empty_robot_config(), [t("robot.error.robots_list")]

    secret_by_appid = _existing_robot_secrets(existing)
    robots: list[dict[str, Any]] = []
    seen_appids: set[str] = set()
    seen_ids: set[str] = set()

    for index, raw_robot in enumerate(raw_robots):
        robot_path = f"robots[{index}]"
        if not isinstance(raw_robot, dict):
            errors.append(t("robot.error.robot_entry_type", path=robot_path))
            continue

        raw_appid = raw_robot.get("appid")
        appid = raw_appid.strip() if isinstance(raw_appid, str) else ""
        if not appid:
            errors.append(t("robot.error.appid_required", path=f"{robot_path}.appid"))
            continue
        if appid in seen_appids:
            errors.append(
                t(
                    "robot.error.appid_duplicate",
                    path=f"{robot_path}.appid",
                    appid=appid,
                )
            )
            continue
        seen_appids.add(appid)

        raw_name = raw_robot.get("name")
        name = raw_name.strip() if isinstance(raw_name, str) else ""
        if not name:
            errors.append(t("robot.error.name_required", path=f"{robot_path}.name"))
            continue
        if len(name) > PANEL_ITEM_NAME_MAX:
            errors.append(
                t(
                    "robot.error.name_too_long",
                    path=f"{robot_path}.name",
                    limit=PANEL_ITEM_NAME_MAX,
                )
            )
            continue

        raw_platform = raw_robot.get("platform")
        platform = raw_platform.strip() if isinstance(raw_platform, str) else ""
        if platform not in PLATFORM_TYPES:
            errors.append(
                t(
                    "robot.error.platform_unsupported",
                    path=f"{robot_path}.platform",
                    platform=platform,
                )
            )
            continue

        raw_secret = raw_robot.get("secret")
        if not isinstance(raw_secret, str):
            errors.append(t("robot.error.secret_type", path=f"{robot_path}.secret"))
            continue
        secret = raw_secret.strip()
        if not secret:
            secret = secret_by_appid.get(appid, "")
        if not secret:
            errors.append(t("robot.error.secret_required", path=f"{robot_path}.secret"))
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
            errors.append(
                t(
                    "robot.error.id_duplicate",
                    path=f"{robot_path}.id",
                    id=normalized_id,
                )
            )
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
    """只转换新版配置，不做旧 schema 合并；合并规则见 :func:`build_runtime_robots`。"""
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
    enabled_scenes = get_enabled_scenes(legacy_config)
    selected_commands = get_selected_commands(legacy_config)
    runtime: list[dict[str, Any]] = []
    for entry in get_platform_entries(legacy_config):
        appid = entry["appid"].strip()
        if not appid:
            continue
        scenes: dict[str, list[dict[str, str]]] = {scene: [] for scene in SCENES}
        for scene in enabled_scenes:
            scenes[scene] = [
                {"name": item["name"], "desc": item["desc"]} for item in selected_commands
            ]
        runtime.append(
            {
                "id": entry["pf_id"],
                "name": entry["name"],
                "appid": appid,
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
    """合并新旧配置为统一运行时机器人列表：新版按 appid 接管，未命中的旧 schema
    机器人继续使用全局场景与 ``selected_commands``。"""
    v2_robots = get_runtime_robots(robot_config)
    v2_appids = {robot["appid"] for robot in v2_robots}
    legacy_robots = [
        robot for robot in _legacy_runtime_robots(legacy_config) if robot["appid"] not in v2_appids
    ]
    runtime = [*v2_robots, *legacy_robots]
    seen_ids: set[str] = set()
    seen_appids: set[str] = set()
    for robot in runtime:
        appid = str(robot.get("appid") or "").strip()
        if appid and appid in seen_appids:
            raise RobotConfigError(t("robot.error.runtime_appid_duplicate", appid=appid))
        seen_appids.add(appid)

        robot_id = str(robot.get("id") or robot.get("appid") or "")
        if robot_id in seen_ids:
            raise RobotConfigError(t("robot.error.runtime_id_duplicate", robot_id=robot_id))
        seen_ids.add(robot_id)
    return runtime


def legacy_to_robot_drafts(legacy_config: dict[str, Any]) -> list[dict[str, Any]]:
    """把旧 schema 机器人转换成新版配置草稿，可直接作为导入时的初始值。

    为每个启用场景准备同样的 ``selected_commands`` 条目并保留 secret，不含稳定 id。
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
