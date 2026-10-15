/**
 * 设置页的表单逻辑：接口响应转可编辑表单、以及提交前的本地校验。
 *
 * 这些函数只依赖入参与注入的翻译函数，抽出来之后校验分支可以直接单测，
 * 不用绕 DOM 去点表单（见同目录 settingsForm.test.ts）。
 * 校验语义与后端 core/config.py 的 normalize_config_payload 对齐。
 */

import type {
  ConfigCommand,
  ConfigLimits,
  ConfigPlatform,
  ConfigPlatformPayload,
  PluginConfigPayload,
  PluginConfigResponse,
} from '../types/dashboard'

/** 后端没给 limits 时的兜底，与 core/config.py 的默认上限一致 */
export const DEFAULT_LIMITS: ConfigLimits = { name_max: 14, desc_max: 30, items_max: 20 }

/** 与 `bridge.t(key, fallback)` 同形，便于在纯函数里取文案 */
export type Translate = (key: string, fallback?: string) => string

/** 校验不通过时返回给页面展示的文案；key 与 fallback 成对维护，i18n 对账用例会遍历校验 */
export const MESSAGES = {
  notLoaded: ['pages.dashboard.settings.notLoaded', '配置尚未载入。'],
  commandsTooMany: ['pages.dashboard.settings.commandsTooMany', '指令条目超出上限。'],
  commandNameRequired: ['pages.dashboard.settings.commandNameRequired', '指令名不能为空。'],
  commandNameTooLong: ['pages.dashboard.settings.commandNameTooLong', '指令名超出长度上限。'],
  commandDescTooLong: [
    'pages.dashboard.settings.commandDescTooLong',
    '指令描述超出长度上限。',
  ],
  platformAppidRequired: [
    'pages.dashboard.settings.platformAppidRequired',
    '平台 appid 不能为空。',
  ],
  platformSecretRequired: [
    'pages.dashboard.settings.platformSecretRequired',
    '新增平台必须填写 ClientSecret。',
  ],
} as const

function message(t: Translate, key: keyof typeof MESSAGES): string {
  const [i18nKey, fallback] = MESSAGES[key]
  return t(i18nKey, fallback)
}

/** 接口响应 -> 可编辑表单：secret 一律留空，留空表示沿用原值 */
export function toForm(source: PluginConfigResponse): PluginConfigPayload {
  return {
    language: source.language,
    scenes: [...source.scenes],
    qq_platforms: source.qq_platforms.map((platform) => ({
      name: platform.name,
      appid: platform.appid,
      platform: platform.platform,
      secret: '',
    })),
    selected_commands: source.selected_commands.map((command) => ({ ...command })),
  }
}

/**
 * 已保存平台按 appid 建索引。
 *
 * 新增/删除行会改变下标，占位与提示必须按 appid 跟随当前行，不能按下标取。
 */
export function indexSavedPlatforms(
  platforms: readonly ConfigPlatform[] | undefined,
): Map<string, ConfigPlatform> {
  return new Map((platforms ?? []).map((platform) => [platform.appid, platform]))
}

/** 新增平台行的初始值 */
export function newPlatform(): ConfigPlatformPayload {
  return { name: '', appid: '', platform: 'qq_official', secret: '' }
}

/** 新增指令行的初始值 */
export function newCommand(): ConfigCommand {
  return { name: '', desc: '' }
}

/** 校验结果：通过时同时给出 trim 之后的提交载荷 */
export type ValidateResult =
  | { ok: true; payload: PluginConfigPayload }
  | { ok: false; reason: string }

/**
 * 提交前的本地校验。
 *
 * 尽早给出可读提示，后端仍会再校验一次（错误响应由调用方展示）。
 * 通过时返回规范化载荷：指令名/描述与平台字段都已 trim。
 */
export function validateForm(
  payload: PluginConfigPayload | null,
  savedPlatforms: readonly ConfigPlatform[],
  limits: ConfigLimits,
  t: Translate,
): ValidateResult {
  if (!payload) {
    return { ok: false, reason: message(t, 'notLoaded') }
  }
  if (payload.selected_commands.length > limits.items_max) {
    return { ok: false, reason: message(t, 'commandsTooMany') }
  }

  const commands: ConfigCommand[] = []
  for (const command of payload.selected_commands) {
    if (!command.name.trim()) {
      return { ok: false, reason: message(t, 'commandNameRequired') }
    }
    if (command.name.length > limits.name_max) {
      return { ok: false, reason: message(t, 'commandNameTooLong') }
    }
    if (command.desc.length > limits.desc_max) {
      return { ok: false, reason: message(t, 'commandDescTooLong') }
    }
    commands.push({ name: command.name.trim(), desc: command.desc.trim() })
  }

  const saved = indexSavedPlatforms(savedPlatforms)
  const platforms: ConfigPlatformPayload[] = []
  for (const platform of payload.qq_platforms) {
    const appid = platform.appid.trim()
    if (!appid) {
      return { ok: false, reason: message(t, 'platformAppidRequired') }
    }
    if (!platform.secret.trim() && !saved.get(appid)?.secret_set) {
      return { ok: false, reason: message(t, 'platformSecretRequired') }
    }
    platforms.push({
      name: platform.name.trim(),
      appid,
      platform: platform.platform,
      secret: platform.secret.trim(),
    })
  }

  return {
    ok: true,
    payload: {
      language: payload.language,
      scenes: [...payload.scenes],
      qq_platforms: platforms,
      selected_commands: commands,
    },
  }
}
