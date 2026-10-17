#### 项目简介

QQ 官方机器人指令面板内容自定义插件。在 AstrBot WebUI 中按机器人、场景配置要展示的指令条目，插件会把它们写入 QQ 官方机器人的指令面板，用户在 QQ 输入 `/` 即可看到面板内容。新版配置按机器人独立维护 AppID / ClientSecret / platform 与各场景指令，旧的全局配置作为兼容性配置继续可用。

#### 技术栈

- Python 3.10+（代码里有 `X | None`、`from __future__ import annotations`；CI 矩阵为 3.10 / 3.11 / 3.12）
- aiohttp（HTTP 客户端，10s 超时）
- AstrBot Star 插件体系（`@register` / `@filter.command` / `Context` / `AstrBotConfig`）
- 插件视图前端：Vue 3 + TypeScript + Vite + Vuetify 4 + vue-router（hash）+ Vitest，源码在 `web/dashboard/`，构建产物提交在 `pages/dashboard/`
- 前端工具链要求 Node `^22.12.0 || >=24`（见 `web/dashboard/package.json` 的 `engines`）与 pnpm 9+（lockfile v9，CI 固定 pnpm 12）
- 无第三方数据库，本地状态存 AstrBot 的 `data/plugin_data/astrbot_plugin_qq_custom_command_panel/`；新版机器人配置存 `robot_config.json`，兼容性配置仍存 AstrBotConfig

#### 目录结构

```text
main.py                  插件入口：@register、initialize() 启动时同步一次、terminate() 收尾
core/                    插件自身的 Python 包，业务逻辑都在这里
├─ __init__.py           公开 API 汇总（__all__）
├─ config.py             兼容性配置解析 / 校验 helper
├─ robot_config.py       新版机器人配置的读写、校验、迁移与合并（robot_config.json）
├─ qq_client.py          QQ 开放平台 HTTP 客户端（鉴权 + 面板增删改查）
├─ panel_syncer.py       按机器人、按场景的面板同步
├─ sync_runner.py        单飞后台同步任务与 SSE 事件缓冲
├─ web_api.py            视图接口 WebApiBundle
├─ state.py              面板归属状态持久化
├─ paths.py              数据目录解析与 PLUGIN_VERSION 常量
└─ i18n.py + i18n/       后端运行期文案（core/i18n/<locale>.json）
_conf_schema.json        WebUI 插件配置 schema（兼容性配置）
metadata.yaml            插件元数据，版本号唯一来源
.astrbot-plugin/i18n/    WebUI 侧 metadata / config / pages 翻译
pages/dashboard/         视图构建产物（提交进仓库，视为生成文件，不要手工改）
web/dashboard/           视图源码（src/api、src/components、src/views、src/test 等）
tests/                   离线 pytest 套件（conftest.py 注入 astrbot stub）
scripts/                 bump_version.py、package_plugin.py
```

#### 开发命令

插件通过 AstrBot 加载，功能性测试仍需要在运行的 AstrBot 实例下进行；业务逻辑可跑离线 pytest 套件（无需安装 AstrBot，`tests/conftest.py` 会注入 astrbot stub）。

Python 侧：

```bash
pip install -r requirements.txt -r requirements-dev.txt   # 运行 + 开发依赖
pytest -q                                                 # 全部离线测试
pytest tests/test_robot_config.py -q                      # 只跑单个模块
pytest -k panel_syncer -q                                 # 按关键字筛选
pytest --cov --cov-branch --cov-report=xml --junitxml=junit.xml -o junit_family=legacy   # 覆盖率 + JUnit，与 codecov-core.yml 一致
ruff check . --fix                                        # lint（E/W/F/I/UP/B/S），顺带修可自动修的
ruff format --check .                                     # 格式检查
pre-commit install                                        # 可选：装 git hook
pre-commit run --all-files                                # 与 pre-commit.ci / CI 同一套 hooks
python scripts/bump_version.py                            # 升版本号
python scripts/package_plugin.py                          # 打发布 zip 到 dist/
```

升级版本号（metadata.yaml 是唯一版本源，`core/paths.py` 与 `web/dashboard/package.json` 必须同步，否则 release.yml 会拒绝发布）：

