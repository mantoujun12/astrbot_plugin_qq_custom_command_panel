/**
 * 状态概览 (/status) 的数据契约, 与后端 build_status 的返回一一对应。
 *
 * 该接口默认查询线上, 每个平台对所有场景各调一次 QQ API, 属慢请求。
 */

export const SCENES = ['c2c', 'group', 'channel', 'dm'] as const

/** 面板生效场景, 与 core/config.py 的 SCENES 对应 */
export type Scene = (typeof SCENES)[number]

/** 平台凭证来源: 插件 schema 的 qq_platforms, 或 AstrBot 平台配置 */
export type PlatformSource = 'schema' | 'context'

/** synced=线上恰有一条本插件面板, duplicate=同场景有多条, missing=该场景线上没有, failed=查询该场景失败 */
export type SceneState = 'synced' | 'duplicate' | 'missing' | 'failed'

export interface ScenePanelStatus {
  scope: Scene
  state: SceneState
  panel_id?: string
  items_count?: number
}

export interface PlatformStatus {
  /** 平台标识: 配置里的备注, 缺省时是 appid */
  pf_id: string
  /** 后端已脱敏, 前端不再自行处理 */
  appid: string
  source: PlatformSource
  platform: string
  /** 只包含当前生效的场景 */
  scenes: ScenePanelStatus[]
  /** 平台级失败原因 (例如列举面板不完整导致同步中止) */
  error?: string
}

export interface StatusResponse {
  plugin: { name: string; version: string }
  platforms: PlatformStatus[]
  /** 当前生效的场景 */
  scenes: Scene[]
  /** max 为 QQ 侧上限 (超长由后端截断, 见 core/config.py) */
  items: { count: number; max: number }
  panels: {
    total: number
    /** 聚合上限 (单机器人上限 × 机器人数); 没有平台时后端省略该字段 */
    max?: number
    /** 有场景查询失败时 total 只是下限, 不能当作精确值展示 */
    partial: boolean
  }
}
