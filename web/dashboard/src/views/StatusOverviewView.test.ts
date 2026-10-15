import { describe, expect, it, vi } from 'vitest'
import type { PluginViewSSEHandlers } from '../bridge'
import type { SyncEvent, StatusResponse } from '../types/dashboard'
import { flush, installBridge, waitUntil, mountView } from '../test/helpers'

vi.mock('../api/dashboard', () => ({
  fetchStatus: vi.fn(),
  fetchConfig: vi.fn(),
  saveConfig: vi.fn(),
}))

function statusFixture(overrides: Partial<StatusResponse> = {}): StatusResponse {
  return {
    plugin: { name: 'astrbot_plugin_qq_custom_command_panel', version: 'v0.5.0' },
    scenes: ['c2c', 'group'],
    items: { count: 3, max: 20 },
    panels: { total: 5, max: 40, partial: false },
    platforms: [
      {
        pf_id: '主机器人',
        appid: '102*****89',
        platform: 'qq_official',
        scenes: [{ scope: 'c2c', state: 'synced', panel_id: 'panel_1a2b3c', items_count: 3 }],
      },
    ],
    ...overrides,
  }
}

function deferred<T>(): { promise: Promise<T>; resolve(value: T): void } {
  let resolve = (_value: T): void => {}
  const promise = new Promise<T>((next) => {
    resolve = next
  })
  return { promise, resolve }
}

/**
 * 状态页的 useBridge / useSyncRun 都是模块级单例，每个用例先重置模块再动态
 * 引入，这样 bridge 与首次加载都能按用例配置（注意：mock 也要在同一批里 import）。
 */
async function loadStatusView(options: { withBackend?: boolean } = {}) {
  const bridge = options.withBackend === false ? null : installBridge()
  vi.resetModules()
  const api = await import('../api/dashboard')
  const { default: StatusOverviewView } = await import('./StatusOverviewView.vue')

  return {
    bridge,
    api,
    async mount() {
      const wrapper = mountView(StatusOverviewView)
      // ready 之后视图才会拉状态：等真实发生的请求，而不是 sleep 一个固定值
      await waitUntil(() => vi.mocked(api.fetchStatus).mock.calls.length > 0)
      await flush()
      return wrapper
    },
  }
}

