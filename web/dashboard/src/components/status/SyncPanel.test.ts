import { describe, expect, it, vi } from 'vitest'
import type { PluginViewSSEHandlers } from '../../bridge'
import type { SyncEvent } from '../../types/dashboard'
import { flush, installBridge, mountView, waitUntil } from '../../test/helpers'

/**
 * 同步卡片与状态页共用 useBridge / useSyncRun 的单例，所以每个用例重置模块后
 * 再引入，并把 bridge 的 SSE 通道握在手里驱动进度。
 */
async function setup(options: { withBackend?: boolean } = {}) {
  const handlers: PluginViewSSEHandlers[] = []
  const bridge =
    options.withBackend === false
      ? null
      : installBridge({
          apiPost: vi.fn(async () => ({ started: true, busy: false })),
          subscribeSSE: vi.fn(async (_endpoint, next) => {
            handlers.push(next ?? {})
            return `sub-${handlers.length}`
          }),
          unsubscribeSSE: vi.fn(async (id: string) => ({ subscriptionId: id })),
        })

  vi.resetModules()
  const { useBridge } = await import('../../composables/useBridge')
  const ready = useBridge().ready
  const { default: SyncPanel } = await import('./SyncPanel.vue')
  await waitUntil(() => ready.value)

  const wrapper = mountView(SyncPanel)
  if (bridge) {
    await waitUntil(() => handlers.length > 0)
  }
  await flush()

  return {
    wrapper,
    bridge,
    emit(event: SyncEvent): void {
      handlers.at(-1)?.onMessage?.({
        raw: JSON.stringify(event),
        parsed: event,
        eventType: 'message',
      })
    },
    startButton: (): ReturnType<typeof wrapper.findAll>[number] | undefined =>
      wrapper.findAll('button').find((node) => node.text().includes('同步面板')),
  }
}

describe('SyncPanel', () => {
  it('disables the entry point without a backend', async () => {
    const panel = await setup({ withBackend: false })

    expect(panel.wrapper.text()).toContain(
      '本地开发环境没有 AstrBot 后端，同步入口不可用。',
    )
    expect(panel.startButton()?.attributes('disabled')).toBeDefined()
  })

  it('shows the empty state and starts a run on demand', async () => {
    const panel = await setup()

    expect(panel.wrapper.text()).toContain('还没有同步记录。')
    expect(panel.startButton()?.attributes('disabled')).toBeUndefined()

    await panel.startButton()?.trigger('click')
    await flush()

    expect(panel.bridge?.apiPost).toHaveBeenCalledWith('sync')
  })

  it('renders progress, per-platform chips and the summary', async () => {
    const panel = await setup()

    panel.emit({ type: 'start', seq: 1, platforms: 2, scenes: 2, items: 3 })
    await flush()
    expect(panel.wrapper.text()).toContain('正在同步…')
    expect(panel.wrapper.text()).toContain('0/2')

    panel.emit({
      type: 'platform',
      seq: 2,
      pf_id: '主机器人',
      index: 1,
      total: 2,
      status: 'ok',
      saved: 3,
    })
    panel.emit({ type: 'message', seq: 3, text: '写入 3 条指令' })
    await flush()
    expect(panel.wrapper.text()).toContain('主机器人')
    expect(panel.wrapper.text()).toContain('1/2')
    expect(panel.wrapper.text()).toContain('写入 3 条指令')

    panel.emit({
      type: 'finish',
      seq: 4,
      ok: true,
      platforms: 2,
      succeeded: 1,
      failed: 1,
    })
    await flush()

    expect(panel.wrapper.text()).toContain('同步完成：成功 1 个平台，失败 1 个')
    // 状态页靠这个事件重新拉一次状态
    expect(panel.wrapper.emitted('finished')).toHaveLength(1)
  })

  it('shows the robot name instead of the internal pf_id', async () => {
    const panel = await setup()

    panel.emit({ type: 'start', seq: 1, platforms: 1, scenes: 1, items: 3 })
    panel.emit({
      type: 'platform',
      seq: 2,
      pf_id: 'f47ac10b-58cc-4372-a567-0e02b2c3d479',
      name: '主机器人',
      appid_masked: '102*****89',
      index: 1,
      total: 1,
      status: 'ok',
      saved: 3,
    })
    await flush()

    expect(panel.wrapper.text()).toContain('主机器人')
    expect(panel.wrapper.text()).not.toContain('f47ac10b-58cc-4372-a567-0e02b2c3d479')
  })

  it('falls back to the masked appid when the robot has no name', async () => {
    const panel = await setup()

    panel.emit({ type: 'start', seq: 1, platforms: 1, scenes: 1, items: 1 })
    panel.emit({
      type: 'platform',
      seq: 2,
      pf_id: '1112223334',
      name: '',
      appid_masked: '111*****34',
      index: 1,
      total: 1,
      status: 'ok',
      saved: 1,
    })
    await flush()

    expect(panel.wrapper.text()).toContain('111*****34')
    expect(panel.wrapper.text()).not.toContain('1112223334')
  })

  it('keeps the progress bar indeterminate when the total is unknown', async () => {
    const panel = await setup()

    panel.emit({ type: 'start', seq: 1, platforms: 0, scenes: 0, items: 0 })
    await flush()

    expect(panel.wrapper.text()).toContain('正在同步…')
    expect(panel.wrapper.text()).not.toContain('0/0')
  })

  it('surfaces a failed run and retries from the last seq', async () => {
    const panel = await setup()

    panel.emit({
      type: 'finish',
      seq: 5,
      ok: false,
      platforms: 1,
      succeeded: 0,
      failed: 1,
      error: 'boom',
    })
    await flush()

    expect(panel.wrapper.text()).toContain('boom')
    const retry = panel.wrapper.findAll('button').find((node) => node.text().includes('重试'))
    expect(retry).toBeDefined()

    const callsBefore = vi.mocked(panel.bridge!.subscribeSSE).mock.calls.length
    await retry?.trigger('click')
    await flush()

    expect(vi.mocked(panel.bridge!.subscribeSSE).mock.calls.length).toBe(callsBefore + 1)
    expect(vi.mocked(panel.bridge!.subscribeSSE).mock.calls.at(-1)?.[2]).toEqual({ since: 5 })
  })

  it('summarises a failure that carries no error message', async () => {
    const panel = await setup()

    panel.emit({
      type: 'start',
      seq: 1,
      platforms: 2,
      scenes: 2,
      items: 1,
    })
    panel.emit({
      type: 'finish',
      seq: 2,
      ok: false,
      platforms: 2,
      succeeded: 1,
      failed: 1,
    })
    await flush()

    expect(panel.wrapper.text()).toContain('同步完成：成功 1 个平台，失败 1 个')
  })

  it('unsubscribes when the page goes away', async () => {
    const panel = await setup()
    const unsubscribe = vi.mocked(panel.bridge!.unsubscribeSSE)

    panel.wrapper.unmount()
    await flush()

    expect(unsubscribe).toHaveBeenCalledWith('sub-1')
  })

  it('warns and stays usable when the run cannot be started', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const panel = await setup()
    // 宿主重载后 bridge 没了：入口还亮着，但这次触发必然失败
    delete window.AstrBotPluginView

    await panel.startButton()?.trigger('click')
    await flush()

    expect(warn).toHaveBeenCalledWith(
      '[qq-command-panel] start sync failed',
      expect.any(Error),
    )
    expect(panel.wrapper.text()).toContain('同步面板')
  })
})
