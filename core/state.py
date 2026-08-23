"""面板状态持久化

将 panel_id 映射存到 AstrBot 的 data_dir 下，符合
"AstrBot 插件开发原则" 中 "持久化数据请存储于 data 目录下" 的要求

存储格式 (YAML):
    pf_id_1:
      c2c: panel_xxx
      group: panel_yyy
    pf_id_2:
      channel: panel_zzz
"""

from __future__ import annotations

from pathlib import Path

import yaml
from astrbot.api import logger

STATE_FILENAME = "panel_state.yaml"


class PanelStateStore:
    """panel_id 持久化存储。"""

    def __init__(self, data_dir: Path | str):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.data_dir / STATE_FILENAME

    def load(self) -> dict[str, dict[str, str]]:
        """加载持久化的 {pf_id: {scope: panel_id}} 映射。"""
        if not self.state_file.exists():
            return {}
        try:
            with self.state_file.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            if not isinstance(data, dict):
                return {}
            # 兜底：保证内部结构是 dict[str, dict[str, str]]
            normalized: dict[str, dict[str, str]] = {}
            for k, v in data.items():
                if isinstance(v, dict):
                    normalized[str(k)] = {str(sk): str(sv) for sk, sv in v.items() if sv}
            return normalized
        except Exception as exc:
            logger.warning(f"[qq-command-panel] 读取面板状态失败: {exc}")
            return {}

    def save(self, state: dict[str, dict[str, str]]) -> None:
        """原子写入 panel_id 映射。"""
        tmp_file = self.state_file.with_suffix(".yaml.tmp")
        try:
            with tmp_file.open("w", encoding="utf-8") as f:
                yaml.safe_dump(state, f, allow_unicode=True, sort_keys=False)
            tmp_file.replace(self.state_file)
        except Exception as exc:
            logger.error(f"[qq-command-panel] 保存面板状态失败: {exc}")
            # 清理临时文件
            try:
                if tmp_file.exists():
                    tmp_file.unlink()
            except Exception as cleanup_exc:
                logger.debug(f"[qq-command-panel] 清理临时文件失败: {cleanup_exc}")

    def clear(self) -> None:
        """删除持久化文件。"""
        try:
            if self.state_file.exists():
                self.state_file.unlink()
        except Exception as exc:
            logger.warning(f"[qq-command-panel] 清理面板状态失败: {exc}")


__all__ = ["STATE_FILENAME", "PanelStateStore"]
