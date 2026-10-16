import { afterEach, describe, expect, it, vi } from 'vitest'
import { reactive } from 'vue'
import { createBridgeStub } from '../test/helpers'
import { SCENES, type ConfigLimits } from '../types/dashboard'
import type {
  RobotConfigForm,
  RobotConfigResponse,
  RobotConfigSavePayload,
} from '../types/robotConfig'
import {
  MOCK_ROBOTS,
  emptyRobotDraft,
  emptySceneConfig,
  fetchRobots,
  isRobotMock,
  robotItemCount,
  robotSceneCount,
  saveRobots,
  toRobotForm,
  validateRobotForm,
} from './robots'

const LIMITS: ConfigLimits = { name_max: 14, desc_max: 30, items_max: 20 }

/** 测试翻译函数回退到 fallback，便于直接断言校验结果 */
const t = (key: string, fallback?: string): string => fallback ?? key

function responseFixture(): RobotConfigResponse {
  return {
    version: 1,
    available_scenes: [...SCENES],
    limits: LIMITS,
    robots: [
      {
        id: 'robot-1',
        name: '主机器人',
        appid: '1023456789',
        platform: 'qq_official',
        secret_masked: 'abc*****yz',
        secret_set: true,
        scenes: {
          c2c: { enabled: true, items: [{ name: 'help', desc: '查看帮助' }] },
          group: { enabled: false, items: [] },
          channel: { enabled: false, items: [] },
          dm: { enabled: false, items: [] },
        },
      },
    ],
  }
}

function robotForm(): RobotConfigForm {
  return {
    id: 'robot-1',
    name: '主机器人',
    appid: '1023456789',
    platform: 'qq_official',
    secret: '',
    scenes: {
      c2c: { enabled: true, items: [{ name: 'help', desc: '查看帮助' }] },
      group: { enabled: false, items: [] },
      channel: { enabled: false, items: [] },
      dm: { enabled: false, items: [] },
    },
  }
}

afterEach(() => {
  delete window.AstrBotPluginView
  delete window.AstrBotPluginPage
})

describe('fetchRobots', () => {
  it('falls back to the mock without a bridge and marks the response as mock', async () => {
    const response = await fetchRobots()

    expect(response).toBe(MOCK_ROBOTS)
    expect(isRobotMock(response)).toBe(true)
  })

  it('reads the robots endpoint when a bridge exists', async () => {
    const bridge = createBridgeStub()
    const response = responseFixture()
    window.AstrBotPluginView = bridge
    vi.mocked(bridge.apiGet).mockResolvedValue(response)

    await expect(fetchRobots()).resolves.toBe(response)
    expect(bridge.apiGet).toHaveBeenCalledWith('robots')
    expect(isRobotMock(response)).toBe(false)
  })

  it('propagates backend failures instead of silently using the mock', async () => {
    const bridge = createBridgeStub()
    window.AstrBotPluginView = bridge
    vi.mocked(bridge.apiGet).mockRejectedValue(new Error('robots failed'))

    await expect(fetchRobots()).rejects.toThrow('robots failed')
  })
})

describe('saveRobots', () => {
  it('refuses to fake a save without a bridge', async () => {
    const payload: RobotConfigSavePayload = { version: 1, robots: [robotForm()] }

    await expect(saveRobots(payload)).rejects.toThrow('no backend')
  })

  it('posts the payload and returns the stored response', async () => {
    const bridge = createBridgeStub()
    const response = responseFixture()
    const payload: RobotConfigSavePayload = { version: response.version, robots: [robotForm()] }
    window.AstrBotPluginView = bridge
    vi.mocked(bridge.apiPost).mockResolvedValue(response)

    await expect(saveRobots(payload)).resolves.toBe(response)
    expect(bridge.apiPost).toHaveBeenCalledWith('robots', payload)
  })

  it('snapshots a reactive payload before posting', async () => {
    const bridge = createBridgeStub()
    window.AstrBotPluginView = bridge
    vi.mocked(bridge.apiPost).mockResolvedValue(responseFixture())

    await saveRobots(reactive({ version: 1, robots: [robotForm()] }))

    const [, body] = vi.mocked(bridge.apiPost).mock.calls[0]
    expect(() => structuredClone(body)).not.toThrow()
    expect(body).toEqual({ version: 1, robots: [robotForm()] })
  })
})

