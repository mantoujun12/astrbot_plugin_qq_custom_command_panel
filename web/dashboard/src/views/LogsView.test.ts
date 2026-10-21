import { afterEach, describe, expect, it, vi } from 'vitest'
import type { LogEvent, LogStreamInfo } from '../types/logs'
import { flush, installBridge, mountView, waitUntil } from '../test/helpers'

vi.mock('../api/logs', () => ({
  getMockLogs: vi.fn(),
  subscribeLogs: vi.fn(),
}))

type SubscribeOptions = Parameters<typeof import('../api/logs').subscribeLogs>[0]

function logEvent(seq: number, overrides: Partial<LogEvent> = {}): LogEvent {
  return {
    type: 'log',
    seq,
    timestamp: `2026-10-21T02:18:0${seq}.000Z`,
    level: 'info',
    message: `message-${seq}`,
    ...overrides,
  }
}

async function loadView(
  options: {
    backend?: boolean
    initial?: LogEvent[]
    reconnect?: LogEvent[]
    streamInfos?: LogStreamInfo[]
  } = {},
) {
  delete window.AstrBotPluginView
  delete window.AstrBotPluginPage
  if (options.backend !== false) {
    installBridge()
  }

  vi.resetModules()
  const api = await import('../api/logs')
  const { default: LogsView } = await import('./LogsView.vue')
  const handlers: SubscribeOptions[] = []
  const stop = vi.fn(async (): Promise<void> => {})
  vi.mocked(api.getMockLogs).mockReturnValue([logEvent(1, { message: 'mock-message' })])
  vi.mocked(api.subscribeLogs).mockImplementation(async (next) => {
    const index = handlers.length
    handlers.push(next)
    next.onStream?.(
      options.streamInfos?.[index] ?? {
        type: 'stream',
        id: `stream-${index + 1}`,
        reset: false,
      },
    )
    next.onOpen?.()
    const entries = index === 0 ? options.initial : options.reconnect
    for (const entry of entries ?? []) {
      next.onEvent(entry)
    }
    return { stop }
  })

  return {
    api,
    handlers,
    stop,
    async mount() {
      const wrapper = mountView(LogsView)
      if (options.backend === false) {
        await waitUntil(() => wrapper.text().includes('mock-message'))
      } else {
        await waitUntil(() => vi.mocked(api.subscribeLogs).mock.calls.length > 0)
      }
      await flush()
      return wrapper
    },
  }
}

afterEach(() => {
  delete window.AstrBotPluginView
  delete window.AstrBotPluginPage
})

