import { afterEach, describe, expect, it, vi } from 'vitest'
import { getMockLogs, isLogEvent, subscribeLogs } from './logs'
import { createBridgeStub } from '../test/helpers'
import type { LogEvent } from '../types/logs'

afterEach(() => {
  delete window.AstrBotPluginView
  delete window.AstrBotPluginPage
})

function logEvent(overrides: Partial<LogEvent> = {}): LogEvent {
  return {
    type: 'log',
    seq: 1,
    timestamp: '2026-10-21T02:18:04.120Z',
    level: 'info',
    message: 'ready',
    ...overrides,
  }
}

describe('isLogEvent', () => {
  it('accepts the backend log contract', () => {
    expect(isLogEvent(logEvent())).toBe(true)
    expect(isLogEvent(logEvent({ traceback: 'Traceback' }))).toBe(true)
  })

  it('rejects malformed or foreign events', () => {
    expect(isLogEvent(null)).toBe(false)
    expect(isLogEvent({ type: 'finish', seq: 1 })).toBe(false)
    expect(isLogEvent(logEvent({ seq: -1 }))).toBe(false)
    expect(isLogEvent(logEvent({ level: 'trace' as never }))).toBe(false)
    expect(isLogEvent({ ...logEvent(), traceback: 42 })).toBe(false)
  })
})

describe('getMockLogs', () => {
  it('returns a fresh copy so views cannot mutate the shared fixture', () => {
    const first = getMockLogs()
    const second = getMockLogs()

    expect(first).toEqual(second)
    expect(first).not.toBe(second)
    expect(first[0]).not.toBe(second[0])
  })
})

describe('subscribeLogs', () => {
  it('subscribes with the replay cursor and forwards valid events', async () => {
    const bridge = createBridgeStub()
    window.AstrBotPluginView = bridge
    const onEvent = vi.fn()
    const onOpen = vi.fn()

    const subscription = await subscribeLogs({ since: 17, onEvent, onOpen })

    expect(bridge.subscribeSSE).toHaveBeenCalledWith(
      'logs/events',
      expect.objectContaining({ onMessage: expect.any(Function), onError: expect.any(Function) }),
      { since: 17 },
    )

    const handlers = vi.mocked(bridge.subscribeSSE).mock.calls[0][1]
    handlers?.onOpen?.()
    expect(onOpen).toHaveBeenCalledTimes(1)

    const event = logEvent({ seq: 18, message: 'live' })
    handlers?.onMessage?.({
      raw: JSON.stringify(event),
      parsed: event,
      eventType: 'message',
    })
    expect(onEvent).toHaveBeenCalledWith(event)

    handlers?.onMessage?.({
      raw: '{"type":"finish"}',
      parsed: { type: 'finish', seq: 19 },
      eventType: 'message',
    })
    expect(onEvent).toHaveBeenCalledTimes(1)

    await subscription.stop()
    expect(bridge.unsubscribeSSE).toHaveBeenCalledWith('sub-1')
  })

  it('reports stream errors', async () => {
    const bridge = createBridgeStub()
    window.AstrBotPluginView = bridge
    const onError = vi.fn()

    await subscribeLogs({ onEvent: vi.fn(), onError })

    const handlers = vi.mocked(bridge.subscribeSSE).mock.calls[0][1]
    handlers?.onError?.()
    expect(onError).toHaveBeenCalledTimes(1)
  })

  it('throws without a bridge', async () => {
    await expect(subscribeLogs({ onEvent: vi.fn() })).rejects.toThrow('no backend')
  })
})
