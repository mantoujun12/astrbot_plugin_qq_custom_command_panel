"""初始化插件"""

from .command_collector import collect_commands
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
from .panel_syncer import PanelSyncer
from .qq_client import QQClient
from .state import STATE_FILENAME, PanelStateStore

__all__ = [
    "DEFAULT_LANGUAGE",
    "DEFAULT_SCENES",
    "LOG_TAG",
    "PANEL_ITEM_DESC_MAX",
    "PANEL_ITEM_NAME_MAX",
    "PANEL_MAX_ITEMS",
    "SCENES",
    "STATE_FILENAME",
    "SUPPORTED_LANGUAGES",
    "PanelStateStore",
    "PanelSyncer",
    "QQClient",
    "Translator",
    "collect_commands",
    "get_configured_platforms",
    "get_enabled_scenes",
    "get_instance",
    "get_platforms_from_context",
    "get_platforms_from_schema",
    "get_selected_commands",
    "initialize",
    "t",
]
