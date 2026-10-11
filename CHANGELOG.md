# Changelog

本文件记录本项目的所有重要变更。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/),
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [v0.4.3] - 2026-10-11

### 修复

- 修复面板状态文件 `panel_state.yaml` 未落到 AstrBot 的 `data/plugin_data/astrbot_plugin_qq_custom_command_panel/` 目录, 而是回退到工作目录 `data/` 的问题 (#30)
- 插件数据目录解析改为按 `StarTools.get_data_dir` → `context.get_data_dir` → `context.data_dir` → AstrBot 官方路径工具的优先级, 兜底仍锚定 AstrBot 配置的数据根, 兼容桌面打包版与 `ASTRBOT_ROOT` (#30)

## [v0.4.2] - 2026-10-11

### 新增

- 基于 AstrBot stub 的离线 pytest 测试套件, 覆盖 `config` / `i18n` / `panel_syncer` / `qq_client` / `state` 等业务逻辑 (#27)
- GitHub Actions CI, 在 Python 3.10 - 3.13 矩阵上运行测试并收集覆盖率 (#27)
- 与 CI 保持一致的 pre-commit hooks (#27)
- 向 Codecov 上传分支覆盖率 (#28)

### 变更

- 将 `aiohttp` 依赖要求更新为 `>=3.14.4` (#26)
- 将 `actions/checkout` 升级到 v7 (#25)
- 调整 GitHub issue 模板, 对齐 `type:*` 标签体系
- 更新 README 徽章与封面, 并修正配置说明与文档措辞

## [v0.4.1] - 2026-09-26

### 变更

- 移除封面图与 changelog 自动化流程, 精简仓库 (#22)
- 移除通过 Python 注册的调试指令 (#23)

## [v0.4.0] - 2026-08-29

### 新增

- 面板指令新增异步进度反馈与结构化输出 (#20)
- 新增 issue 模板及带讨论链接的 GitHub 配置 (#19)

### 修复

- 修复 `qq_panel_list` 未展示全部已注册指令的问题 (#18)

## [v0.3.0] - 2026-08-28

### 新增

- 新增面板详情能力: `get_panel`, 并扩展 `update_panel` 的 `target_type` 参数 (#14)
- 新增 Dependabot 依赖自动更新配置, 并更新相关依赖 (#10, #11, #12, #13)

### 变更

- 将 `PanelSyncer` 的 `build_clients` / `list_all_panels` 暴露为公开方法 (#7)
- 移除无效的 `auto_sync_on_config_change` schema 选项 (#8)
- 面板同步与清理操作改为并行执行, 提升效率 (#14)
- 更新封面与 Logo, 完善 README (#15)
- 新增自动发布与 changelog GitHub Actions 工作流 (#9)

## [v0.2.2] - 2026-08-24

### 新增

- 国际化(i18n)支持 (#6)

### 文档

- 新增 README 与 Logo (#4)
- 优化文档与指令描述, 提升可读性 (#5)

## [v0.2.0] - 2026-08-23

### 新增

- 支持用户在配置中自定义 QQ 平台凭据与指令条目 (#2)

### 修复

- 优化面板同步逻辑, 避免重复创建面板 (#3)

## [v0.1.0] - 2026-08-23

### 新增

- 首次发布: QQ 官方机器人指令面板同步功能 (#1)

[v0.4.3]: https://github.com/mantoujun12/astrbot_plugin_qq_custom_command_panel/compare/v0.4.2...v0.4.3
[v0.4.2]: https://github.com/mantoujun12/astrbot_plugin_qq_custom_command_panel/compare/v0.4.1...v0.4.2
[v0.4.1]: https://github.com/mantoujun12/astrbot_plugin_qq_custom_command_panel/compare/v0.4.0...v0.4.1
[v0.4.0]: https://github.com/mantoujun12/astrbot_plugin_qq_custom_command_panel/compare/v0.3.0...v0.4.0
[v0.3.0]: https://github.com/mantoujun12/astrbot_plugin_qq_custom_command_panel/compare/v0.2.2...v0.3.0
[v0.2.2]: https://github.com/mantoujun12/astrbot_plugin_qq_custom_command_panel/compare/v0.2.0...v0.2.2
[v0.2.0]: https://github.com/mantoujun12/astrbot_plugin_qq_custom_command_panel/compare/v0.1.0...v0.2.0
[v0.1.0]: https://github.com/mantoujun12/astrbot_plugin_qq_custom_command_panel/releases/tag/v0.1.0
