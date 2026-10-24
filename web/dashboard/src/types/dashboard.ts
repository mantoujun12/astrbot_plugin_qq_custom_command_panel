/**
 * 状态接口 (/status)、配置接口 (/config) 与同步进度流 (/sync/events) 的数据契约，
 * 和 core/web_api.py 的 build_status / export_config 以及 core/panel_syncer.py
 * 的结构化事件一一对应。
 */

export const SCENES = ['c2c', 'group', 'channel', 'dm'] as const

/** 可用场景，和 core/config.py 的 SCENES 对应 */
export type Scene = (typeof SCENES)[number]

/** synced=该场景恰好一个本插件面板，duplicate=同场景多份，missing=没有，failed=查询失败 */
export type SceneState = 'synced' | 'duplicate' | 'missing' | 'failed'

export interface ScenePanelStatus {
  scope: Scene
  state: SceneState
  panel_id?: string
  items_count?: number
}

export interface PlatformStatus {
  /**
   * 平台稳定标识。新版机器人是内部 id（可能是 UUID），兼容配置是备注名；
   * 仅用于去重 / key，展示请用 name，再回退到 appid。
   */
  pf_id: string
  /** 新版机器人备注名；兼容配置或旧响应里可能省略 */
  name?: string
  /** v2=新版机器人配置，legacy=兼容性全局配置；旧响应里可能省略 */
  source?: 'v2' | 'legacy'
  /** 脱敏后的 appid，前端不参与拼写 */
  appid: string
  platform: string
  /** 只列出当前生效的场景 */
  scenes: ScenePanelStatus[]
  /** 平台级失败原因（场景列表整体不可用），此时不要展示同步状态 */
  error?: string
}

export interface StatusResponse {
  plugin: { name: string; version: string }
  platforms: PlatformStatus[]
  /** 当前生效的场景 */
  scenes: Scene[]
  /** max 为 QQ 面板上限，超出会被后台截断（见 core/config.py）*/
  items: { count: number; max: number }
  panels: {
    total: number
    /** 综合上限（平台总数 × 单平台上限）；没有平台时省略该字段 */
    max?: number
    /** 有场景查询失败时 total 只是下限，不能按精确值展示 */
    partial: boolean
  }
}

/** 配置接口返回的平台条目：secret 只回掩码，不回明文 */
export interface ConfigPlatform {
  name: string
  appid: string
  platform: string
  secret_masked: string
  secret_set: boolean
}

export interface ConfigCommand {
  name: string
  desc: string
}

export interface ConfigLimits {
  name_max: number
  desc_max: number
  items_max: number
}

export interface PluginConfigResponse {
  language: string
  /** 插件视图主色，旧版后端可能省略 */
  primary_color?: string
  /** 插件视图辅助色，旧版后端可能省略 */
  secondary_color?: string
  scenes: Scene[]
  available_scenes: Scene[]
  qq_platforms: ConfigPlatform[]
  selected_commands: ConfigCommand[]
  limits: ConfigLimits
}

/** 提交给 /config 的平台条目：secret 留空表示沿用原配置里的值 */
export interface ConfigPlatformPayload {
  name: string
  appid: string
  platform: string
  secret: string
}

export interface PluginConfigPayload {
  language: string
  primary_color?: string
  secondary_color?: string
  scenes: Scene[]
  qq_platforms: ConfigPlatformPayload[]
  selected_commands: ConfigCommand[]
}

/**
 * 提交给 POST /config 的载荷。后端按字段合并，缺省字段沿用已保存的值
 * （见 core/config.py 的 normalize_config_payload），所以每个页面只提交自己负责的字段，
 * 不会把别的页面改过的值覆盖回去。
 */
export type PluginConfigSubmit = Partial<PluginConfigPayload>

/** SSE 同步进度事件，和 PanelSyncer.sync_all 的 on_event 一一对应 */
export interface SyncMessageEvent {
  type: 'message'
  seq: number
  text: string
}

export interface SyncStartEvent {
  type: 'start'
  seq: number
  mode?: 'sync' | 'clear'
  platforms: number
  scenes: number
  items: number
}

export interface SyncPlatformEvent {
  type: 'platform'
  seq: number
  /** 稳定的平台键，用于进度去重，不保证可读 */
  pf_id: string
  /** 机器人备注名，缺失时前端回退到 appid_masked */
  name?: string
  /** 脱敏 appid，name 缺失时的展示回退 */
  appid_masked?: string
  index: number
  total: number
  status: 'ok' | 'error'
  saved: number
  error?: string | null
}

export interface SyncFinishEvent {
  type: 'finish'
  seq: number
  ok: boolean
  reason?: string
  platforms: number
  succeeded: number
  failed: number
  error?: string | null
  result?: Record<string, unknown>
}

export type SyncEvent = SyncMessageEvent | SyncStartEvent | SyncPlatformEvent | SyncFinishEvent

/** 单个平台的同步结果，用于渲染状态标签 */
export interface SyncPlatformState {
  pf_id: string
  name: string
  appid_masked: string
  index: number
  status: 'ok' | 'error'
  saved: number
  error: string
}

/** 页面渲染用的同步运行状态 */
export interface SyncRunState {
  status: 'idle' | 'running' | 'done' | 'failed'
  /** 本轮要同步的平台数，来自 start 事件 */
  platforms: number
  /** 已回报结果的平台数 */
  completed: number
  succeeded: number
  failed: number
  messages: string[]
  platformStates: SyncPlatformState[]
  /** 已收到的最大 seq，重连时用它续订 */
  lastSeq: number
  /** 传输层或后端异常信息 */
  error: string
}
