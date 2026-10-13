/**
 * 状态概览 (/status) 的数据契约。
 *
 * 插件后端目前还没有注册任何 Web API, 这里先把契约固定下来, 后续在
 * main.py 里用 `context.register_web_api` 按同样字段返回。字段都能从 core
 * 现有的公开方法得到, 不需要改核心逻辑:
 *
 *   build_clients()         -> platforms / source
 *   get_enabled_scenes()    -> scenes
 *   get_selected_commands() -> items
 *   list_all_panels()       -> 各场景线上状态 (含失败场景)
 *
 * 注意: 该接口默认查询线上, 每个平台会对 4 个场景各调一次 QQ API, 属于慢请求。
 */

export const SCENES = ['c2c', 'group', 'channel', 'dm'] as const

/** 面板生效场景, 与 core/config.py 的 SCENES 对应 */
export type Scene = (typeof SCENES)[number]

/** 平台凭证来源: 插件 schema 的 qq_platforms, 或 AstrBot 平台配置 */
export type PlatformSource = 'schema' | 'context'

/** synced=线上有本插件的面板, missing=该场景线上没有, failed=查询该场景失败 */
export type SceneState = 'synced' | 'missing' | 'failed'

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
  panels: { total: number; max: number }
}
