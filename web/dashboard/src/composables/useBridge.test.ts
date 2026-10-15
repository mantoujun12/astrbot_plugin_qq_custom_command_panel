import { describe, expect, it, vi } from 'vitest'
import type { PluginViewContext } from '../bridge'
import { flush, installBridge, waitUntil } from '../test/helpers'

type UseBridge = typeof import('./useBridge').useBridge

/** bridge 与上下文是模块级单例，每个用例都拿一份全新的模块 */
async function loadUseBridge(): Promise<UseBridge> {
  vi.resetModules()
  return (await import('./useBridge')).useBridge
}

describe('useBridge', () => {
  it('connects to an injected bridge and follows the host context', async () => {
    const context: PluginViewContext = { locale: 'en-US', isDark: true }
    const bridge = installBridge({
      ready: vi.fn(async () => context),
      getContext: vi.fn(() => context),
      t: vi.fn((key: string, fallback?: string) => `host:${fallback ?? key}`),
    })

    const useBridge = await loadUseBridge()
    const app = useBridge()

    // bootstrap 是异步的：先等它连上，期间视图自己决定渲染什么
    expect(app.ready.value).toBe(false)
    expect(app.hasBackend.value).toBe(false)
    await waitUntil(() => app.ready.value)

    expect(app.ready.value).toBe(true)
    expect(app.hasBackend.value).toBe(true)
    expect(app.locale.value).toBe('en-US')
    expect(app.isDark.value).toBe(true)
    expect(app.t('pages.dashboard.title', '指令面板')).toBe('host:指令面板')
    expect(bridge.onContext).toHaveBeenCalledTimes(1)
  })

  it('only bootstraps once for every caller', async () => {
    const bridge = installBridge()
    const useBridge = await loadUseBridge()

    const first = useBridge()
    const second = useBridge()
    await waitUntil(() => second.ready.value)

    expect(bridge.ready).toHaveBeenCalledTimes(1)
    expect(bridge.onContext).toHaveBeenCalledTimes(1)
    expect(second.ready.value).toBe(true)
    expect(first.hasBackend.value).toBe(second.hasBackend.value)
  })

  it('keeps rendering when the host context fails to load', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const bridge = installBridge({
      ready: vi.fn(async () => {
        throw new Error('bridge exploded')
      }),
      getContext: vi.fn(() => ({ locale: 'zh-CN' })),
    })

    const useBridge = await loadUseBridge()
    const app = useBridge()
    await waitUntil(() => app.ready.value)

    // bridge 本身可用，只是上下文读失败：按默认主题继续渲染
    expect(app.ready.value).toBe(true)
    expect(app.hasBackend.value).toBe(true)
    expect(app.locale.value).toBe('zh-CN')
    expect(app.isDark.value).toBe(false)
    expect(bridge.onContext).toHaveBeenCalledTimes(1)
    expect(warn).toHaveBeenCalledWith(
      '[qq-command-panel] bridge ready() failed',
      expect.any(Error),
    )
  })

  it('accepts the ready() snapshot when getContext() has nothing yet', async () => {
    installBridge({
      ready: vi.fn(async () => ({ locale: 'en-US', isDark: true })),
      getContext: vi.fn(() => null),
    })

    const useBridge = await loadUseBridge()
    const app = useBridge()
    await waitUntil(() => app.ready.value)

    expect(app.locale.value).toBe('en-US')
    expect(app.isDark.value).toBe(true)
  })

  it('prefers the freshest getContext() over the ready() snapshot', async () => {
    installBridge({
      ready: vi.fn(async () => ({ locale: 'en-US', isDark: true })),
      getContext: vi.fn(() => ({ locale: 'zh-CN', isDark: false })),
    })

    const useBridge = await loadUseBridge()
    const app = useBridge()
    await waitUntil(() => app.ready.value)

    expect(app.locale.value).toBe('zh-CN')
    expect(app.isDark.value).toBe(false)
  })

  it('follows later context changes pushed by the host', async () => {
    const handlers: (() => void)[] = []
    let current: PluginViewContext | null = { locale: 'zh-CN', isDark: false }
    installBridge({
      getContext: vi.fn(() => current),
      onContext: vi.fn((handler: () => void) => {
        handlers.push(handler)
        return () => {}
      }),
    })

    const useBridge = await loadUseBridge()
    const app = useBridge()
    await waitUntil(() => app.ready.value)
    expect(app.isDark.value).toBe(false)

    current = { locale: 'en-US', isDark: true }
    handlers[0]?.()
    await flush()

    expect(app.locale.value).toBe('en-US')
    expect(app.isDark.value).toBe(true)
  })

  it('ignores a context change that carries no context', async () => {
    const handlers: (() => void)[] = []
    let current: PluginViewContext | null = { locale: 'zh-CN', isDark: true }
    installBridge({
      getContext: vi.fn(() => current),
      onContext: vi.fn((handler: () => void) => {
        handlers.push(handler)
        return () => {}
      }),
    })

    const useBridge = await loadUseBridge()
    const app = useBridge()
    await waitUntil(() => app.ready.value)

    current = null
    handlers[0]?.()
    await flush()

    expect(app.locale.value).toBe('zh-CN')
    expect(app.isDark.value).toBe(true)
  })

  it('uses the host pre-injected dark theme before the bridge arrives', async () => {
    document.documentElement.dataset.theme = 'dark'
    const useBridge = await loadUseBridge()

    expect(useBridge().isDark.value).toBe(true)
  })

  it('uses the host pre-injected light theme before the bridge arrives', async () => {
    document.documentElement.dataset.theme = 'light'
    const useBridge = await loadUseBridge()

    expect(useBridge().isDark.value).toBe(false)
  })

  it('follows the system preference when the host injects no theme', async () => {
    vi.spyOn(window, 'matchMedia').mockReturnValue({ matches: true } as MediaQueryList)
    const useBridge = await loadUseBridge()

    expect(useBridge().isDark.value).toBe(true)
  })

  it('renders as a local dev page when no bridge shows up', async () => {
    const useBridge = await loadUseBridge()
    const app = useBridge()
    await waitUntil(() => app.ready.value)

    // dev 下等 300ms 就放行，不再空转等宿主
    expect(app.ready.value).toBe(true)
    expect(app.hasBackend.value).toBe(false)
    expect(app.t('pages.dashboard.title', '指令面板')).toBe('指令面板')
    expect(app.locale.value).toBe('zh-CN')
  })

  it('keeps waiting for a late bridge in production', async () => {
    vi.useFakeTimers()
    vi.stubEnv('DEV', false)
    const useBridge = await loadUseBridge()
    const app = useBridge()

    // 首轮 3s 超时内宿主没注入：视图先不放行，免得先渲染 mock 再被真实数据替换
    await vi.advanceTimersByTimeAsync(3_100)
    expect(app.ready.value).toBe(false)
    expect(app.hasBackend.value).toBe(false)

    const bridge = installBridge()
    await vi.advanceTimersByTimeAsync(600)

    expect(app.hasBackend.value).toBe(true)
    expect(app.ready.value).toBe(true)
    expect(bridge.onContext).toHaveBeenCalledTimes(1)
  })

  it('gives up on the bridge once the production retry window is over', async () => {
    vi.useFakeTimers()
    vi.stubEnv('DEV', false)
    const useBridge = await loadUseBridge()
    const app = useBridge()

    await vi.advanceTimersByTimeAsync(3_100)
    await vi.advanceTimersByTimeAsync(30_100)

    expect(app.ready.value).toBe(true)
    expect(app.hasBackend.value).toBe(false)
  })
})
