import { afterEach, describe, expect, it, vi } from 'vitest'
import { fetchStatus } from './dashboard'
import { MOCK_STATUS } from './mock'
import type { PluginViewBridge } from '../bridge'
import type { StatusResponse } from '../types/dashboard'

function createBridge(): PluginViewBridge {
  return {
    ready: vi.fn(async () => ({})),
    getContext: vi.fn(() => null),
    getLocale: vi.fn(() => 'zh-CN'),
    t: vi.fn((key: string, fallback?: string) => fallback ?? key),
    onContext: vi.fn(() => () => {}),
    apiGet: vi.fn(async () => null),
    apiPost: vi.fn(async () => null),
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
    const bridge = createBridge()
    window.AstrBotPluginView = bridge
    const payload: StatusResponse = { ...MOCK_STATUS, scenes: ['c2c'] }
    vi.mocked(bridge.apiGet).mockResolvedValue(payload)

    await expect(fetchStatus()).resolves.toBe(payload)
    expect(bridge.apiGet).toHaveBeenCalledWith('status', undefined)
  })

  it('passes refresh=1 when asked to bypass the backend cache', async () => {
    const bridge = createBridge()
    window.AstrBotPluginView = bridge

    await fetchStatus({ refresh: true })

    expect(bridge.apiGet).toHaveBeenCalledWith('status', { refresh: 1 })
  })

  it('propagates backend failures instead of falling back to the mock', async () => {
    const bridge = createBridge()
    window.AstrBotPluginView = bridge
    vi.mocked(bridge.apiGet).mockRejectedValue(new Error('status failed'))

    await expect(fetchStatus({ refresh: true })).rejects.toThrow('status failed')
  })
})
