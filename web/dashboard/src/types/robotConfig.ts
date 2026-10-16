/** 新版机器人配置接口（GET / POST /robots）的数据契约 */

import type { ConfigCommand, ConfigLimits, Scene } from './dashboard'

export interface RobotSceneConfig {
  enabled: boolean
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

export interface RobotConfigResponse {
  version: number
  robots: RobotConfig[]
  available_scenes: Scene[]
  limits: ConfigLimits
}

export interface RobotConfigPayload {
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
