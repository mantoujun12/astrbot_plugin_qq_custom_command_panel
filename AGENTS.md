#### 项目简介

QQ 官方机器人指令面板内容自定义插件。在 AstrBot WebUI 中配置要展示的指令条目，插件会把它们写入 QQ 官方机器人的指令面板，用户在 QQ 输入 `/` 即可看到面板内容。

#### 技术栈

- Python 3.10+（代码里有 X | None、from __future__ import annotations）
- aiohttp(HTTP 客户端，10s 超时)
- AstrBot Star 插件体系(@register / @filter.command / Context / AstrBotConfig)
- 插件视图前端：Vue 3 + TypeScript + Vite + Vuetify 4 + vue-router(hash)，源码在 `web/dashboard/`，构建产物提交在 `pages/dashboard/`
- 无第三方数据库，本地状态存 AstrBot 的 `data/plugin_data/astrbot_plugin_qq_custom_command_panel/`

#### 开发命令

插件通过 AstrBot 加载，功能性测试仍需要在运行的 AstrBot 实例下进行；
业务逻辑可跑离线 pytest 套件（无需安装 AstrBot，tests/conftest.py 会注入 astrbot stub）。

安装运行 + 开发依赖：

`pip install -r requirements.txt -r requirements-dev.txt`

运行离线测试：

`pytest -q`

规范性检查建议使用 Ruff 修复和格式化：

`ruff check . --fix`

`ruff format --check .`

或安装 pre-commit 后跑同一套 hooks(与 pre-commit.ci / CI 一致)：

`pre-commit run --all-files`

插件视图前端（在 `web/dashboard/` 下）：

`pnpm install` / `pnpm dev` / `pnpm build`

`pnpm build` 会先跑 `vue-tsc` 类型检查，产物直接写入仓库根目录的 `pages/dashboard/`（见 `vite.config.ts` 的 `build.outDir`），不需要手工拷贝，产物需要一起提交。

#### 架构约定

1. QQ API GET /v2/panels 必须带 scope 参数
2. 面板同步中任一场景拉取失败要中止，不许吞异常（否则会重复创建面板）
3. PanelSyncer 通过 build_clients / list_all_panels 等公开方法暴露能力；外部禁止直接访问 _ 前缀私有方法
4. 配置解析逻辑整合到 core/config.py 的 helper 函数(get_platforms_from_schema / get_platforms_from_context / get_configured_platforms)，不要散落在 main.py
5. 指令用 @filter.command 注册，描述取 handler docstring 第一行（除非显式传 description）
6. 异步一律 async/await，不用回调风格
7. 日志统一 from astrbot.api import logger，前缀 [qq-command-panel]

#### 插件视图 (web/dashboard)

1. 视图必须保留 `base: './'` 与 hash 路由。宿主按真实文件路径下发资源（带令牌前缀），绝对路径 `/assets/...` 会 404，history 路由刷新也会 404。
2. 数据访问集中在 `src/api/` 并通过 bridge(`window.AstrBotPluginView`)调后端；本地 dev 没有 bridge 时退回 mock(`src/api/mock.ts`)，且必须在页面上标注，不许把假数据伪装成真实状态。
3. 文案走 `bridge.t(key, fallback)`，key 写在 `.astrbot-plugin/i18n/<locale>.json` 的 `views.<view>.*`。产物**不含**翻译，只编译进 fallback 文案；所以改文案只需改 JSON + 重载插件，不用重新 build，但 key 和 fallback 要成对维护。
4. 主题与配色跟随宿主：用 bridge context 的 `isDark` 切 `<v-app :theme>`，色值抄宿主 `dashboard/src/theme/*.ts`。插件视图跑在 iframe 里，宿主的 `--v-theme-*` 不会继承进来。
5. iframe 是 sandbox 的（没有 `allow-same-origin`），禁止访问 `localStorage` / cookies / 父页面 DOM；需要持久化的状态放后端。
6. 不做 SCSS 定制层。只有宿主靠 SCSS 才拿得到的值（如卡片 16px 圆角），在 `src/styles/dashboard.css` 里直接写数值。
7. 产物文件名不带内容哈希（宿主对所有视图资源都返回 `Cache-Control: no-store`），且产物视为生成文件 —— 冲突时重新 `pnpm build`，不要手工合并（见 `.gitattributes`）。
8. 后端接口用 `context.register_web_api()` + `astrbot.api.web`(json_response / error_response / stream_response / request)，不要把 FastAPI/Quart 的原始请求对象暴露给业务代码。

#### 代码风格

要点：类型注解齐全、from __future__ import annotations、Path 而非字符串拼路径、__all__ 导出公开 API。

#### 提交规范

要点：Conventional Commits + 单一职责。

格式：feat: / fix: / refactor: / chore: / docs:
一个 commit/PR 只做一件事
英文 message
分支名 feat/xxx / fix/xxx