`python scripts/bump_version.py` 不带参数是交互式选择 patch / minor / major / 自定义；也可直接 `python scripts/bump_version.py minor` 或 `v0.6.0`，另有 `--dry-run` 预览、`--check` 只校验三处是否一致。

打包发布 zip：

`python scripts/package_plugin.py` 默认输出到 `dist/`，可用 `-o 目录或 *.zip` 指定输出、`-v v0.6.0` 覆盖版本号；只收录 AstrBot 会读取的文件（metadata.yaml / main.py / `_conf_schema.json` / requirements.txt / logo.png / README.md / LICENSE / core / .astrbot-plugin / pages），tests、web、.github 不进包。

插件视图前端（在 `web/dashboard/` 下）：

```bash
pnpm install        # 需要 Node ^22.12.0 || >=24
pnpm dev            # 本地 dev server（没有 bridge，走 mock）
pnpm build          # vue-tsc 类型检查 + Vite 打包，产物直接写 pages/dashboard/
pnpm preview        # 预览构建产物
pnpm test           # vitest 单次运行
pnpm test:coverage  # 覆盖率（阈值见 vitest.config.ts）
pnpm test:report    # 额外产出 test-report.junit.xml
pnpm test:codecov   # 覆盖率 + JUnit，CI 用的入口
```

`pnpm build` 会先跑 `vue-tsc` 类型检查，产物直接写入仓库根目录的 `pages/dashboard/`（见 `vite.config.ts` 的 `build.outDir`），不需要手工拷贝，产物需要一起提交。

#### 测试

离线 pytest 套件（`tests/`）：

- 用例与 `core/` 模块一一对应，命名 `test_<模块>.py`（`core/robot_config.py` → `tests/test_robot_config.py`），新增或修改业务逻辑要带上对应用例
- `tests/conftest.py` 在导入期往 `sys.modules` 注入最小 astrbot stub（logger / Star / register / web helper / AstrBotConfig）；它必须先于所有测试模块执行，因此禁止在 conftest 里 import 插件代码，也不要为了让测试跑通去随意扩大 stub 表面
- 异步用例靠 `pyproject.toml` 的 `asyncio_mode = "auto"`，直接写 `async def test_...`，不用加 `@pytest.mark.asyncio`
- 公共假件统一放 `tests/fakes.py`（FakeResponse / FakeSession / FakeQQClient），不要在各自的测试里另起一套
- `main.py` 是装配层（`from .core import ...` 相对导入，仓库根不是包），离线套件不覆盖它，改动入口只能在真实 AstrBot 下验证
- 覆盖率只统计生产代码（`[tool.coverage.run]` 已 omit `tests/*`），本地用上面那条 `pytest --cov` 复现 CI 口径

vitest 套件（`web/dashboard/`）：

- 测试文件与被测代码同目录、命名 `*.test.ts`；视图挂载走 `src/test/helpers.ts` 的 `mountView`，断言只看文案 / 自有 class / 属性 / emit，不断言 Vuetify 内部结构
- `pnpm test:coverage` 不得低于 `vitest.config.ts` 的 `coverage.thresholds`；覆盖率只统计 `src/**`，`*.test.ts`、`src/main.ts`、`src/test/**` 除外
- bridge、受限 iframe 等宿主相关行为只能靠单测兜住，真机表现仍需在 AstrBot 下验证

#### CI 与发布

| workflow | 触发 | 内容 |
| --- | --- | --- |
| `ci-core.yml` | push master / PR | Python 3.10 / 3.11 / 3.12 跑 `pytest` |
| `ci-dashboard.yml` | push master / PR | Node 24 + pnpm 12 跑 `pnpm install --frozen-lockfile` + `pnpm build`（含 vue-tsc 类型检查） |
| `codecov-core.yml` | push master / PR | `pytest --cov --cov-branch --cov-report=xml --junitxml=junit.xml`，分两次以 flag `unittests` 上传覆盖率与 Test Analytics |
| `codecov-dashboard.yml` | push master / PR | `pnpm test:codecov`，以 flag `dashboard` 上传 `coverage/lcov.info` 与 `test-report.junit.xml` |
| `release.yml` | push master 且改动 `metadata.yaml`，或手动 dispatch | 校验三处版本号一致 → `scripts/package_plugin.py` 打包 → 打 tag → 建 Release |
| `pullfrog.yml` | 手动 dispatch | 外部 agent 工作流，不参与构建与发布 |

