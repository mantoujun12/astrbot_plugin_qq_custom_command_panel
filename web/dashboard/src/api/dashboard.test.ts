import { afterEach, describe, expect, it, vi } from 'vitest'
import { reactive } from 'vue'
import { fetchConfig, fetchStatus, saveConfig } from './dashboard'
import { MOCK_CONFIG, MOCK_STATUS } from './mock'
import { createBridgeStub } from '../test/helpers'
import type {
  PluginConfigPayload,
  PluginConfigResponse,
  StatusResponse,
} from '../types/dashboard'

/** 合法的提交载荷：secret 留空表示沿用原值 */
function configPayload(): PluginConfigPayload {
  return {
    language: 'en-US',
    scenes: ['group'],
    qq_platforms: [
      { name: 'pf1', appid: '1023456789', platform: 'qq_official', secret: '' },
    ],
    selected_commands: [{ name: 'help', desc: '说明' }],
  }
}

afterEach(() => {
  delete window.AstrBotPluginView
  delete window.AstrBotPluginPage
})

describe('fetchStatus', () => {
  it('falls back to the mock without a bridge', async () => {
    await expect(fetchStatus()).resolves.toBe(MOCK_STATUS)
  })

  it('requests the status endpoint without params by default', async () => {
    const bridge = createBridgeStub()
    window.AstrBotPluginView = bridge
    const payload: StatusResponse = { ...MOCK_STATUS, scenes: ['c2c'] }
    vi.mocked(bridge.apiGet).mockResolvedValue(payload)

    await expect(fetchStatus()).resolves.toBe(payload)
    expect(bridge.apiGet).toHaveBeenCalledWith('status', undefined)
  })

  it('passes refresh=1 when asked to bypass the backend cache', async () => {
    const bridge = createBridgeStub()
    window.AstrBotPluginView = bridge

    await fetchStatus({ refresh: true })

    expect(bridge.apiGet).toHaveBeenCalledWith('status', { refresh: 1 })
  })

  it('propagates backend failures instead of falling back to the mock', async () => {
    const bridge = createBridgeStub()
    window.AstrBotPluginView = bridge
    vi.mocked(bridge.apiGet).mockRejectedValue(new Error('status failed'))

    await expect(fetchStatus({ refresh: true })).rejects.toThrow('status failed')
  })
})

describe('fetchConfig', () => {
  it('falls back to the mock without a bridge', async () => {
    await expect(fetchConfig()).resolves.toBe(MOCK_CONFIG)
  })

  it('reads the config endpoint', async () => {
    const bridge = createBridgeStub()
    window.AstrBotPluginView = bridge
    const payload: PluginConfigResponse = { ...MOCK_CONFIG, language: 'en-US' }
    vi.mocked(bridge.apiGet).mockResolvedValue(payload)

    await expect(fetchConfig()).resolves.toBe(payload)
    expect(bridge.apiGet).toHaveBeenCalledWith('config')
  })
})

describe('saveConfig', () => {
  it('refuses to fake a save without a bridge', async () => {
    await expect(saveConfig(configPayload())).rejects.toThrow('no backend')
  })

  it('posts the payload and returns the stored config', async () => {
    const bridge = createBridgeStub()
    window.AstrBotPluginView = bridge
    const payload = configPayload()
    vi.mocked(bridge.apiPost).mockResolvedValue(MOCK_CONFIG)

    const result = await saveConfig(payload)

    expect(result).toBe(MOCK_CONFIG)
    expect(bridge.apiPost).toHaveBeenCalledWith('config', payload)
  })

  it('snapshots a reactive payload into cloneable data before posting', async () => {
    const bridge = createBridgeStub()
    window.AstrBotPluginView = bridge
    vi.mocked(bridge.apiPost).mockResolvedValue(MOCK_CONFIG)

    await saveConfig(reactive(configPayload()))

    const [, body] = vi.mocked(bridge.apiPost).mock.calls[0]
    // 视图传进来的是 Vue 的 Proxy，postMessage 的结构化克隆无法处理
    expect(() => structuredClone(body)).not.toThrow()
    expect(body).toEqual(configPayload())
  })

  it('propagates validation errors from the backend', async () => {
    const bridge = createBridgeStub()
    window.AstrBotPluginView = bridge
    vi.mocked(bridge.apiPost).mockRejectedValue(new Error('language：fr-FR 不是支持的语言'))

    await expect(saveConfig(configPayload())).rejects.toThrow('language')
  })
})
