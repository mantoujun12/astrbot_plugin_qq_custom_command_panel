#### 项目简介

QQ 官方机器人指令面板内容自定义插件。在 AstrBot WebUI 中配置要展示的指令条目, 插件会把它们写入 QQ 官方机器人的指令面板, 用户在 QQ 输入 `/` 即可看到面板内容。

#### 技术栈

- Python 3.10+(代码里有 X | None、from __future__ import annotations)
- aiohttp(HTTP 客户端, 10s 超时)
- AstrBot Star 插件体系(@register / @filter.command / Context / AstrBotConfig)
- 无第三方数据库,本地状态存 AstrBot 的 `data/plugin_data/astrbot_plugin_qq_custom_command_panel/`

#### 开发命令

插件通过 AstrBot 加载，功能性测试仍需要在运行的 AstrBot 实例下进行；
业务逻辑可跑离线 pytest 套件(无需安装 AstrBot，tests/conftest.py 会注入 astrbot stub)。

安装运行 + 开发依赖：

`pip install -r requirements.txt -r requirements-dev.txt`

运行离线测试：

`pytest -q`

规范性检查建议使用 Ruff 修复和格式化：

`ruff check . --fix`

`ruff format --check .`

或安装 pre-commit 后跑同一套 hooks(与 pre-commit.ci / CI 一致)：

`pre-commit run --all-files`

#### 架构约定

1. QQ API GET /v2/panels 必须带 scope 参数
2. 面板同步中任一场景拉取失败要中止, 不许吞异常(否则会重复创建面板)
3. PanelSyncer 通过 build_clients / list_all_panels 等公开方法暴露能力; 外部禁止直接访问 _ 前缀私有方法
4. 配置解析逻辑整合到 core/config.py 的 helper 函数(get_platforms_from_schema / get_platforms_from_context / get_configured_platforms), 不要散落在 main.py
5. 指令用 @filter.command 注册, 描述取 handler docstring 第一行(除非显式传 description)
6. 异步一律 async/await, 不用回调风格
7. 日志统一 from astrbot.api import logger, 前缀 [qq-command-panel]

#### 代码风格

要点: 类型注解齐全、from __future__ import annotations、Path 而非字符串拼路径、__all__ 导出公开 API。

#### 提交规范

要点: Conventional Commits + 单一职责。

格式: feat: / fix: / refactor: / chore: / docs:
一个 commit/PR 只做一件事
英文 message
分支名 feat/xxx / fix/xxx
