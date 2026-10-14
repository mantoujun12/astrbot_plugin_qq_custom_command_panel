"""pytest 根配置：注入 astrbot stub，使插件代码无需安装 AstrBot 即可导入。

必须先于所有测试模块执行（pytest 启动时加载 conftest），因此：
1. 往 sys.modules 注入轻量假 `astrbot` 包；
2. 禁止在此文件 import 任何插件代码 (core.* / main)。

stub 只伪造代码里实际用到的最小接口面：
- astrbot.api.logger（i18n / state / panel_syncer 使用）
- astrbot.api.star.Context / Star / register（仅导入期绑定，运行时几乎不碰）
- astrbot.api.web（core/web_api.py 的响应 helper）
- astrbot.core.config.astrbot_config.AstrBotConfig（仅 main.py）

注意：main.py 使用 `from .core import ...` 相对导入，而仓库根不是包，
`import main` 会失败 — 因此本套测试不覆盖 main.py（装配层，无业务逻辑）。
"""

from __future__ import annotations

import logging
import sys
import types

_PYTEST_HOME = "pytest_home"


def _mod(name: str, **attrs: object) -> types.ModuleType:
    """创建假模块，设置属性并注册到 sys.modules"""
    mod = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(mod, key, value)
    sys.modules[name] = mod
    return mod


def _install_astrbot_stub() -> None:
    """向 sys.modules 注入轻量假 astrbot 包

    已存在真 astrbot（如在 AstrBot 宿主进程内跑 pytest）时不覆盖。
    """
    if "astrbot" in sys.modules:
        return

    # 真 logging.Logger 而非 Mock: 原生支持 exc_info，且 pytest caplog 可捕获
    logger = logging.getLogger("astrbot")

    api = _mod("astrbot.api", logger=logger)

    class Context:  # noqa: SM051 - 仅占位，被测代码只拿它当类型注解
        ...

    class Star:
        """main.py 的基类占位"""

        def __init__(self, context: object = None) -> None:
            self.context = context

    def register(*args: object, **kwargs: object):  # noqa: ANN202 - stub 装饰器
        def deco(cls):
            return cls

        return deco

    _mod(
        "astrbot.api.star",
        Context=Context,
        Star=Star,
        register=register,
    )
    # 父子属性链接，保证 `import astrbot.api.star` 与
    # `astrbot.api.star.Context` 两种写法都能工作
    api.star = sys.modules["astrbot.api.star"]

    # astrbot.api.web 占位实现：只保留 payload，供离线测试断言 handler 返回内容
    def json_response(data=None, **kwargs):  # noqa: ANN001, ANN202 - stub
        return {"__json__": True, "data": data}

    def error_response(message="", status_code=400, **kwargs):  # noqa: ANN001, ANN202 - stub
        return {"__error__": True, "message": message, "status_code": status_code}

    def stream_response(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202 - stub
        return {"__stream__": True}

    class _FakeQuery:
        """假 query 参数容器：与真实 request.query 的 get(key, default, type) 对齐"""

        # 测试可通过 request.query.set_values({...}) 注入查询参数
        values: dict = {}

        def get(self, key, default=None, **kwargs):  # noqa: ANN001, ANN003, ANN201 - stub
            return self.values.get(key, default)

        def getlist(self, key):  # noqa: ANN001, ANN201 - stub
            value = self.values.get(key)
            return list(value) if isinstance(value, list) else []

        def set_values(self, values: dict) -> None:  # noqa: ANN001 - stub
            self.values = dict(values)

    class _FakeRequest:
        query = _FakeQuery()
        # 测试可通过 request.payload = {...} 注入 JSON 请求体
        payload: object = {}

        async def json(self, default=None):  # noqa: ANN001, ANN201 - stub
            return self.payload if self.payload is not None else default

    web = _mod(
        "astrbot.api.web",
        json_response=json_response,
        error_response=error_response,
        stream_response=stream_response,
        request=_FakeRequest(),
    )
    api.web = web

    _mod("astrbot.core")
    _mod("astrbot.core.config")
    _mod(
        "astrbot.core.config.astrbot_config",
        AstrBotConfig=type("AstrBotConfig", (dict,), {}),
    )
    # 中间层属性链接，缺少会导致部分导入路径下 ModuleNotFoundError
    sys.modules["astrbot.core"].config = sys.modules["astrbot.core.config"]

    _mod("astrbot", api=api, core=sys.modules["astrbot.core"])


_install_astrbot_stub()