发布是幂等的：tag 与 release 都已存在就跳过，上次中途失败或漏掉 push 事件时可在 Actions 里手动 dispatch 重跑。合并前至少要过 ci-core、ci-dashboard 与 pre-commit。

#### 架构约定

1. QQ API GET /v2/panels 必须带 scope 参数
2. 面板同步现在按机器人、按场景执行；任一场景 list_panels 失败时该机器人整次同步中止，不许吞异常（否则会重复创建面板）
3. PanelSyncer 通过 build_runtime_robots / build_clients / list_all_panels 等公开方法暴露能力；外部禁止直接访问 _ 前缀私有方法
4. 兼容性配置解析逻辑整合到 core/config.py 的 helper 函数(get_platforms_from_schema / get_configured_platforms / export_config / normalize_config_payload)，不要散落在 main.py；新版机器人配置的读写、校验、迁移与合并统一放 `core/robot_config.py`
5. 指令用 @filter.command 注册，描述取 handler docstring 第一行（除非显式传 description）
6. 异步一律 async/await，不用回调风格
7. 日志统一 from astrbot.api import logger，前缀 [qq-command-panel]
8. 平台凭证只来自插件自己的配置：兼容性配置从 `qq_platforms` 读取，新版配置从 `robot_config.json` 读取；AstrBot 不向插件暴露平台适配器的机器人信息，禁止再写从 context 回退读取 appid / clientSecret 的逻辑
9. 面板同步的结构化进度走 `PanelSyncer.sync_all(on_event=...)`，后台任务与事件缓冲由 `core/sync_runner.py` 的 `SyncRunner` 负责；同一时间只允许一个同步任务
10. 新旧配置运行时按 AppID 合并：`robot_config.json` 中定义了某 AppID 就由新版接管该机器人；未被接管的兼容机器人继续使用旧全局 `scenes` + `selected_commands`；合并统一走公开的 `build_runtime_robots`，不要在同步 / 状态 / Web API 里各自复制规则
11. `robot_config.json` 损坏、非法编码或结构异常时必须抛错并中止，不允许静默回退兼容配置；新版保存采用 `version` 乐观并发检查，过期写入返回 HTTP 409

#### 插件视图 (web/dashboard)

