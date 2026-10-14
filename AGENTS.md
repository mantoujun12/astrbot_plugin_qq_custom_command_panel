#### 项目简介

QQ 官方机器人指令面板内容自定义插件。在 AstrBot WebUI 中配置要展示的指令条目，插件会把它们写入 QQ 官方机器人的指令面板，用户在 QQ 输入 `/` 即可看到面板内容。

#### 技术栈

- Python 3.10+（代码里有 X | None、from __future__ import annotations）
- aiohttp(HTTP 客户端，10s 超时)
- AstrBot Star 插件体系(@register / @filter.command / Context / AstrBotConfig)
- 插件视图前端：Vue 3 + TypeScript + Vite + Vuetify 4 + vue-router(hash) + Vitest，源码在 `web/dashboard/`，构建产物提交在 `pages/dashboard/`
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

`pnpm install` / `pnpm dev` / `pnpm build` / `pnpm test` / `pnpm test:coverage` / `pnpm test:report` / `pnpm test:codecov`

`pnpm build` 会先跑 `vue-tsc` 类型检查，产物直接写入仓库根目录的 `pages/dashboard/`（见 `vite.config.ts` 的 `build.outDir`），不需要手工拷贝，产物需要一起提交。

`pnpm test` 跑 vitest 单元测试（配置见 `vitest.config.ts`，测试文件与被测代码同目录、命名 `*.test.ts`）；`pnpm test:codecov` 是 CI 用的入口，一次产出 `coverage/lcov.info` 与 `test-report.junit.xml`，由 `.github/workflows/codecov-dashboard.yml` 分两次以 flag `dashboard` 上传 Codecov（覆盖率 + Test Analytics）。Python 侧对应 `.github/workflows/codecov-core.yml`，flag 为 `unittests`。

#### 架构约定

1. QQ API GET /v2/panels 必须带 scope 参数
2. 面板同步中任一场景拉取失败要中止，不许吞异常（否则会重复创建面板）
3. PanelSyncer 通过 build_clients / list_all_panels 等公开方法暴露能力；外部禁止直接访问 _ 前缀私有方法
4. 配置解析逻辑整合到 core/config.py 的 helper 函数(get_platforms_from_schema / get_configured_platforms / export_config / normalize_config_payload)，不要散落在 main.py
5. 指令用 @filter.command 注册，描述取 handler docstring 第一行（除非显式传 description）
6. 异步一律 async/await，不用回调风格
7. 日志统一 from astrbot.api import logger，前缀 [qq-command-panel]
8. 平台凭证只来自插件自己的 `qq_platforms`：AstrBot 不向插件暴露平台适配器的机器人信息，禁止再写从 context 回退读取 appid / clientSecret 的逻辑
9. 面板同步的结构化进度走 `PanelSyncer.sync_all(on_event=...)`，后台任务与事件缓冲由 `core/sync_runner.py` 的 `SyncRunner` 负责；同一时间只允许一个同步任务

#### 插件视图 (web/dashboard)

1. 视图必须保留 `base: './'` 与 hash 路由。宿主按真实文件路径下发资源（带令牌前缀），绝对路径 `/assets/...` 会 404，history 路由刷新也会 404。
2. 数据访问集中在 `src/api/` 并通过 bridge(`window.AstrBotPluginView`)调后端；本地 dev 没有 bridge 时退回 mock(`src/api/mock.ts`)，且必须在页面上标注，不许把假数据伪装成真实状态。
3. 文案走 `bridge.t(key, fallback)`，key 写在 `.astrbot-plugin/i18n/<locale>.json` 的 `pages.<view>.*`（宿主按 `pages.<目录名>.title` 取视图标题，写成 `views` 会让标题回退成目录名）。产物**不含**翻译，只编译进 fallback 文案；所以改文案只需改 JSON + 重载插件，不用重新 build，但 key 和 fallback 要成对维护。
4. 主题与配色跟随宿主：用 bridge context 的 `isDark` 切 `<v-app :theme>`，色值抄宿主 `dashboard/src/theme/*.ts`。插件视图跑在 iframe 里，宿主的 `--v-theme-*` 不会继承进来。
5. iframe 是 sandbox 的（没有 `allow-same-origin`），禁止访问 `localStorage` / cookies / 父页面 DOM；需要持久化的状态放后端。
6. 不做 SCSS 定制层。只有宿主靠 SCSS 才拿得到的值（如卡片 16px 圆角），在 `src/styles/dashboard.css` 里直接写数值。
7. 产物文件名不带内容哈希（宿主对所有视图资源都返回 `Cache-Control: no-store`），且产物视为生成文件 —— 冲突时重新 `pnpm build`，不要手工合并（见 `.gitattributes`）。
8. 后端接口用 `context.register_web_api()` + `astrbot.api.web`(json_response / error_response / stream_response / request)，不要把 FastAPI/Quart 的原始请求对象暴露给业务代码。
9. 视图接口固定为 `status`(GET) / `config`(GET+POST) / `sync`(POST) / `sync/events`(GET, SSE)，统一在 `core/web_api.py` 的 `WebApiBundle` 里注册，路径前缀是插件名。
10. 写回配置只走 `POST config` → `AstrBotConfig.update()` + `save_config_async()`；`GET config` 只回 secret 掩码，明文 secret 不允许出现在响应、日志或前端里，前端提交时留空表示沿用原值。
11. 同步进度用 SSE：后端从 `SyncRunner.stream(since)` 产事件（`data: {...}\n\n`），前端用 `bridge.subscribeSSE` 订阅、收到 `finish` 后自行退订；宿主不会通知流被关闭。

#### 代码风格

要点：类型注解齐全、from __future__ import annotations、Path 而非字符串拼路径、__all__ 导出公开 API。

#### 文案与标点

- 中文文案（文档、注释、docstring、`zh-CN` i18n、`_conf_schema.json`）统一使用全角标点：`，。：；？！（）“”`；中文句读处不得用半角逗号 `,` 代替 `，`，也不得用半角冒号 `:` 代替 `：`。
- 英文文案、代码、`en-US` locale 文件保持半角标点：`, . : ; ( )`。
- 只调整注释、docstring 与字符串字面量里的标点；代码位置的标点属于语法，不得改动。改动前端 fallback 文案后需重新 `pnpm build` 并提交 `pages/dashboard/` 产物。

#### 提交规范

要点：Conventional Commits + 单一职责。

格式：feat: / fix: / refactor: / chore: / docs:
一个 commit/PR 只做一件事
英文 message
分支名 feat/xxx / fix/xxx
