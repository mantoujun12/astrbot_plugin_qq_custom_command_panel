"""core.qq_client.QQClient 的单元测试 (注入 FakeSession, 无真实网络)"""

from __future__ import annotations

import pytest

from core.qq_client import QQ_API_BASE, QQClient
from tests.fakes import FakeSession


def make_client(session: FakeSession) -> QQClient:
    return QQClient(appid="app1", secret="sec1", http=session)


TOKEN_URL = "https://bots.qq.com/app/getAppAccessToken"


# ---------------------------------------------------------------------------
# access_token 获取与缓存
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_token_fetched_and_cached() -> None:
    session = FakeSession()
    session.route_token({"access_token": "tok1", "expires_in": 7200})
    client = make_client(session)

    token1 = await client._ensure_token()
    token2 = await client._ensure_token()

    assert token1 == "tok1"
    assert token2 == "tok1"
    # 只请求了一次 token 端点
    token_calls = [r for r in session.requests if r["url"] == TOKEN_URL]
    assert len(token_calls) == 1


@pytest.mark.asyncio
async def test_token_expires_and_refetches() -> None:
    session = FakeSession()
    session.route_token({"access_token": "tok1", "expires_in": 7200})
    client = make_client(session)

    await client._ensure_token()
    # 模拟过期: token 过期时间回到过去
    client._token_expire_at = 0.0
    await client._ensure_token()

    token_calls = [r for r in session.requests if r["url"] == TOKEN_URL]
    assert len(token_calls) == 2


@pytest.mark.asyncio
async def test_token_http_error_raises_and_clears_cache() -> None:
    session = FakeSession()
    session.route_token({"message": "bad"}, status=500)
    client = make_client(session)

    with pytest.raises(RuntimeError, match="500"):
        await client._ensure_token()

    assert client._token is None


@pytest.mark.asyncio
async def test_token_missing_in_response_raises() -> None:
    session = FakeSession()
    session.route_token({"expires_in": 7200})  # 无 access_token
    client = make_client(session)

    with pytest.raises(RuntimeError, match="access_token"):
        await client._ensure_token()


# ---------------------------------------------------------------------------
# request: 鉴权头 / 错误处理
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_request_sends_auth_header() -> None:
    session = FakeSession()
    session.route_token({"access_token": "tok9", "expires_in": 7200})
    session.route_panels("GET", "/v2/panels", payload={"records": []})
    client = make_client(session)

    await client.request("GET", "/v2/panels", params={"scope": "c2c"})

    panel_calls = [r for r in session.requests if r["url"] == f"{QQ_API_BASE}/v2/panels"]
    assert len(panel_calls) == 1
    headers = panel_calls[0]["kwargs"]["headers"]
    assert headers["Authorization"] == "QQBot tok9"


@pytest.mark.asyncio
async def test_request_http_error_raises_runtime_error() -> None:
    session = FakeSession()
    session.route_token({"access_token": "tok1", "expires_in": 7200})
    session.route_panels("GET", "/v2/panels", status=400, payload={"code": 40030011})
    client = make_client(session)

    with pytest.raises(RuntimeError, match="400"):
        await client.request("GET", "/v2/panels", params={"scope": "c2c"})


@pytest.mark.asyncio
async def test_request_non_json_response_wraps_raw() -> None:
    session = FakeSession()
    session.route_token({"access_token": "tok1", "expires_in": 7200})
    session.route_panels(
        "GET",
        "/v2/panels",
        status=200,
        text="<html>oops</html>",
        json_error=ValueError("no json"),
    )
    client = make_client(session)

    data = await client.request("GET", "/v2/panels")
    assert data == {"raw": "<html>oops</html>"}


# ---------------------------------------------------------------------------
# list_panels / create_panel / get_panel / update_panel / delete_panel
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_panels_backfills_scope() -> None:
    session = FakeSession()
    session.route_token({"access_token": "tok1", "expires_in": 7200})
    session.route_panels(
        "GET",
        "/v2/panels",
        payload={"records": [{"panel_id": "p1"}, {"panel_id": "p2", "scope": "other"}]},
    )
    client = make_client(session)

    records = await client.list_panels("c2c")

    assert records[0]["scope"] == "c2c"  # 缺失的 scope 被回填
    assert records[1]["scope"] == "other"  # 已有 scope 不覆盖
    # scope 参数必须带上 (QQ API 约定)
    panel_calls = [r for r in session.requests if "/v2/panels" in r["url"]]
    assert panel_calls[0]["kwargs"]["params"] == {"scope": "c2c"}


@pytest.mark.asyncio
async def test_create_panel_returns_id() -> None:
    session = FakeSession()
    session.route_token({"access_token": "tok1", "expires_in": 7200})
    session.route_panels("POST", "/v2/panels", payload={"panel_id": "p_new"})
    client = make_client(session)

    panel_id = await client.create_panel(
        scope="group",
        items=[{"name": "a", "type": "command", "desc": "b"}],
        remark="remark",
    )
    assert panel_id == "p_new"

    body = session.requests[-1]["kwargs"]["json"]
    assert body["scope"] == "group"
    assert body["target_type"] == "all"
    assert body["panel"]["remark"] == "remark"


