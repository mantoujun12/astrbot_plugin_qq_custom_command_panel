/**
 * 新版机器人配置的数据访问层与表单纯函数。
 *
 * GET /robots 本地开发时退回 mock；POST 无 bridge 直接抛错，避免把未落库的数据展示成保存成功。
 */

import { getBridge } from '../bridge'
import { SCENES, type ConfigCommand, type ConfigLimits, type Scene } from '../types/dashboard'
import type {
  RobotConfig,
  RobotConfigForm,
  RobotConfigPayload,
  RobotConfigResponse,
  RobotConfigSavePayload,
  RobotSceneConfig,
} from '../types/robotConfig'
import { toPlain } from './serialize'

/** 对应后端 register_web_api 的路径 `/<plugin_name>/robots` */
const ROBOTS_ENDPOINT = 'robots'

/** 与 `bridge.t(key, fallback)` 同形，便于纯函数注入文案 */
export type Translate = (key: string, fallback?: string) => string

/** 本地开发用的机器人配置，仅导出给页面判断与调试使用 */
export const MOCK_ROBOTS: RobotConfigResponse = {
  version: 1,
  available_scenes: [...SCENES],
  limits: { name_max: 14, desc_max: 30, items_max: 20 },
  robots: [
    {
      id: 'robot-demo-1',
      name: '主机器人',
      appid: '1023456789',
      platform: 'qq_official',
      secret_masked: 'abc*****yz',
      secret_set: true,
      scenes: {
        c2c: {
          enabled: true,
          items: [
            { name: 'help', desc: '查看帮助' },
            { name: 'ping', desc: '连通性测试' },
          ],
        },
        group: {
          enabled: true,
          items: [{ name: 'status', desc: '查看运行状态' }],
        },
        channel: { enabled: false, items: [] },
        dm: { enabled: false, items: [] },
      },
    },
    {
      id: 'robot-demo-2',
      name: '测试机器人',
      appid: '1038765432',
      platform: 'qq_official_webhook',
      secret_masked: 'def*****wv',
      secret_set: true,
      scenes: {
        c2c: { enabled: false, items: [] },
        group: {
          enabled: true,
          items: [{ name: 'debug', desc: '调试模式' }],
        },
        channel: { enabled: false, items: [] },
        dm: { enabled: false, items: [] },
      },
    },
  ],
}

/** 校验失败时返回的文案，key 与 fallback 成对维护 */
export const ROBOT_MESSAGES = {
  notLoaded: ['pages.dashboard.robots.notLoaded', '机器人配置尚未载入。'],
  appidRequired: ['pages.dashboard.robots.appidRequired', 'AppID 不能为空。'],
  nameRequired: ['pages.dashboard.robots.nameRequired', '机器人名称不能为空。'],
  nameTooLong: ['pages.dashboard.robots.nameTooLong', '机器人名称超出长度上限。'],
  secretRequired: [
    'pages.dashboard.robots.secretRequired',
    '新机器人必须填写 ClientSecret。',
  ],
  secretRequiredForAppidChange: [
    'pages.dashboard.robots.secretRequiredForAppidChange',
    '修改 AppID 后必须重新填写 ClientSecret。',
  ],
  sceneRequiresItem: [
    'pages.dashboard.robots.sceneRequiresItem',
    '启用的场景至少需要 1 条指令。',
  ],
  sceneItemsTooMany: [
    'pages.dashboard.robots.sceneItemsTooMany',
    '单个场景的指令条目超出上限。',
  ],
  commandNameRequired: [
    'pages.dashboard.robots.commandNameRequired',
    '指令名不能为空。',
  ],
  commandNameTooLong: [
    'pages.dashboard.robots.commandNameTooLong',
    '指令名超出长度上限。',
  ],
  commandDescTooLong: [
    'pages.dashboard.robots.commandDescTooLong',
    '指令描述超出长度上限。',
  ],
} as const

function message(t: Translate, key: keyof typeof ROBOT_MESSAGES): string {
  const [i18nKey, fallback] = ROBOT_MESSAGES[key]
  return t(i18nKey, fallback)
}

export function emptySceneConfig(): RobotSceneConfig {
  return { enabled: false, items: [] }
}

export function emptyRobotDraft(): RobotConfigForm {
  const scenes = {} as Record<Scene, RobotSceneConfig>
  for (const scene of SCENES) {
    scenes[scene] = emptySceneConfig()
  }
  return {
    id: '',
    name: '',
    appid: '',
    platform: 'qq_official',
    secret: '',
    scenes,
  }
}

/** 接口响应转可编辑表单；secret 留空表示沿用原值 */
export function toRobotForm(robot: RobotConfig): RobotConfigForm {
  const scenes = {} as Record<Scene, RobotSceneConfig>
  for (const scene of SCENES) {
    const source = robot.scenes[scene]
    scenes[scene] = source
      ? { enabled: source.enabled, items: source.items.map((item) => ({ ...item })) }
      : emptySceneConfig()
  }
  return {
    id: robot.id,
    name: robot.name,
    appid: robot.appid,
    platform: robot.platform,
    secret: '',
    scenes,
  }
}

