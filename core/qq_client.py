"""QQ 官方机器人 API 客户端封装

- access_token 自动获取与缓存
- 指令面板相关接口: list / create / update / delete
"""

from __future__ import annotations

import time
from typing import Any

import aiohttp

from .i18n import t

QQ_API_BASE = "https://api.bot.qq.com"
DEFAULT_TOKEN_TTL = 600  # 提前 10 分钟刷新


class QQClient:
    """QQ 官方机器人 API 异步客户端"""

    def __init__(
        self,
        appid: str,
        secret: str,
        http: aiohttp.ClientSession,
        token_ttl: int = DEFAULT_TOKEN_TTL,
        platform_label: str = "qq",
    ):
        self.appid = appid
        self.secret = secret
        self._http = http
        self._token: str | None = None
        self._token_expire_at: float = 0.0
        self._token_ttl = token_ttl
        # 平台标签 (qq_official / qq_official_webhook), 仅用于日志和调试展示
        self.platform_label = platform_label

    async def _ensure_token(self) -> str:
        """获取 / 刷新 access_token, 带内存缓存"""
        now = time.time()
        if self._token and self._token_expire_at > now:
            return self._token

        url = "https://bots.qq.com/app/getAppAccessToken"
        json_body = {"appId": self.appid, "clientSecret": self.secret}
        try:
            async with self._http.post(url, json=json_body) as resp:
                if resp.status >= 400:
                    text = await resp.text()
                    raise RuntimeError(t("qq.get_token_http_error", status=resp.status, text=text))
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
            raise RuntimeError(t("qq.get_token_failed", data=data))
        self._token = token
        self._token_expire_at = now + expires_in - self._token_ttl
        return token

    async def request(
        self,
        method: str,
        path: str,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """通用 QQ API 请求"""
        token = await self._ensure_token()
        headers = {
            "Authorization": f"QQBot {token}",
            "Content-Type": "application/json; charset=utf-8",
        }
        url = f"{QQ_API_BASE}{path}"
        async with self._http.request(
            method, url, headers=headers, params=params, json=json_body
        ) as resp:
            text = await resp.text()
            try:
                data: dict[str, Any] = await resp.json()
            except Exception:
                data = {"raw": text}
            if resp.status >= 400:
                raise RuntimeError(
                    t(
                        "qq.api_failed",
                        method=method,
                        path=path,
                        status=resp.status,
                        data=data,
                    )
                )
            return data

    # ------------------------------------------------------------------
    # 指令面板 API 封装
    # ------------------------------------------------------------------

    async def list_panels(self, scope: str) -> list[dict[str, Any]]:
        """查询指定场景的指令面板列表

        QQ API 要求 GET /v2/panels 必须带 scope 参数 (c2c/group/channel/dm),
        否则会返回 40030011 生效场景不合法。
        返回原始 records 列表 (每个元素带有 panel.scope 字段)。
        """
        data = await self.request("GET", "/v2/panels", params={"scope": scope})
        records = data.get("records", []) if isinstance(data, dict) else []
        # 把 scope 回填到每个 record 上, 调用方合并多场景时不用关心来源
        for r in records:
            if isinstance(r, dict) and "scope" not in r:
                r["scope"] = scope
        return list(records)

    async def create_panel(
        self,
        scope: str,
        items: list[dict[str, Any]],
        target_type: str = "all",
        target_openids: list[str] | None = None,
        remark: str = "",
    ) -> str:
        """创建指令面板，返回 panel_id"""
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
            raise RuntimeError(t("qq.create_panel_no_id", data=data))
        return str(panel_id)

    async def get_panel(self, panel_id: str) -> dict[str, Any]:
        """查询单个指令面板详情

        GET /v2/panels/{panel_id}
        返回原始面板对象 (含 scope / panel_id / panel.items / panel.remark / target_type 等)。
        """
        data = await self.request("GET", f"/v2/panels/{panel_id}")
        if not isinstance(data, dict):
            raise RuntimeError(t("qq.get_panel_invalid_response", data=data))
        return data

    async def update_panel(
        self,
        panel_id: str,
        items: list[dict[str, Any]] | None = None,
        remark: str = "",
        *,
        target_type: str | None = None,
        target_openids: list[str] | None = None,
    ) -> None:
        """修改指令面板内容 (扩展版)

        新增可选 keyword-only 参数, 不传即保持原行为 100% 向后兼容:
        - items: 为 None 时不更新 items 字段 (仅改 remark / target_type)
        - target_type: "all" | "specific" | None (None 不更新)
        - target_openids: target_type=specific 时必填; 根据面板原 scope
          自动映射为 user_openids / group_openids / channel_openids
        """
        body: dict[str, Any] = {}
        panel_inner: dict[str, Any] = {}
        if items is not None:
            panel_inner["items"] = items
        if remark is not None:
            panel_inner["remark"] = remark[:255]
        if panel_inner:
            body["panel"] = panel_inner
        if target_type is not None:
            body["target_type"] = target_type
            if target_type == "specific" and target_openids is not None:
                # specific 场景必须知道原面板 scope, 才能映射到正确的 openids 键名
                try:
                    detail = await self.get_panel(panel_id)
                except Exception as exc:
                    raise RuntimeError(
                        t("qq.update_panel_get_scope_failed", panel_id=panel_id, exc=exc)
                    ) from exc
                scope = detail.get("scope")
                if scope == "c2c" or scope == "dm":
                    body["user_openids"] = list(target_openids)
                elif scope == "group":
                    body["group_openids"] = list(target_openids)
                elif scope == "channel":
                    body["channel_openids"] = list(target_openids)
                else:
                    raise RuntimeError(
                        t(
                            "qq.update_panel_scope_unknown",
                            panel_id=panel_id,
                            scope=scope,
                        )
                    )
        await self.request("PUT", f"/v2/panels/{panel_id}", json_body=body)

    async def delete_panel(self, panel_id: str) -> None:
        """删除指令面板"""
        await self.request("DELETE", f"/v2/panels/{panel_id}")


__all__ = ["DEFAULT_TOKEN_TTL", "QQ_API_BASE", "QQClient"]