describe('LogsView', () => {
  it('renders replayed logs and connects the SSE handler', async () => {
    const state = await loadView({
      initial: [logEvent(1), logEvent(2, { level: 'warning' })],
    })

    const wrapper = await state.mount()

    expect(state.api.subscribeLogs).toHaveBeenCalledWith(
      expect.objectContaining({ since: 0, onEvent: expect.any(Function) }),
    )
    expect(wrapper.text()).toContain('实时连接')
    expect(wrapper.findAll('.qc-log-row')).toHaveLength(2)
    expect(wrapper.text()).toContain('message-1')
    expect(wrapper.text()).toContain('message-2')
  })

  it('combines search and log-level filtering', async () => {
    const state = await loadView({
      initial: [
        logEvent(1, { message: 'Alpha ready' }),
        logEvent(2, { level: 'error', message: 'Beta failed' }),
      ],
    })
    const wrapper = await state.mount()

    await wrapper.get('.qc-log-search input').setValue('BETA')
    expect(wrapper.findAll('.qc-log-row')).toHaveLength(1)
    expect(wrapper.text()).toContain('Beta failed')

    await wrapper.get('.qc-log-search input').setValue('')
    await wrapper.get('.qc-log-level--info').trigger('click')
    expect(wrapper.findAll('.qc-log-row')).toHaveLength(1)
    expect(wrapper.text()).toContain('Beta failed')

    await wrapper.get('.qc-log-level-all').trigger('click')
    expect(wrapper.findAll('.qc-log-row')).toHaveLength(2)
  })

  it('treats a cleared search model as an empty query', async () => {
    const state = await loadView({ initial: [logEvent(1), logEvent(2)] })
    const wrapper = await state.mount()

    wrapper.findComponent({ name: 'VTextField' }).vm.$emit('update:modelValue', null)
    await flush()

    expect(wrapper.findAll('.qc-log-row')).toHaveLength(2)
  })

  it('pauses the display, keeps collecting, and flushes pending logs on resume', async () => {
    const state = await loadView({ initial: [logEvent(1)] })
    const wrapper = await state.mount()

    await wrapper.get('.qc-log-pause').trigger('click')
    state.handlers[0]?.onEvent(logEvent(2, { message: 'while-paused' }))
    state.handlers[0]?.onEvent(logEvent(3, { message: 'still-paused' }))
    await flush()

    expect(wrapper.text()).not.toContain('while-paused')
    expect(wrapper.text()).toContain('2 条待显示')
    expect(wrapper.text()).toContain('后台仍在收集日志')

    await wrapper.get('.qc-log-pause').trigger('click')
    await flush()

    expect(wrapper.text()).toContain('while-paused')
    expect(wrapper.text()).toContain('still-paused')
  })

  it('clears only the current view and keeps receiving new logs', async () => {
    const state = await loadView({ initial: [logEvent(1), logEvent(2)] })
    const wrapper = await state.mount()

    await wrapper.get('.qc-log-clear').trigger('click')
    expect(wrapper.findAll('.qc-log-row')).toHaveLength(0)
    expect(wrapper.text()).toContain('还没有日志')

    state.handlers[0]?.onEvent(logEvent(3, { message: 'after-clear' }))
    await flush()

    expect(wrapper.findAll('.qc-log-row')).toHaveLength(1)
    expect(wrapper.text()).toContain('after-clear')
  })

  it('expands traceback details on demand', async () => {
    const state = await loadView({
      initial: [
        logEvent(1, {
          level: 'error',
          message: 'sync failed',
          traceback: 'Traceback (most recent call last):\nRuntimeError: boom',
        }),
      ],
    })
    const wrapper = await state.mount()

    expect(wrapper.text()).not.toContain('RuntimeError: boom')
    await wrapper.get('.qc-log-detail-toggle').trigger('click')
    expect(wrapper.get('.qc-log-traceback').text()).toContain('RuntimeError: boom')
  })

  it('turns auto-scroll off when the user leaves the bottom and on at the bottom', async () => {
    const state = await loadView({ initial: [logEvent(1)] })
    const wrapper = await state.mount()
    const viewport = wrapper.get('.qc-log-viewport').element as HTMLElement
    const toggle = wrapper.get('.qc-log-autoscroll input')
    Object.defineProperties(viewport, {
      scrollHeight: { configurable: true, value: 1000 },
      clientHeight: { configurable: true, value: 300 },
    })

    viewport.scrollTop = 100
    await wrapper.get('.qc-log-viewport').trigger('scroll')
    expect((toggle.element as HTMLInputElement).checked).toBe(false)

    viewport.scrollTop = 700
    await wrapper.get('.qc-log-viewport').trigger('scroll')
    expect((toggle.element as HTMLInputElement).checked).toBe(true)
  })

  it('shows disconnects and reconnects from the last received sequence', async () => {
    const state = await loadView({ initial: [logEvent(5)] })
    const wrapper = await state.mount()

    state.handlers[0]?.onError?.(new Error('stream stopped'))
    await flush()

    expect(wrapper.text()).toContain('连接已断开')
    expect(wrapper.text()).toContain('日志流已中断')
    expect(state.stop).toHaveBeenCalledTimes(1)

    await wrapper.get('.qc-log-retry').trigger('click')
    await waitUntil(() => vi.mocked(state.api.subscribeLogs).mock.calls.length === 2)
    expect(vi.mocked(state.api.subscribeLogs).mock.calls[1][0]).toEqual(
      expect.objectContaining({ since: 5, streamId: 'stream-1' }),
    )

    wrapper.unmount()
    await flush()
    expect(state.stop).toHaveBeenCalledTimes(2)
  })

  it('resets the display and sequence when reconnecting to a new process stream', async () => {
    const state = await loadView({
      initial: [logEvent(5, { message: 'previous process' })],
      reconnect: [logEvent(1, { message: 'new process' })],
      streamInfos: [
        { type: 'stream', id: 'stream-1', reset: false },
        { type: 'stream', id: 'stream-2', reset: true },
      ],
    })
    const wrapper = await state.mount()

    state.handlers[0]?.onError?.(new Error('stream stopped'))
    await flush()
    await wrapper.get('.qc-log-retry').trigger('click')
    await waitUntil(() => vi.mocked(state.api.subscribeLogs).mock.calls.length === 2)
    await flush()

    expect(wrapper.text()).not.toContain('previous process')
    expect(wrapper.text()).toContain('new process')
    expect(wrapper.findAll('.qc-log-row')).toHaveLength(1)

    wrapper.unmount()
    await flush()
  })

  it('labels local mock logs without pretending to be live', async () => {
    const state = await loadView({ backend: false })

    const wrapper = await state.mount()

    expect(state.api.subscribeLogs).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('本地模拟')
    expect(wrapper.text()).toContain('展示的是 mock 日志')
    expect(wrapper.text()).toContain('mock-message')
  })
})
