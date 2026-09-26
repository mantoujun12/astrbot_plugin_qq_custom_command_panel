<div align="center">

# astrbot_plugin_qq_custom_command_panel

<!-- Badge -->

[![GitHub License](https://img.shields.io/github/license/mantoujun12/astrbot_plugin_qq_custom_command_panel?style=for-the-badge)](LICENSE)
![GitHub Release](https://img.shields.io/github/v/release/mantoujun12/astrbot_plugin_qq_custom_command_panel?sort=date&display_name=tag&style=for-the-badge)
![GitHub Repo stars](https://img.shields.io/github/stars/mantoujun12/astrbot_plugin_qq_custom_command_panel?style=for-the-badge)
[![AstrBot](https://img.shields.io/badge/AstrBot-%234984b9?style=for-the-badge&logo=Github)](https://github.com/AstrBotDevs/AstrBot)

<!-- Badge -->

QQ 官方机器人指令面板内容自定义插件

在 **AstrBot WebUI** 中配置要展示的指令条目, 插件会把它们写入 QQ 官方机器人的指令面板,

用户在 QQ 输入 `/` 即可看到面板内容。

</div>

## 核心特性

- 用户在 **AstrBot WebUI** 中通过 schema 的 `selected_commands` 字段手动添加指令条目 (name + desc), 面板内容完全由用户决定
- 支持 c2c (单聊)、group (群聊)、channel (文字子频道)、dm (频道私信) 四种场景
- 可直接在 schema 的 `qq_platforms` 里填写 appid + clientSecret, 不依赖 AstrBot 后台是否配置了 qq_official 适配器
- 配置变更后重启 AstrBot 即会自动同步, 无需任何指令操作

## 配置说明

在 AstrBot WebUI -> 插件配置 -> `astrbot_plugin_qq_custom_command_panel` 中:

1. **qq_platforms**: 添加 QQ 机器人, 填入 appid / clientSecret (留空则自动从 AstrBot 平台配置读取)
2. **scenes**: 选择生效场景, 默认 `c2c + group`
3. **selected_commands**: 添加要在 QQ 面板展示的指令条目, 每条 {name, desc}, name 最长 14 字符, desc 最长 30 字符, 最多 20 条

> 插件启动时会自动同步一次面板; 修改配置后重启 AstrBot 即可生效。

## 已知限制

QQ 官方机器人指令面板的 API 限制:

- 每个面板最多 20 个元素
- 元素 name 最长 14 字符, desc 最长 30 字符
- 每机器人最多 20 个面板
- `channel` / `dm` 场景仅支持 `target_type=all`

目前项目限制:

- 多个机器人共享相同的面板配置项，但会根据各自的 appid 接收独立的面板

## 下一步计划

- [x] i18n - 国际化支持
- [x] QQ API 覆盖 - 更新、批量、子频道、富文本
- [ ] 完善调用入口 - 可视化 + 异步进度反馈
- [ ] 完善配置 - 连接测试等
- [ ] Web UI - 可视化配置，一键同步 AstrBot 指令列表并按需选择

## 参考链接

- [QQ 机器人开放平台 - 开发文档 v2](https://bot.qq.com/wiki/develop/api-v2/) - 指令面板 / 消息收发 / API 鉴权等官方接口规范
- [AstrBot 插件开发指南](https://docs.astrbot.app/dev/star/plugin-new.html) - Star / filter / schema / 插件 Pages 等开发参考
- [AstrBot Plugin Pages](https://docs.astrbot.app/dev/star/guides/plugin-pages.html) - 自建 WebUI 的 bridge / Web API 规范 (对应下一步计划中的 Web UI)

## 许可证

本项目使用 AGPLv3 协议开源, 详见 [LICENSE](LICENSE) 文件。
