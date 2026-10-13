/**
 * 本地 `pnpm dev` 用的假数据。
 *
 * 覆盖「已同步 / 线上缺失 / 查询失败」三种状态，便于离线验证布局；生产环境不会
 * 走到这里（见 api/dashboard.ts 的 fetchStatus）。
 */

import type { StatusResponse } from '../types/dashboard'

export const MOCK_STATUS: StatusResponse = {
  plugin: { name: 'astrbot_plugin_qq_custom_command_panel', version: 'v0.5.0' },
  scenes: ['c2c', 'group'],
  items: { count: 3, max: 20 },
  panels: { total: 5, max: 40, partial: true },
  platforms: [
    {
      pf_id: '主机器人',
      appid: '102****47',
      source: 'schema',
      platform: 'qq_official',
      scenes: [
        { scope: 'c2c', state: 'synced', panel_id: 'panel_1a2b3c', items_count: 3 },
        { scope: 'group', state: 'duplicate', panel_id: 'panel_4d5e6f', items_count: 3 },
      ],
    },
    {
      pf_id: '测试机器人',
      appid: '103****88',
      source: 'context',
      platform: 'qq_official_webhook',
      scenes: [
        { scope: 'c2c', state: 'missing' },
        { scope: 'group', state: 'failed' },
      ],
    },
  ],
}