@pytest.mark.asyncio
async def test_create_panel_no_id_raises() -> None:
    session = FakeSession()
    session.route_token({"access_token": "tok1", "expires_in": 7200})
    session.route_panels("POST", "/v2/panels", payload={})
    client = make_client(session)

    with pytest.raises(RuntimeError, match="panel_id"):
        await client.create_panel(scope="group", items=[])


@pytest.mark.asyncio
async def test_create_panel_remark_truncated() -> None:
    session = FakeSession()
    session.route_token({"access_token": "tok1", "expires_in": 7200})
    session.route_panels("POST", "/v2/panels", payload={"panel_id": "p"})
    client = make_client(session)

    await client.create_panel(scope="c2c", items=[], remark="r" * 400)

    body = session.requests[-1]["kwargs"]["json"]
    assert len(body["panel"]["remark"]) == 255


@pytest.mark.asyncio
async def test_get_panel_returns_detail() -> None:
    session = FakeSession()
    session.route_token({"access_token": "tok1", "expires_in": 7200})
    session.route_panels(
        "GET",
        "/v2/panels/p1",
        payload={"panel_id": "p1", "scope": "group"},
    )
    client = make_client(session)

    detail = await client.get_panel("p1")
    assert detail["panel_id"] == "p1"
    assert detail["scope"] == "group"


@pytest.mark.asyncio
async def test_update_panel_items_only() -> None:
    session = FakeSession()
    session.route_token({"access_token": "tok1", "expires_in": 7200})
    session.route_panels("PUT", "/v2/panels/p1", payload={})
    client = make_client(session)

    await client.update_panel("p1", items=[{"name": "x"}], remark="r")

    body = session.requests[-1]["kwargs"]["json"]
    assert body == {"panel": {"items": [{"name": "x"}], "remark": "r"}}
    assert "target_type" not in body


@pytest.mark.asyncio
async def test_update_panel_specific_c2c_maps_user_openids() -> None:
    session = FakeSession()
    session.route_token({"access_token": "tok1", "expires_in": 7200})
    # specific 需要先查详情拿 scope
    session.route_panels("GET", "/v2/panels/p1", payload={"panel_id": "p1", "scope": "c2c"})
    session.route_panels("PUT", "/v2/panels/p1", payload={})
    client = make_client(session)

    await client.update_panel(
        "p1",
        target_type="specific",
        target_openids=["u1", "u2"],
    )

    put_body = session.requests[-1]["kwargs"]["json"]
    assert put_body["target_type"] == "specific"
    assert put_body["user_openids"] == ["u1", "u2"]


@pytest.mark.asyncio
async def test_update_panel_specific_group_maps_group_openids() -> None:
    session = FakeSession()
    session.route_token({"access_token": "tok1", "expires_in": 7200})
    session.route_panels("GET", "/v2/panels/p1", payload={"panel_id": "p1", "scope": "group"})
    session.route_panels("PUT", "/v2/panels/p1", payload={})
    client = make_client(session)

    await client.update_panel("p1", target_type="specific", target_openids=["g1"])

    put_body = session.requests[-1]["kwargs"]["json"]
    assert put_body["group_openids"] == ["g1"]


@pytest.mark.asyncio
async def test_update_panel_specific_channel_maps_channel_openids() -> None:
    session = FakeSession()
    session.route_token({"access_token": "tok1", "expires_in": 7200})
    session.route_panels("GET", "/v2/panels/p1", payload={"panel_id": "p1", "scope": "channel"})
    session.route_panels("PUT", "/v2/panels/p1", payload={})
    client = make_client(session)

    await client.update_panel("p1", target_type="specific", target_openids=["ch1"])

    put_body = session.requests[-1]["kwargs"]["json"]
    assert put_body["channel_openids"] == ["ch1"]


@pytest.mark.asyncio
async def test_update_panel_specific_unknown_scope_raises() -> None:
    session = FakeSession()
    session.route_token({"access_token": "tok1", "expires_in": 7200})
    session.route_panels("GET", "/v2/panels/p1", payload={"panel_id": "p1", "scope": "weird"})
    client = make_client(session)

    with pytest.raises(RuntimeError, match="weird"):
        await client.update_panel("p1", target_type="specific", target_openids=["u1"])


@pytest.mark.asyncio
async def test_update_panel_specific_requires_openids() -> None:
    session = FakeSession()
    session.route_token({"access_token": "tok1", "expires_in": 7200})
    client = make_client(session)

    with pytest.raises(ValueError, match="target_openids"):
        await client.update_panel("p1", target_type="specific")


@pytest.mark.asyncio
async def test_delete_panel_sends_delete() -> None:
    session = FakeSession()
    session.route_token({"access_token": "tok1", "expires_in": 7200})
    session.route_panels("DELETE", "/v2/panels/p1", payload={})
    client = make_client(session)

    await client.delete_panel("p1")

    assert session.requests[-1]["method"] == "DELETE"
    assert session.requests[-1]["url"] == f"{QQ_API_BASE}/v2/panels/p1"