/**
 * 已保存机器人是否改动了 AppID。
 *
 * 后端按 appid 复用 secret，AppID 变化后旧 secret 不再适用；新增机器人没有
 * 已保存的 AppID，因此始终返回 false。
 */
export function robotAppidChanged(
  robot: Pick<RobotConfigForm, 'appid'>,
  savedAppid: string,
): boolean {
  const original = savedAppid.trim()
  return original !== '' && robot.appid.trim() !== original
}

export function robotSceneCount(robot: Pick<RobotConfigForm, 'scenes'>): number {
  return SCENES.filter((scene) => robot.scenes[scene]?.enabled).length
}

export function robotItemCount(robot: Pick<RobotConfigForm, 'scenes'>): number {
  return SCENES.reduce((total, scene) => {
    const config = robot.scenes[scene]
    return total + (config?.enabled ? config.items.length : 0)
  }, 0)
}

export function isRobotMock(response: RobotConfigResponse | null | undefined): boolean {
  return response === MOCK_ROBOTS
}

export async function fetchRobots(): Promise<RobotConfigResponse> {
  const bridge = getBridge()
  if (!bridge) {
    return MOCK_ROBOTS
  }
  return (await bridge.apiGet(ROBOTS_ENDPOINT)) as RobotConfigResponse
}

/** 校验结果：通过时同时给出 trim 后、可用于 POST 的载荷 */
export type ValidateRobotResult =
  | { ok: true; payload: RobotConfigPayload }
  | { ok: false; reason: string }

/** 校验已有机器人时补充的上下文 */
export interface ValidateRobotOptions {
  /** 已保存机器人的原 AppID；新增机器人为空 */
  savedAppid?: string
}

/**
 * 提交前的单台机器人本地校验：提前拦截明显错误并规范化提交字段，后端仍会再次校验。
 * id 为空视为新机器人，此时 secret 必填；已有机器人留空 secret 表示沿用原值，
 * 但 AppID 变化后后端无法按新 appid 复用旧 secret，必须重新填写。
 */
export function validateRobotForm(
  robot: RobotConfigForm | null,
  limits: ConfigLimits,
  t: Translate,
  options: ValidateRobotOptions = {},
): ValidateRobotResult {
  if (!robot) {
    return { ok: false, reason: message(t, 'notLoaded') }
  }

  const appid = robot.appid.trim()
  if (!appid) {
    return { ok: false, reason: message(t, 'appidRequired') }
  }

  const name = robot.name.trim()
  if (!name) {
    return { ok: false, reason: message(t, 'nameRequired') }
  }
  if (name.length > limits.name_max) {
    return { ok: false, reason: message(t, 'nameTooLong') }
  }
  const id = robot.id.trim()
  const secret = robot.secret.trim()
  if (!secret) {
    if (!id) {
      return { ok: false, reason: message(t, 'secretRequired') }
    }
    if (robotAppidChanged(robot, options.savedAppid ?? '')) {
      return { ok: false, reason: message(t, 'secretRequiredForAppidChange') }
    }
  }

  const scenes = {} as Record<Scene, RobotSceneConfig>
  for (const scene of SCENES) {
    const source = robot.scenes[scene] ?? emptySceneConfig()
    if (source.items.length > limits.items_max) {
      return { ok: false, reason: message(t, 'sceneItemsTooMany') }
    }
    if (source.enabled && source.items.length === 0) {
      return { ok: false, reason: message(t, 'sceneRequiresItem') }
    }

    const items: ConfigCommand[] = []
    for (const item of source.items) {
      const name = item.name.trim()
      const desc = item.desc.trim()
      if (!name) {
        return { ok: false, reason: message(t, 'commandNameRequired') }
      }
      if (name.length > limits.name_max) {
        return { ok: false, reason: message(t, 'commandNameTooLong') }
      }
      if (desc.length > limits.desc_max) {
        return { ok: false, reason: message(t, 'commandDescTooLong') }
      }
      items.push({ name, desc })
    }
    scenes[scene] = { enabled: source.enabled, items }
  }

  return {
    ok: true,
    payload: {
      id,
      name,
      appid,
      platform: robot.platform.trim(),
      secret,
      scenes,
    },
  }
}

/**
 * 保存机器人配置，返回落库后的完整响应；本地无 bridge 时抛错，不允许伪造成保存成功。
 * payload 可能是响应式对象，先通过 toPlain 快照成纯数据再交给 bridge。
 */
export async function saveRobots(
  payload: RobotConfigSavePayload,
): Promise<RobotConfigResponse> {
  const bridge = getBridge()
  if (!bridge) {
    throw new Error('no backend: robot config saving is unavailable in local dev')
  }
  return (await bridge.apiPost(ROBOTS_ENDPOINT, toPlain(payload))) as RobotConfigResponse
}
