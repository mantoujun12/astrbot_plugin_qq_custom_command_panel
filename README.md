# astrbot_plugin_qq_custom_command_panel

QQ 官方机器人指令面板内容自定义插件。在 AstrBot WebUI 中配置要展示的指令条目, 插件会把它们写入 QQ 官方机器人的指令面板, 用户在 QQ 输入 `/` 即可看到面板内容。

## 核心特性

- 用户在 AstrBot WebUI 中通过 schema 的 `selected_commands` 字段手动添加指令条目 (name + desc), 面板内容完全由用户决定
- 支持 c2c (单聊)、group (群聊)、channel (文字子频道)、dm (频道私信) 四种场景
- 可直接在 schema 的 `qq_platforms` 里填写 appid + clientSecret, 不依赖 AstrBot 后台是否配置了 qq_official 适配器
- 一键删除该 appid 下所有面板 (`/qq_panel_purge`), 无需担心 20 上限

## 配置说明

在 AstrBot WebUI -> 插件配置 -> astrbot_plugin_qq_custom_command_panel 中:

1. **qq_platforms**: 添加 QQ 机器人, 填入 appid / clientSecret (留空则自动从 AstrBot 平台配置读取)
2. **scenes**: 选择生效场景, 默认 `c2c + group`
3. **selected_commands**: 添加要在 QQ 面板展示的指令条目, 每条 {name, desc}, name 最长 14 字符, desc 最长 30 字符, 最多 20 条
4. **auto_sync_on_config_change**: 配置变更后自动同步到面板

## 调试指令

| 指令 | 作用 |
|---|---|
| `/qq_panel_resync` | 手动重新同步面板 |
| `/qq_panel_fetch` | 查看 QQ 服务端已注册的指令面板 |
| `/qq_panel_purge` | 直接清空该 appid 下所有指令面板 |
| `/qq_panel_list` | 列出 AstrBot 已注册的指令 (仅辅助填 schema, 不会写入面板) |
| `/qq_panel_platforms` | 查看 schema / context 平台配置识别情况 |
| `/qq_panel_reload_check` | 确认代码版本 |

## 已知限制

QQ 官方机器人指令面板的 API 限制:

- 每个面板最多 20 个元素
- 元素 name 最长 14 字符, desc 最长 30 字符
- 每机器人最多 20 个面板
- `channel` / `dm` 场景仅支持 `target_type=all`

## 下一步计划

- [] i18n - 国际化支持
- [] QQ API 覆盖 - 更新、批量、子频道、富文本
- [] 完善调用入口 - 可视化 + 异步进度反馈
- [] 完善配置 - 连接测试等
- [] Web UI - 可视化配置，一键同步 AstrBot 指令列表并按需选择

## 许可证

本项目使用 AGPLv3 协议开源, 详见 [LICENSE](LICENSE) 文件。