describe('robot form helpers', () => {
  it('builds empty scene and robot drafts with every scene disabled', () => {
    expect(emptySceneConfig()).toEqual({ enabled: false, items: [] })

    const draft = emptyRobotDraft()

    expect(draft.id).toBe('')
    expect(draft.secret).toBe('')
    expect(Object.keys(draft.scenes).sort()).toEqual([...SCENES].sort())
    for (const scene of SCENES) {
      expect(draft.scenes[scene]).toEqual({ enabled: false, items: [] })
    }
  })

  it('converts a response robot to an editable form without exposing a secret', () => {
    const source = responseFixture().robots[0]
    const form = toRobotForm(source)

    expect(form.secret).toBe('')
    expect(form.scenes.c2c.items).toEqual([{ name: 'help', desc: '查看帮助' }])
    expect(form.scenes.c2c.items).not.toBe(source.scenes.c2c.items)
  })

  it('counts enabled scenes and items in enabled scenes only', () => {
    const form = robotForm()
    form.scenes.group = { enabled: true, items: [{ name: 'ping', desc: '' }] }
    form.scenes.channel = { enabled: false, items: [{ name: 'hidden', desc: '' }] }

    expect(robotSceneCount(form)).toBe(2)
    expect(robotItemCount(form)).toBe(2)
  })
})

describe('validateRobotForm', () => {
  it('requires appid', () => {
    const form = robotForm()
    form.appid = '   '

    expect(validateRobotForm(form, LIMITS, t)).toEqual({
      ok: false,
      reason: 'AppID 不能为空。',
    })
  })

  it('requires a non-empty robot name within the limit', () => {
    const missing = robotForm()
    missing.name = ' '
    expect(validateRobotForm(missing, LIMITS, t)).toEqual({
      ok: false,
      reason: '机器人名称不能为空。',
    })

    const tooLong = robotForm()
    tooLong.name = 'x'.repeat(LIMITS.name_max + 1)
    expect(validateRobotForm(tooLong, LIMITS, t)).toEqual({
      ok: false,
      reason: '机器人名称超出长度上限。',
    })
  })

  it('requires secret for a new robot but allows an existing robot to keep it', () => {
    const draft = emptyRobotDraft()
    draft.name = '新机器人'
    draft.appid = '1023456789'

    expect(validateRobotForm(draft, LIMITS, t)).toEqual({
      ok: false,
      reason: '新机器人必须填写 ClientSecret。',
    })

    expect(validateRobotForm(robotForm(), LIMITS, t).ok).toBe(true)
  })

  it('requires at least one item for every enabled scene', () => {
    const form = robotForm()
    form.scenes.c2c = { enabled: true, items: [] }

    expect(validateRobotForm(form, LIMITS, t)).toEqual({
      ok: false,
      reason: '启用的场景至少需要 1 条指令。',
    })
  })

  it('rejects a scene above the item limit', () => {
    const form = robotForm()
    const limits: ConfigLimits = { ...LIMITS, items_max: 1 }
    form.scenes.c2c.items.push({ name: 'ping', desc: '' })

    expect(validateRobotForm(form, limits, t)).toEqual({
      ok: false,
      reason: '单个场景的指令条目超出上限。',
    })
  })

  it('rejects empty, overlong command names and overlong descriptions', () => {
    const emptyName = robotForm()
    emptyName.scenes.c2c.items[0].name = ' '
    expect(validateRobotForm(emptyName, LIMITS, t).ok).toBe(false)

    const longName = robotForm()
    longName.scenes.c2c.items[0].name = 'x'.repeat(LIMITS.name_max + 1)
    expect(validateRobotForm(longName, LIMITS, t)).toEqual({
      ok: false,
      reason: '指令名超出长度上限。',
    })

    const longDesc = robotForm()
    longDesc.scenes.c2c.items[0].desc = 'x'.repeat(LIMITS.desc_max + 1)
    expect(validateRobotForm(longDesc, LIMITS, t)).toEqual({
      ok: false,
      reason: '指令描述超出长度上限。',
    })
  })

  it('returns trimmed, normalized fields when validation passes', () => {
    const form = robotForm()
    form.name = ' 主机器人 '
    form.appid = ' 1023456789 '
    form.scenes.c2c.items[0] = { name: ' help ', desc: ' 查看帮助 ' }
    form.scenes.group = { enabled: true, items: [{ name: ' ping ', desc: ' ' }] }

    const result = validateRobotForm(form, LIMITS, t)

    expect(result).toEqual({
      ok: true,
      payload: {
        id: 'robot-1',
        name: '主机器人',
        appid: '1023456789',
        platform: 'qq_official',
        secret: '',
        scenes: {
          c2c: { enabled: true, items: [{ name: 'help', desc: '查看帮助' }] },
          group: { enabled: true, items: [{ name: 'ping', desc: '' }] },
          channel: { enabled: false, items: [] },
          dm: { enabled: false, items: [] },
        },
      },
    })
  })

  it('rejects a null form before reading limits', () => {
    expect(validateRobotForm(null, LIMITS, t)).toEqual({
      ok: false,
      reason: '机器人配置尚未载入。',
    })
  })
})



