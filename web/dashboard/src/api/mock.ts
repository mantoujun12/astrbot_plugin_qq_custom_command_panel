/**
 * 本地 `pnpm dev` 用的假数据。
 *
 * 覆盖「已同步 / 重复面板 / 缺失 / 查询失败」几种状态，方便调样式；真实后端不会
 * 走到这里（见 api/dashboard.ts 的 fetchStatus / fetchConfig）。
 *
 * 注意：平台凭证只能来自插件配置，mock 里也不出现 AstrBot 平台来源的假平台。
 */

import type { PluginConfigResponse, StatusResponse } from '../types/dashboard'

export const MOCK_STATUS: StatusResponse = {
  plugin: { name: 'astrbot_plugin_qq_custom_command_panel', version: 'v0.5.0' },
  scenes: ['c2c', 'group'],
  items: { count: 3, max: 20 },
  panels: { total: 5, max: 40, partial: true },
  platforms: [
    {
      pf_id: '主机器人',
      appid: '102*****89',
      platform: 'qq_official',
      scenes: [
        { scope: 'c2c', state: 'synced', panel_id: 'panel_1a2b3c', items_count: 3 },
        { scope: 'group', state: 'duplicate', panel_id: 'panel_4d5e6f', items_count: 3 },
      ],
    },
    {
      pf_id: '测试机器人',
      appid: '103*****88',
      platform: 'qq_official_webhook',
      scenes: [
        { scope: 'c2c', state: 'missing' },
        { scope: 'group', state: 'failed' },
      ],
    },
  ],
}

export const MOCK_CONFIG: PluginConfigResponse = {
  language: 'zh-CN',
  primary_color: '#3c96ca',
  secondary_color: '#2f86bd',
  scenes: ['c2c', 'group'],
  available_scenes: ['c2c', 'group', 'channel', 'dm'],
  qq_platforms: [
    {
      name: '主机器人',
      appid: '1023456789',
      platform: 'qq_official',
      secret_masked: 'abc*****yz',
      secret_set: true,
    },
    {
      name: '测试机器人',
      appid: '1038765432',
      platform: 'qq_official_webhook',
      secret_masked: 'def*****wv',
      secret_set: true,
    },
  ],
  selected_commands: [
    { name: 'help', desc: '查看帮助' },
    { name: 'ping', desc: '连通性测试' },
    { name: 'status', desc: '查看运行状态' },
  ],
  limits: { name_max: 14, desc_max: 30, items_max: 20 },
}
