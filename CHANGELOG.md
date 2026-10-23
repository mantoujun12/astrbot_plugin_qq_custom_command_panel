# Changelog

本文件记录本项目的所有重要变更。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### 修复

- 修复 `robot_config.json` 读取或保存时的目录检查、目录创建、序列化与写入失败会直接抛出未包装的 `OSError` / `TypeError`，导致「机器人」页读取、保存与导入返回非本地化 500 的问题；这些失败现在统一转换为 `RobotConfigError` (#72)

## [v0.6.1] - 2026-10-21

### 新增

- 视图侧边栏新增「日志」页：通过 SSE 实时查看插件输出，支持搜索、日志等级过滤、暂停、自动滚动、堆栈展开与清空当前视图；后端按插件日志前缀收集并保留当前进程最近 1000 条 (#62)

### 变更

- 视图「机器人」页在窄屏下将机器人列表改为下拉菜单，避免机器人较多时在编辑器上方堆积 (#60)

### 修复

- 修复在 AstrBot 4.29+ 上插件加载失败并报 `__init__() missing 1 required positional argument: 'config'` 的问题：`astrbot.api.logger` 现为按调用方模块解析目标的转发代理，日志缓冲改为解析出插件共享的 logger 再安装 handler，插件入口也显式使用 `Star.logger`，不再误走 Loguru 分支抛 `TypeError`，也不会把 handler 挂到其他模块的 logger 上导致面板日志为空 (#63)
- 修复日志采集与 Loguru 宿主不兼容、调试日志遗漏、插件重载后流游标失效及旧订阅卡住的问题；同时仅采集本插件源码发出的日志，并限制并发日志流数量 (#62)
- 修复日志页从 mock 切换到真实流时启动日志被游标过滤，以及清空搜索后列表异常的问题 (#62)

## [v0.6.0] - 2026-10-17

### 新增

- 新增俄语与日语支持：WebUI 元数据、配置项、插件视图文案，以及 core 日志、同步进度和校验错误均可使用 `ru-RU` / `ja-JP` (#58)
- 视图「设置」页新增「关于插件」卡片，展示插件简介、版本号并提供 GitHub 仓库入口 (#57)
- 视图「设置」页新增主题配色：可配置主色与辅助色（`#RRGGBB`），保存后同步应用到浅色与深色主题 (#57)
- 新增新版机器人配置：按「机器人 → 场景 → 指令条目」组织，每台机器人独立维护 AppID / ClientSecret / platform 与四种场景的指令条目；视图侧边栏新增「机器人」页，旧的全局设置页改名为「兼容性」并继续可用 (#48)
- 新增新版配置 Web API：`GET /<plugin>/robots`、`POST /<plugin>/robots`、`POST /<plugin>/robots/import-legacy`；旧配置可从兼容性配置按 AppID 导入，新版配置持久化到 `plugin_data/astrbot_plugin_qq_custom_command_panel/robot_config.json` (#48)
- 新旧配置运行时按 AppID 逐机器人合并：新版定义某 AppID 时接管该机器人，未接管的兼容机器人继续使用旧全局 `scenes` + `selected_commands` (#48)
- 面板同步改为按机器人、按场景写入；场景未启用时清理该场景下本插件面板，任一场景拉取失败时该机器人整次同步中止 (#48)
- 新版配置保存与导入增加 `version` 乐观并发检查，版本不一致返回 HTTP 409；`robot_config.json` 损坏时抛错并中止，不回退旧配置 (#48)

### 变更

- 状态概览的平台卡片显示机器人备注名，并标注该平台由「机器人配置」还是「兼容性配置」接管，便于确认当前生效的配置来源 (#57)
- 状态概览的指标卡不再显示“上限”和“部分场景查询失败，该值为下限”备注，达到上限时仍保留数值高亮 (#57)
- 视图「设置」页改为可维护插件日志语言：页面内读取并写回 `language`（保存后立即生效），「兼容性」页只保留场景、平台与指令条目；配置写回改为按字段合并，两个页面不会互相覆盖对方刚保存的改动 (#50)
- 视图「机器人」页的「新增机器人」与「从兼容配置导入」改为弹窗：新增只需先填名称与平台凭证，各场景的指令条目创建后再去配置 (#50)
- 视图「机器人」页删除机器人配置时增加确认弹窗，取消不会移除机器人，确认后仍需保存才会写入配置；mock 环境下也可打开弹窗预览 (#57)
- 视图观感对齐 AstrBot 宿主页面层：随包分发 Outfit 变量字体、统一卡片与按钮圆角、收紧栅格沟槽与输入框密度，侧边栏底部显示插件版本号 (#50)
- 运行期不再在 `requirements.txt` 中声明 `aiohttp`，改由 AstrBot 宿主环境提供，避免与宿主版本冲突；测试环境单独声明 `aiohttp>=3.14.5` (#48, #56)
- 升级开发与 CI 依赖：`pytest` 9.1.1、`pytest-asyncio` 1.4.0、`pytest-cov` 7.1.0、`ruff` 0.17.0 (#52, #53, #54, #55)，`actions/setup-python` 升级到 v7 (#51)

### 修复

- 修复旧配置里存在非法主题色时，其他页面保存被同一字段校验拦住的问题；未提交的主题色会回退到默认配色 (#57)
- 修复新版配置按「机器人 → 场景」写入不同指令后同步失败的问题：写入 QQ 面板的条目重新带上 `type: command`，此前只发 `name` / `desc` 会被 QQ 以 `30015 面板元素类型不合法` 整份拒绝，同步结果因此显示为「没有触发」；同时场景写入失败不再被静默吞掉，平台会带着失败原因和已写入的场景数上报 (#48)
- 修复同步结果的平台计数：整轮没有任何条目时（纯清理）不再报成「成功 0 个平台」，处理过的机器人一律计入 `platforms`；场景因面板数达到 QQ 上限而没写入时也按失败上报，不再静默跳过 (#48)
- 修复从可视化视图保存配置后，AstrBot 插件配置页的 `qq_platforms` / `selected_commands` 报「找不到对应模板，请删除后重新添加。」的问题：写回 `template_list` 字段时补上 AstrBot 用于匹配模板的 `__template_key`（本插件为 `qq_platform` / `command`），提交项缺失或携带非法 key 时一律纠正为插件声明的模板 key；旧版本写坏的配置在下一次保存时会被补齐 (#47)

### 文档

- 补全 README：新增「安装」章节与 `robot_config.json` 结构示例，开发章节补充覆盖率、打包、发布与 CI 命令和目录结构 (#49)
- 补全 AGENTS.md：新增目录结构、测试约定、CI 与发布说明，开发命令补齐单测筛选、覆盖率、pre-commit 与打包命令 (#49)

## [v0.5.2] - 2026-10-16

### 变更

- 将 `aiohttp` 依赖要求由 `==3.14.3` 放宽为 `>=3.14.3`，避免与 AstrBot 主环境已安装的其他版本产生冲突 (#46)

## [v0.5.1] - 2026-10-15

### 新增

- 可视化视图新增「同步」入口：状态页点「同步面板」即可按当前配置同步，进度通过 SSE 实时推送（进度条 + 逐平台状态 + 日志）；任务跑在后台，刷新或切页后回来还能续看结果 (#39)
- 可视化视图的设置页改为可编辑：language / scenes / qq_platforms / selected_commands 都能在页面上维护并写回插件配置（保存后立即生效），另有「保存并同步」 (#39)
- 视图后端新增 `GET /<plugin>/config`、`POST /<plugin>/config`、`POST /<plugin>/sync`、`GET /<plugin>/sync/events`(SSE) 四个接口 (#39)
- `PanelSyncer.sync_all` 新增结构化进度回调 `on_event`；新增 `SyncRunner` 负责单飞的后台同步任务与事件缓冲 (#39)
- 新增 `scripts/package_plugin.py`：按 AstrBot 实际读取的文件白名单打包发布 zip（含 LICENSE，排除 `__pycache__` / `*.pyc`），仅依赖标准库、固定时间戳以保证产物可复现，自动发布工作流改用该脚本 (#40)
- 新增 `scripts/bump_version.py`：一条命令同步 metadata.yaml、core/paths.py 与 web/dashboard/package.json 的版本号，支持交互式选择与 `patch` / `minor` / `major` / 指定版本，另有 `--dry-run` 预览与 `--check` 一致性校验 (#44)

### 变更

- 前端视图新增 vitest 单元测试，并把 dashboard 的覆盖率与测试结果接入 Codecov（flag `dashboard`），核心 pytest 也接入 `codecov.yml` 覆盖率门禁 (#38, #42, #43)
- 统一全仓库中英文标点：中文使用全角，英文与代码使用半角 (#37)

### 修复

- 修正视图 i18n 根键：`views.<view>` 改为 `pages.<view>`，面板标题不再回退成目录名 `dashboard`，视图内文案与语言切换恢复生效 (#39)
- 平台凭证只从插件配置读取：删除从 AstrBot context 回退读取平台适配器信息的逻辑（插件拿不到适配器里的机器人信息），状态接口与前端类型移除 `source` 字段，mock 数据同步更新 (#39)
- 修复可视化视图保存配置时抛出 `DataCloneError` 的问题：提交前把 Vue 响应式对象快照为可结构化克隆的普通数据 (#41)
- 修复自动发布工作流在 v0.5.0 合并时未被触发且无法重跑的问题：改由 tag / release 是否存在决定是否发布，新增 `workflow_dispatch` 手动补发，并在打 tag 前校验三处版本号一致 (#36)

## [v0.5.0] - 2026-10-13

> **内嵌面板（AstrBot WebUI 可视化视图）目前处于测试阶段**，界面布局与状态接口仍可能继续调整，使用中遇到问题欢迎反馈。

### 新增

- 内嵌面板（AstrBot WebUI 可视化视图）：在 WebUI 中查看各 QQ 平台的面板同步状态、指令条目数与配置概要，跟随宿主的明暗主题 (#33, #34)
- 视图后端接口 `GET /<plugin>/status`: 基于 `context.register_web_api()` 并发查询各平台面板状态，对 appid / pf_id 脱敏，并带单飞 + 短 TTL 缓存 (#34)

### 变更

- 前端视图 (Vue 3 + TypeScript + Vite + Vuetify 4) 的构建与类型检查纳入 CI 与 pre-commit，构建产物不带内容哈希 (#33, #34)
- `PanelSyncer` 新增 `build_clients()` 与公开的 `owned_panels_by_scope()`，供视图状态接口复用 (#34)

## [v0.4.4] - 2026-10-12

### 变更

- 将 `aiohttp` 依赖要求固定为 `==3.14.3` (#32)

## [v0.4.3] - 2026-10-11

### 修复

- 修复面板状态文件 `panel_state.yaml` 未落到 AstrBot 的 `data/plugin_data/astrbot_plugin_qq_custom_command_panel/` 目录，而是回退到工作目录 `data/` 的问题 (#30)
- 插件数据目录解析改为按 `StarTools.get_data_dir` → `context.get_data_dir` → `context.data_dir` → AstrBot 官方路径工具的优先级；即使官方路径工具不可用，最后兜底也按 AstrBot 的数据根规则（`ASTRBOT_ROOT` > 桌面版 `~/.astrbot` > 工作目录）定位，不会写到数据根之外 (#30)

## [v0.4.2] - 2026-10-11

### 新增

- 基于 AstrBot stub 的离线 pytest 测试套件，覆盖 `config` / `i18n` / `panel_syncer` / `qq_client` / `state` 等业务逻辑 (#27)
- GitHub Actions CI，在 Python 3.10 - 3.13 矩阵上运行测试并收集覆盖率 (#27)
- 与 CI 保持一致的 pre-commit hooks (#27)
- 向 Codecov 上传分支覆盖率 (#28)

### 变更

- 将 `aiohttp` 依赖要求更新为 `>=3.14.4` (#26)
- 将 `actions/checkout` 升级到 v7 (#25)
- 调整 GitHub issue 模板，对齐 `type:*` 标签体系
- 更新 README 徽章与封面，并修正配置说明与文档措辞

## [v0.4.1] - 2026-09-26

### 变更

- 移除封面图与 changelog 自动化流程，精简仓库 (#22)
- 移除通过 Python 注册的调试指令 (#23)

## [v0.4.0] - 2026-08-29

### 新增

- 面板指令新增异步进度反馈与结构化输出 (#20)
- 新增 issue 模板及带讨论链接的 GitHub 配置 (#19)

### 修复

- 修复 `qq_panel_list` 未展示全部已注册指令的问题 (#18)

## [v0.3.0] - 2026-08-28

### 新增

- 新增面板详情能力：`get_panel`，并扩展 `update_panel` 的 `target_type` 参数 (#14)
- 新增 Dependabot 依赖自动更新配置，并更新相关依赖 (#10, #11, #12, #13)

### 变更

- 将 `PanelSyncer` 的 `build_clients` / `list_all_panels` 暴露为公开方法 (#7)
- 移除无效的 `auto_sync_on_config_change` schema 选项 (#8)
- 面板同步与清理操作改为并行执行，提升效率 (#14)
- 更新封面与 Logo，完善 README (#15)
- 新增自动发布与 changelog GitHub Actions 工作流 (#9)

## [v0.2.2] - 2026-08-24

### 新增

- 国际化(i18n)支持 (#6)

### 文档

- 新增 README 与 Logo (#4)
- 优化文档与指令描述，提升可读性 (#5)

## [v0.2.0] - 2026-08-23

### 新增

- 支持用户在配置中自定义 QQ 平台凭据与指令条目 (#2)

### 修复

- 优化面板同步逻辑，避免重复创建面板 (#3)

## [v0.1.0] - 2026-08-23

### 新增

- 首次发布：QQ 官方机器人指令面板同步功能 (#1)

[v0.6.1]: https://github.com/mantoujun12/astrbot_plugin_qq_custom_command_panel/compare/v0.6.0...v0.6.1
[v0.6.0]: https://github.com/mantoujun12/astrbot_plugin_qq_custom_command_panel/compare/v0.5.2...v0.6.0
[v0.5.2]: https://github.com/mantoujun12/astrbot_plugin_qq_custom_command_panel/compare/v0.5.1...v0.5.2
[v0.5.1]: https://github.com/mantoujun12/astrbot_plugin_qq_custom_command_panel/compare/v0.5.0...v0.5.1
[v0.5.0]: https://github.com/mantoujun12/astrbot_plugin_qq_custom_command_panel/compare/v0.4.4...v0.5.0
[v0.4.4]: https://github.com/mantoujun12/astrbot_plugin_qq_custom_command_panel/compare/v0.4.3...v0.4.4
[v0.4.3]: https://github.com/mantoujun12/astrbot_plugin_qq_custom_command_panel/compare/v0.4.2...v0.4.3
[v0.4.2]: https://github.com/mantoujun12/astrbot_plugin_qq_custom_command_panel/compare/v0.4.1...v0.4.2
[v0.4.1]: https://github.com/mantoujun12/astrbot_plugin_qq_custom_command_panel/compare/v0.4.0...v0.4.1
[v0.4.0]: https://github.com/mantoujun12/astrbot_plugin_qq_custom_command_panel/compare/v0.3.0...v0.4.0
[v0.3.0]: https://github.com/mantoujun12/astrbot_plugin_qq_custom_command_panel/compare/v0.2.2...v0.3.0
[v0.2.2]: https://github.com/mantoujun12/astrbot_plugin_qq_custom_command_panel/compare/v0.2.0...v0.2.2
[v0.2.0]: https://github.com/mantoujun12/astrbot_plugin_qq_custom_command_panel/compare/v0.1.0...v0.2.0
[v0.1.0]: https://github.com/mantoujun12/astrbot_plugin_qq_custom_command_panel/releases/tag/v0.1.0
