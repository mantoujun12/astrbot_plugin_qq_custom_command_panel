/**
 * 新版机器人配置接口（GET / POST /robots）的数据契约。
 *
 * 每台机器人独立维护各场景的启用状态与指令条目；secret 只回掩码，
 * 提交时留空表示沿用后端已有值。
 */

import type { ConfigCommand, ConfigLimits, Scene } from './dashboard'

/** 单个场景下的机器人指令面板配置 */
export interface RobotSceneConfig {
  /** 该场景是否启用指令面板 */
  enabled: boolean
  /** 写入该场景面板的指令条目 */
  items: ConfigCommand[]
}

/** GET /robots 返回的单台机器人配置，secret 只含掩码 */
export interface RobotConfig {
  /** 新建机器人的 id 为空字符串；已有机器人使用后端生成的 id */
  id: string
  name: string
  appid: string
  platform: string
  secret_masked: string
  secret_set: boolean
  scenes: Record<Scene, RobotSceneConfig>
}

/** GET /robots 的完整响应 */
export interface RobotConfigResponse {
  version: number
  robots: RobotConfig[]
  available_scenes: Scene[]
  limits: ConfigLimits
}

/** POST /robots 中单台机器人的可编辑载荷 */
export interface RobotConfigPayload {
  /** 新机器人为空字符串，已有机器人保留原 id */
  id: string
  name: string
  appid: string
  platform: string
  /** 留空表示沿用已有值 */
  secret: string
  scenes: Record<Scene, RobotSceneConfig>
}

/** POST /robots 的完整载荷，version 用于后端做配置版本校验 */
export interface RobotConfigSavePayload {
  version: number
  robots: RobotConfigPayload[]
}

/** 与接口载荷结构一致的表单别名，避免页面层再维护一套重复类型 */
export type RobotConfigForm = RobotConfigPayload