describe('StatusOverviewView', () => {
  it('loads the status and renders the overview cards', async () => {
    const { api, mount } = await loadStatusView()
    vi.mocked(api.fetchStatus).mockResolvedValue(statusFixture())

    const wrapper = await mount()

    expect(api.fetchStatus).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('状态概览')
    // 平台数 / 场景数 / 指令条目 / 线上面板
    expect(wrapper.findAll('.qc-metric-value').map((node) => node.text())).toEqual([
      '1',
      '2',
      '3',
      '5',
    ])
    expect(wrapper.text()).toContain('主机器人')
    expect(wrapper.text()).toContain('已同步')
  })

  it('shows the partial note when some scenes failed to query', async () => {
    const { api, mount } = await loadStatusView()
    vi.mocked(api.fetchStatus).mockResolvedValue(
      statusFixture({ panels: { total: 5, max: 40, partial: true } }),
    )

    const wrapper = await mount()

    expect(wrapper.text()).toContain('部分场景查询失败，该值为下限')
  })

  it('keeps the loading indicator up until the slow request answers', async () => {
    const { api, mount } = await loadStatusView()
    const pending = deferred<StatusResponse>()
    vi.mocked(api.fetchStatus).mockReturnValue(pending.promise)

    const wrapper = await mount()
    // 页面自己那条：Vuetify 的每张 v-card 都常驻一条隐藏的 v-card__loader，
    // 只能按「页面容器下的进度条」来定位
    expect(wrapper.find('.qc-page > .v-progress-linear').exists()).toBe(true)

    pending.resolve(statusFixture())
    await flush()

    expect(wrapper.find('.qc-page > .v-progress-linear').exists()).toBe(false)
    expect(wrapper.findAll('.qc-metric-value')).toHaveLength(4)
  })

  it('shows the backend error instead of the cards', async () => {
    const { api, mount } = await loadStatusView()
    vi.mocked(api.fetchStatus).mockRejectedValue(new Error('status failed'))

    const wrapper = await mount()

    expect(wrapper.text()).toContain('获取状态失败')
    expect(wrapper.text()).toContain('status failed')
    expect(wrapper.findAll('.qc-metric-value')).toHaveLength(0)
  })

  it('points at the settings page when no platform is configured', async () => {
    const { api, mount } = await loadStatusView()
    vi.mocked(api.fetchStatus).mockResolvedValue(statusFixture({ platforms: [] }))

    const wrapper = await mount()

    expect(wrapper.text()).toContain('还没有可用的 QQ 平台')
    expect(wrapper.text()).not.toContain('主机器人')
  })

  it('warns when the command list is empty', async () => {
    const { api, mount } = await loadStatusView()
    vi.mocked(api.fetchStatus).mockResolvedValue(
      statusFixture({ items: { count: 0, max: 20 } }),
    )

    const wrapper = await mount()

    expect(wrapper.text()).toContain('尚未配置指令条目，同步会清空本插件创建的面板。')
  })

  it('refreshes with refresh=1 when the user clicks 刷新', async () => {
    const { api, mount } = await loadStatusView()
    vi.mocked(api.fetchStatus).mockResolvedValue(statusFixture())

    const wrapper = await mount()
    const refresh = wrapper.findAll('button').find((node) => node.text().includes('刷新'))
    expect(refresh).toBeDefined()

    await refresh?.trigger('click')
    await flush()

    expect(api.fetchStatus).toHaveBeenLastCalledWith({ refresh: true })
  })

  it('ignores an older response that lands after a newer one', async () => {
    const { api, mount } = await loadStatusView()
    const slow = deferred<StatusResponse>()
    const fast = deferred<StatusResponse>()
    const fetchStatus = vi.mocked(api.fetchStatus)
    fetchStatus.mockReturnValueOnce(slow.promise).mockReturnValueOnce(fast.promise)

    const wrapper = await mount()
    const refresh = wrapper.findAll('button').find((node) => node.text().includes('刷新'))
    await refresh?.trigger('click')
    await waitUntil(() => vi.mocked(api.fetchStatus).mock.calls.length === 2)

    fast.resolve(statusFixture({ items: { count: 7, max: 20 } }))
    await flush()
    slow.resolve(statusFixture({ items: { count: 1, max: 20 } }))
    await flush()

    // 先发的旧请求后到，不能覆盖新数据，也不能把 loading 又打开
    expect(wrapper.findAll('.qc-metric-value')[2]?.text()).toBe('7')
    expect(wrapper.find('.qc-page > .v-progress-linear').exists()).toBe(false)
  })

  it('labels the mock data in local dev', async () => {
    const { api, mount } = await loadStatusView({ withBackend: false })
    vi.mocked(api.fetchStatus).mockResolvedValue(statusFixture())

    const wrapper = await mount()

    expect(wrapper.text()).toContain('本地开发环境：展示的是 mock 数据，未连接 AstrBot 后端。')
  })

  it('reloads after the sync card reports a finished run', async () => {
    const handlers: PluginViewSSEHandlers[] = []
    const bridge = installBridge({
      subscribeSSE: vi.fn(async (_endpoint, next) => {
        handlers.push(next ?? {})
        return `sub-${handlers.length}`
      }),
    })
    vi.resetModules()
    const api = await import('../api/dashboard')
    const { default: StatusOverviewView } = await import('./StatusOverviewView.vue')
    vi.mocked(api.fetchStatus).mockResolvedValue(statusFixture())

    const wrapper = mountView(StatusOverviewView)
    await waitUntil(
      () =>
        vi.mocked(api.fetchStatus).mock.calls.length > 0 &&
        vi.mocked(bridge.subscribeSSE).mock.calls.length > 0,
    )
    await flush()
    expect(api.fetchStatus).toHaveBeenCalledTimes(1)
    expect(bridge.subscribeSSE).toHaveBeenCalledTimes(1)

    const finish: SyncEvent = {
      type: 'finish',
      seq: 2,
      ok: true,
      platforms: 1,
      succeeded: 1,
      failed: 0,
    }
    handlers[0]?.onMessage?.({ raw: JSON.stringify(finish), parsed: finish, eventType: 'message' })
    await flush()

    // 同步结束后状态页要拿新数据，且绕过后端短期缓存
    expect(api.fetchStatus).toHaveBeenCalledTimes(2)
    expect(api.fetchStatus).toHaveBeenLastCalledWith({ refresh: true })
    expect(wrapper.text()).toContain('同步完成：成功 1 个平台，失败 0 个')
  })
})
