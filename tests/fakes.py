"""测试通用假件 (fakes): FakeQQClient / FakeSession

只实现被测代码实际调用的方法，未实现的方法调用会直接 AttributeError，
避免 fakes 默默偏离真实接口。
"""

from __future__ import annotations

from typing import Any

from core.qq_client import DEFAULT_TOKEN_TTL, QQ_API_BASE


class FakeResponse:
    """假 aiohttp.Response: 预置 status / json / text"""

    def __init__(
        self,
        *,
        status: int = 200,
        payload: dict[str, Any] | None = None,
        text: str = "",
        json_error: Exception | None = None,
    ) -> None:
        self.status = status
        self._payload = payload if payload is not None else {}
        self._text = text
        self._json_error = json_error

    async def json(self) -> dict[str, Any]:
        if self._json_error is not None:
            raise self._json_error
        return self._payload

    async def text(self) -> str:
        return self._text

    async def __aenter__(self) -> FakeResponse:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None


class FakeSession:
    """假 aiohttp.ClientSession: 按 (method, url) 路由返回预置响应

    - 记录所有请求 (method, url, kwargs)，供断言
    - 未匹配到路由时返回 500 + {"raw": ...}，不抛异常，
      与真实 aiohttp 行为对齐（HTTP 错误也是正常响应）
    """

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.routes: dict[tuple[str, str], FakeResponse] = {}

    def route(
        self,
        method: str,
        url: str,
        response: FakeResponse,
    ) -> None:
        self.routes[(method.upper(), url)] = response

    def _match(self, method: str, url: str) -> FakeResponse:
        return self.routes.get(
            (method.upper(), url),
            FakeResponse(status=500, payload={"raw": "no route"}, text="no route"),
        )

    def request(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> FakeResponse:
        """与真实 aiohttp 对齐：同步返回 async context manager，由调用方 `async with`"""
        self.requests.append({"method": method, "url": url, "kwargs": kwargs})
        return self._match(method, url)

    def post(
        self,
        url: str,
        **kwargs: Any,
    ) -> FakeResponse:
        """与真实 aiohttp 对齐：同步返回 async context manager，由调用方 `async with`"""
        self.requests.append({"method": "POST", "url": url, "kwargs": kwargs})
        return self._match("POST", url)

    def closed(self) -> bool:
        return False

    # ---- 便捷构造器：面板 API 路由 ----

    def route_token(self, payload: dict[str, Any], status: int = 200) -> None:
        self.route(
            "POST",
            "https://bots.qq.com/app/getAppAccessToken",
            FakeResponse(status=status, payload=payload),
        )

    def route_panels(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        status: int = 200,
        text: str = "",
        json_error: Exception | None = None,
    ) -> None:
        self.route(
            method,
            f"{QQ_API_BASE}{path}",
            FakeResponse(
                status=status,
                payload=payload,
                text=text,
                json_error=json_error,
            ),
        )


class FakeQQClient:
    """假 QQClient: 可编程各场景 list_panels 成败，记录写操作

    用作 PanelSyncer.sync_for_platform / clear_for_platform 的 client 参数，
    覆盖 AGENTS.md 中 "任一场景拉取失败要中止" 等关键约定的测试。
    """

    def __init__(
        self,
        *,
        existing: dict[str, list[dict[str, Any]]] | None = None,
        failing_scopes: set[str] | None = None,
        platform_label: str = "qq_official",
    ) -> None:
        self.platform_label = platform_label
        self.failing_scopes = failing_scopes or set()
        # scope -> 面板列表（seed 数据，create/delete/update 会修改它）
        self._panels: dict[str, list[dict[str, Any]]] = existing or {}
        # 记录所有写操作
        self.created: list[tuple[str, list[dict[str, Any]]]] = []
        self.updated: list[tuple[str, list[dict[str, Any]]]] = []
        self.deleted: list[str] = []
        self._next_id = 1000

    # ---- 读操作 ----

    async def list_panels(self, scope: str) -> list[dict[str, Any]]:
        if scope in self.failing_scopes:
            raise RuntimeError(f"list {scope} failed")
        return list(self._panels.get(scope, []))

    # ---- 写操作 ----

    async def create_panel(
        self,
        scope: str,
        items: list[dict[str, Any]],
        target_type: str = "all",
        target_openids: list[str] | None = None,
        remark: str = "",
    ) -> str:
        self._next_id += 1
        panel_id = f"panel_new_{self._next_id}"
        self.created.append((scope, list(items)))
        self._panels.setdefault(scope, []).append(
            {
                "panel_id": panel_id,
                "scope": scope,
                "panel": {"items": list(items), "remark": remark},
            }
        )
        return panel_id

    async def update_panel(
        self,
        panel_id: str,
        items: list[dict[str, Any]] | None = None,
        remark: str = "",
        *,
        target_type: str | None = None,
        target_openids: list[str] | None = None,
    ) -> None:
        self.updated.append((panel_id, list(items or [])))
        for panels in self._panels.values():
            for p in panels:
                if p.get("panel_id") == panel_id:
                    inner = p.setdefault("panel", {})
                    if items is not None:
                        inner["items"] = list(items)
                    inner["remark"] = remark

    async def delete_panel(self, panel_id: str) -> None:
        self.deleted.append(str(panel_id))
        for scope, panels in self._panels.items():
            self._panels[scope] = [p for p in panels if p.get("panel_id") != panel_id]

    # ---- 断言辅助 ----

    def panels_in(self, scope: str) -> list[dict[str, Any]]:
        return self._panels.get(scope, [])


__all__ = [
    "DEFAULT_TOKEN_TTL",
    "FakeQQClient",
    "FakeResponse",
    "FakeSession",
]
