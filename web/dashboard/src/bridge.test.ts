import { afterEach, describe, expect, it, vi } from 'vitest'
import { getBridge, waitForBridge } from './bridge'
import type { PluginViewBridge } from './bridge'

function createBridge(): PluginViewBridge {
  return {
    ready: vi.fn(async () => ({})),
    getContext: vi.fn(() => null),
    getLocale: vi.fn(() => 'zh-CN'),
    t: vi.fn((key: string, fallback?: string) => fallback ?? key),
    onContext: vi.fn(() => () => {}),
    apiGet: vi.fn(async () => null),
    apiPost: vi.fn(async () => null),
    subscribeSSE: vi.fn(async () => 'sub-1'),
    unsubscribeSSE: vi.fn(async () => ({ subscriptionId: 'sub-1' })),
  }
}

afterEach(() => {
  delete window.AstrBotPluginView
  delete window.AstrBotPluginPage
  vi.useRealTimers()
})

describe('getBridge', () => {
  it('returns null when the SDK is not injected', () => {
    expect(getBridge()).toBeNull()
  })

  it('prefers AstrBotPluginView over AstrBotPluginPage', () => {
    const primary = createBridge()
    const legacy = createBridge()
    window.AstrBotPluginView = primary
    window.AstrBotPluginPage = legacy

    expect(getBridge()).toBe(primary)
  })

  it('falls back to AstrBotPluginPage', () => {
    const legacy = createBridge()
    window.AstrBotPluginPage = legacy

    expect(getBridge()).toBe(legacy)
  })

})

describe('waitForBridge', () => {
  it('resolves immediately when the SDK is already present', async () => {
    const bridge = createBridge()
    window.AstrBotPluginView = bridge

    await expect(waitForBridge(1000)).resolves.toBe(bridge)
  })

  it('resolves once the SDK shows up during polling', async () => {
    vi.useFakeTimers()
    const bridge = createBridge()
    const pending = waitForBridge(1000, 50)

    await vi.advanceTimersByTimeAsync(120)
    window.AstrBotPluginView = bridge
    await vi.advanceTimersByTimeAsync(60)

    await expect(pending).resolves.toBe(bridge)
  })

  it('resolves null after the timeout', async () => {
    vi.useFakeTimers()
    const pending = waitForBridge(200, 50)

    await vi.advanceTimersByTimeAsync(300)

    await expect(pending).resolves.toBeNull()
  })
})
