"""QQ 官方机器人 API 客户端封装

- access_token 自动获取与缓存
- 指令面板相关接口: list / create / update / delete
"""

from __future__ import annotations

import time
from typing import Any

import aiohttp

QQ_API_BASE = "https://api.bot.qq.com"
DEFAULT_TOKEN_TTL = 600  # 提前 10 分钟刷新


class QQClient:
    """QQ 官方机器人 API 异步客户端。"""

    def __init__(
        self,
        appid: str,
        secret: str,
        http: aiohttp.ClientSession,
        token_ttl: int = DEFAULT_TOKEN_TTL,
    ):
        self.appid = appid
        self.secret = secret
        self._http = http
        self._token: str | None = None
        self._token_expire_at: float = 0.0
        self._token_ttl = token_ttl

    async def _ensure_token(self) -> str:
        """获取 / 刷新 access_token，带内存缓存。"""
        now = time.time()
        if self._token and self._token_expire_at > now:
            return self._token

        url = "https://bots.qq.com/app/getAppAccessToken"
        json_body = {"appId": self.appid, "clientSecret": self.secret}
        try:
            async with self._http.post(url, json=json_body) as resp:
                if resp.status >= 400:
                    text = await resp.text()
                    raise RuntimeError(f"获取 access_token HTTP {resp.status}: {text}")
                data = await resp.json()
        except Exception:
            # 拉取失败时清掉旧 token, 下次重新尝试
            self._token = None
            self._token_expire_at = 0.0
            raise

        token = data.get("access_token")
        expires_in = int(data.get("expires_in", 7200))
        if not token:
            self._token = None
            self._token_expire_at = 0.0
            raise RuntimeError(f"获取 access_token 失败: {data}")
        self._token = token
        self._token_expire_at = now + expires_in - self._token_ttl
        return token

    async def request(
        self,
        method: str,
        path: str,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """通用 QQ API 请求。"""
        token = await self._ensure_token()
        headers = {
            "Authorization": f"QQBot {token}",
            "Content-Type": "application/json; charset=utf-8",
        }
        url = f"{QQ_API_BASE}{path}"
        async with self._http.request(method, url, headers=headers, json=json_body) as resp:
            text = await resp.text()
            try:
                data: dict[str, Any] = await resp.json()
            except Exception:
                data = {"raw": text}
            if resp.status >= 400:
                raise RuntimeError(f"QQ API {method} {path} 失败 [{resp.status}]: {data}")
            return data

    # ------------------------------------------------------------------
    # 指令面板 API 封装
    # ------------------------------------------------------------------

    async def list_panels(self) -> list[dict[str, Any]]:
        """查询指令面板列表。"""
        data = await self.request("GET", "/v2/panels")
        panels = data.get("panels", []) if isinstance(data, dict) else []
        return list(panels)

    async def create_panel(
        self,
        scope: str,
        items: list[dict[str, Any]],
        target_type: str = "all",
        target_openids: list[str] | None = None,
        remark: str = "",
    ) -> str:
        """创建指令面板，返回 panel_id。"""
        body: dict[str, Any] = {
            "scope": scope,
            "target_type": target_type,
            "panel": {
                "items": items,
                "remark": remark[:255],
            },
        }
        if target_type == "specific":
            if scope == "c2c":
                body["user_openids"] = target_openids or []
            elif scope == "group":
                body["group_openids"] = target_openids or []
        data = await self.request("POST", "/v2/panels", json_body=body)
        panel_id = data.get("panel_id") if isinstance(data, dict) else None
        if not panel_id:
            raise RuntimeError(f"创建面板失败，未返回 panel_id: {data}")
        return str(panel_id)

    async def update_panel(
        self,
        panel_id: str,
        items: list[dict[str, Any]],
        remark: str = "",
    ) -> None:
        """修改指令面板内容。"""
        body = {
            "panel": {
                "items": items,
                "remark": remark[:255],
            }
        }
        await self.request("PUT", f"/v2/panels/{panel_id}", json_body=body)

    async def delete_panel(self, panel_id: str) -> None:
        """删除指令面板。"""
        await self.request("DELETE", f"/v2/panels/{panel_id}")


__all__ = ["DEFAULT_TOKEN_TTL", "QQ_API_BASE", "QQClient"]
