# astrbot_plugin_qq_custom_command_panel

将 AstrBot 已注册的指令同步到 QQ 官方机器人指令面板，用户在 QQ 输入 `/` 即可唤起面板快速调用 AstrBot 指令。

## 核心功能

- 支持 c2c (单聊)、group (群聊)、channel (文字子频道)、dm (频道私信) 四种场景
- 启动时自动同步 AstrBot 指令到 QQ 官方机器人指令面板
- 通过 AstrBot WebUI 选择要暴露的指令 (最多 20 个) 和生效场景
- 内置调试指令 `/qq_panel_resync`、`/qq_panel_list`

## 已知问题

QQ 官方机器人指令面板的 API 限制：

- 每个面板最多 20 个元素
- 元素 name 最长 14 字符，desc 最长 30 字符
- 每机器人最多 20 个面板
- `channel` / `dm` 场景仅支持 `target_type=all`

## 许可证

本项目使用 AGPLv3 协议开源，详见 [LICENSE](LICENSE) 文件。
