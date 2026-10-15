import { describe, expect, it } from 'vitest'
import {
  DEFAULT_LIMITS,
  indexSavedPlatforms,
  newCommand,
  newPlatform,
  toForm,
  validateForm,
} from './settingsForm'
import type {
  ConfigLimits,
  ConfigPlatform,
  PluginConfigPayload,
  PluginConfigResponse,
} from '../types/dashboard'

const t = (key: string, fallback?: string): string => fallback ?? key

function response(overrides: Partial<PluginConfigResponse> = {}): PluginConfigResponse {
  return {
    language: 'zh-CN',
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
    ],
    selected_commands: [{ name: 'help', desc: '查看帮助' }],
    limits: DEFAULT_LIMITS,
    ...overrides,
  }
}

function payload(overrides: Partial<PluginConfigPayload> = {}): PluginConfigPayload {
  return {
    language: 'zh-CN',
    scenes: ['c2c', 'group'],
    qq_platforms: [
      { name: '主机器人', appid: '1023456789', platform: 'qq_official', secret: '' },
    ],
    selected_commands: [{ name: 'help', desc: '查看帮助' }],
    ...overrides,
  }
}

function savedPlatform(overrides: Partial<ConfigPlatform> = {}): ConfigPlatform {
  return {
    name: '主机器人',
    appid: '1023456789',
    platform: 'qq_official',
    secret_masked: 'abc*****yz',
    secret_set: true,
    ...overrides,
  }
}

function limits(overrides: Partial<ConfigLimits> = {}): ConfigLimits {
  return { ...DEFAULT_LIMITS, ...overrides }
}

function fail(
  form: PluginConfigPayload | null,
  saved: ConfigPlatform[] = [savedPlatform()],
  config: ConfigLimits = DEFAULT_LIMITS,
): string {
  const result = validateForm(form, saved, config, t)
  expect(result.ok).toBe(false)
  return result.ok ? '' : result.reason
}

describe('toForm', () => {
  it('copies the scenes and commands and clears every secret', () => {
    const form = toForm(response())

    expect(form).toEqual({
      language: 'zh-CN',
      scenes: ['c2c', 'group'],
      qq_platforms: [
        { name: '主机器人', appid: '1023456789', platform: 'qq_official', secret: '' },
      ],
      selected_commands: [{ name: 'help', desc: '查看帮助' }],
    })
  })

  it('never shares arrays or objects with the response', () => {
    const source = response()
    const form = toForm(source)

    expect(form.scenes).not.toBe(source.scenes)
    expect(form.selected_commands[0]).not.toBe(source.selected_commands[0])
    expect(form.qq_platforms[0]).not.toBe(source.qq_platforms[0])
  })
})

describe('indexSavedPlatforms', () => {
  it('indexes by appid and tolerates a missing config', () => {
    expect(indexSavedPlatforms(undefined).size).toBe(0)
    expect(indexSavedPlatforms([savedPlatform()]).get('1023456789')?.secret_set).toBe(true)
  })
})

describe('new rows', () => {
  it('starts a platform with the default type and no secret', () => {
    expect(newPlatform()).toEqual({
      name: '',
      appid: '',
      platform: 'qq_official',
      secret: '',
    })
  })

  it('starts an empty command row', () => {
    expect(newCommand()).toEqual({ name: '', desc: '' })
  })
})

describe('validateForm', () => {
  it('reports a config that has not loaded yet', () => {
    expect(fail(null)).toBe('配置尚未载入。')
  })

  it('accepts a form that matches the saved config', () => {
    const result = validateForm(payload(), [savedPlatform()], DEFAULT_LIMITS, t)

    expect(result.ok).toBe(true)
  })

  it('keeps the payload language and scenes', () => {
    const result = validateForm(
      payload({ language: 'en-US', scenes: ['group'] }),
      [savedPlatform()],
      DEFAULT_LIMITS,
      t,
    )

    expect(result.ok && result.payload.language).toBe('en-US')
    expect(result.ok && result.payload.scenes).toEqual(['group'])
  })

  it('rejects more commands than the backend allows', () => {
    const form = payload({
      selected_commands: [
        { name: 'help', desc: '' },
        { name: 'ping', desc: '' },
      ],
    })

    expect(fail(form, [savedPlatform()], limits({ items_max: 1 }))).toBe(
      '指令条目超出上限。',
    )
  })

  it('accepts a command list that is exactly at the limit', () => {
    const form = payload({ selected_commands: [{ name: 'help', desc: '' }] })

    expect(validateForm(form, [savedPlatform()], limits({ items_max: 1 }), t).ok).toBe(
      true,
    )
  })

  it('rejects an empty command name', () => {
    const form = payload({ selected_commands: [{ name: '   ', desc: '' }] })

    expect(fail(form)).toBe('指令名不能为空。')
  })

  it('rejects a command name over the length limit', () => {
    const form = payload({
      selected_commands: [{ name: 'x'.repeat(DEFAULT_LIMITS.name_max + 1), desc: '' }],
    })

    expect(fail(form)).toBe('指令名超出长度上限。')
  })

  it('rejects a command description over the length limit', () => {
    const form = payload({
      selected_commands: [
        { name: 'help', desc: 'y'.repeat(DEFAULT_LIMITS.desc_max + 1) },
      ],
    })

    expect(fail(form)).toBe('指令描述超出长度上限。')
  })

  it('rejects a platform without an appid', () => {
    const form = payload({
      qq_platforms: [{ name: '', appid: '  ', platform: 'qq_official', secret: 's' }],
    })

    expect(fail(form)).toBe('平台 appid 不能为空。')
  })

  it('rejects a new platform without a secret', () => {
    const form = payload({
      qq_platforms: [
        { name: '新机器人', appid: '1038765432', platform: 'qq_official', secret: '' },
      ],
    })

    expect(fail(form)).toBe('新增平台必须填写 ClientSecret。')
  })

  it('keeps an existing secret when the field is left empty', () => {
    const form = payload()
    const result = validateForm(form, [savedPlatform()], DEFAULT_LIMITS, t)

    expect(result.ok && result.payload.qq_platforms).toEqual([
      { name: '主机器人', appid: '1023456789', platform: 'qq_official', secret: '' },
    ])
  })

  it('accepts a new platform that brings its own secret', () => {
    const form = payload({
      qq_platforms: [
        { name: '新机器人', appid: '1038765432', platform: 'qq_official_webhook', secret: ' sec ' },
      ],
    })
    const result = validateForm(form, [], DEFAULT_LIMITS, t)

    expect(result.ok && result.payload.qq_platforms[0]).toEqual({
      name: '新机器人',
      appid: '1038765432',
      platform: 'qq_official_webhook',
      secret: 'sec',
    })
  })

  it('trims every submitted field', () => {
    const form = payload({
      qq_platforms: [
        { name: '  主机器人  ', appid: ' 1023456789 ', platform: 'qq_official', secret: '' },
      ],
      selected_commands: [{ name: ' help ', desc: ' 查看帮助 ' }],
    })
    const result = validateForm(form, [savedPlatform()], DEFAULT_LIMITS, t)

    expect(result.ok && result.payload).toEqual({
      language: 'zh-CN',
      scenes: ['c2c', 'group'],
      qq_platforms: [
        { name: '主机器人', appid: '1023456789', platform: 'qq_official', secret: '' },
      ],
      selected_commands: [{ name: 'help', desc: '查看帮助' }],
    })
  })
})
