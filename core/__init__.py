"""初始化插件"""

from .config import (
    DEFAULT_SCENES,
    PANEL_ITEM_DESC_MAX,
    PANEL_ITEM_NAME_MAX,
    PANEL_MAX_ITEMS,
    SCENES,
    get_configured_platforms,
    get_enabled_scenes,
    get_platforms_from_context,
    get_platforms_from_schema,
    get_selected_commands,
)
from .i18n import (
    DEFAULT_LANGUAGE,
    LOG_TAG,
    SUPPORTED_LANGUAGES,
    Translator,
    get_instance,
    initialize,
    t,
)
from .panel_syncer import PanelSyncer, ProgressCallback
from .paths import PLUGIN_NAME, PLUGIN_VERSION, resolve_plugin_data_dir
from .qq_client import QQClient
from .state import STATE_FILENAME, PanelStateStore
from .web_api import (
    STATUS_ROUTE_SUFFIX,
    build_status,
    mask_appid,
    panel_items_count,
    register_status_api,
)

__all__ = [
    "DEFAULT_LANGUAGE",
    "DEFAULT_SCENES",
    "LOG_TAG",
    "PANEL_ITEM_DESC_MAX",
    "PANEL_ITEM_NAME_MAX",
    "PANEL_MAX_ITEMS",
    "PLUGIN_NAME",
    "PLUGIN_VERSION",
    "SCENES",
    "STATE_FILENAME",
    "STATUS_ROUTE_SUFFIX",
    "SUPPORTED_LANGUAGES",
    "PanelStateStore",
    "PanelSyncer",
    "ProgressCallback",
    "QQClient",
    "Translator",
    "build_status",
    "get_configured_platforms",
    "get_enabled_scenes",
    "get_instance",
    "get_platforms_from_context",
    "get_platforms_from_schema",
    "get_selected_commands",
    "initialize",
    "mask_appid",
    "panel_items_count",
    "register_status_api",
    "resolve_plugin_data_dir",
    "t",
]