1. 视图必须保留 `base: './'` 与 hash 路由。宿主按真实文件路径下发资源（带令牌前缀），绝对路径 `/assets/...` 会 404，history 路由刷新也会 404。
2. 数据访问集中在 `src/api/`，统一通过 bridge(`window.AstrBotPluginView`)调用后端；API 调用使用 bridge 的 `apiGet` / `apiPost` / `subscribeSSE`，鉴权与 token 前缀由宿主 bridge 处理，前端不要自己拼插件名前缀或鉴权头。本地 dev 没有 bridge 时退回 mock，且必须在页面上标注，不许把假数据伪装成真实状态。
3. 文案走 `bridge.t(key, fallback)`，key 写在 `.astrbot-plugin/i18n/<locale>.json` 的 `pages.<view>.*`（宿主按 `pages.<目录名>.title` 取视图标题，写成 `views` 会让标题回退成目录名）。产物**不含**翻译，只编译进 fallback 文案；所以改文案只需改 JSON + 重载插件，不用重新 build，但 key 和 fallback 要成对维护。
4. 主题与配色跟随宿主：用 bridge context 的 `isDark` 切 `<v-app :theme>`，色值抄宿主 `dashboard/src/theme/*.ts`。插件视图跑在 iframe 里，宿主的 `--v-theme-*` 不会继承进来。
5. iframe 是 sandbox 的（没有 `allow-same-origin`），禁止访问 `localStorage` / cookies / 父页面 DOM；需要持久化的状态放后端。
6. 不做 SCSS 定制层。只有宿主靠 SCSS 才拿得到的值（如卡片 16px 圆角），在 `src/styles/dashboard.css` 里直接写数值。
7. 产物文件名不带内容哈希（宿主对所有视图资源都返回 `Cache-Control: no-store`），且产物视为生成文件 —— 冲突时重新 `pnpm build`，不要手工合并（见 `.gitattributes`）。
8. 后端接口用 `context.register_web_api()` + `astrbot.api.web`(json_response / error_response / stream_response / request)，不要把 FastAPI/Quart 的原始请求对象暴露给业务代码。
9. 视图接口固定为 `status`(GET) / `config`(GET+POST) / `robots`(GET+POST) / `robots/import-legacy`(POST) / `sync`(POST) / `sync/events`(GET, SSE)，统一在 `core/web_api.py` 的 `WebApiBundle` 里注册，路径前缀是插件名。
10. 兼容性配置写回走 `POST config` → `AstrBotConfig.update()` + `save_config_async()`；新版机器人配置读取 / 保存走 `GET / POST robots`，保存由 `core/robot_config.py` 校验并原子写入 `robot_config.json`（临时文件 + `Path.replace`）。`GET config` / `GET robots` 都只回 secret 掩码，明文 secret 不允许出现在响应、日志或前端里，前端提交时留空表示沿用原值。
11. 同步进度用 SSE：后端从 `SyncRunner.stream(since)` 产事件（`data: {...}\n\n`），前端用 `bridge.subscribeSSE` 订阅、收到 `finish` 后自行退订；宿主不会通知流被关闭。
12. 视图代码改动要带同目录同名 `*.test.ts`：挂载走 `src/test/helpers.ts` 的 `mountView`，断言只看文案/自有 class/属性/emit，不要断言 Vuetify 内部结构；`pnpm test:coverage` 不得低于 `vitest.config.ts` 的 `coverage.thresholds`。
13. 视图侧边栏顶部固定为「状态概览」「机器人」「兼容性」，底部是「设置」（当前为占位页）；机器人页负责 机器人 → 场景 → 指令条目的编辑与导入，文案 key 前缀是 `pages.dashboard.robots.*`，兼容页使用 `pages.dashboard.compatibility.*`，设置页使用 `pages.dashboard.settings.*`。

#### 代码风格

要点：类型注解齐全、from __future__ import annotations、Path 而非字符串拼路径、__all__ 导出公开 API。

Ruff 配置在 `pyproject.toml`：line-length 100、target py312、select `E/W/F/I/UP/B/S`；pre-commit 里 `ruff-check --fix` 必须排在 `ruff-format` 之前。

#### 文案与标点

- 中文文案（文档、注释、docstring、`zh-CN` i18n、`_conf_schema.json`）统一使用全角标点：`，。：；？！（）“”`；中文句读处不得用半角逗号 `,` 代替 `，`，也不得用半角冒号 `:` 代替 `：`。
- 英文文案、代码、`en-US` locale 文件保持半角标点：`, . : ; ( )`。
- 只调整注释、docstring 与字符串字面量里的标点；代码位置的标点属于语法，不得改动。改动前端 fallback 文案后需重新 `pnpm build` 并提交 `pages/dashboard/` 产物。
- 文案分三处，改动时要一起过：`core/i18n/<locale>.json`（后端日志与进度）、`.astrbot-plugin/i18n/<locale>.json`（WebUI 元数据 / 配置项 / 视图标题，也是 `bridge.t` 的 key 来源）、`web/dashboard/src` 里 `bridge.t(key, fallback)` 的 fallback 字面量（编译进产物，改了要重新 `pnpm build`）。新增 key 时 `zh-CN`、`en-US`、`ru-RU`、`ja-JP` 四份都要补，并保持占位符一致。

#### 提交规范

要点：Conventional Commits + 单一职责。

格式：feat: / fix: / refactor: / chore: / docs:
一个 commit/PR 只做一件事
英文 message
分支名 feat/xxx / fix/xxx
文档改动走 `docs:`；改动用户可见行为时同步更新 CHANGELOG.md 的 `[Unreleased]`（分类：新增 / 变更 / 修复 / 文档）
