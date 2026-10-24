import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  initialSyncState,
  reduceSyncEvent,
  startSync,
  subscribeSyncRun,
} from './sync'
import { createBridgeStub } from '../test/helpers'
import type { SyncEvent } from '../types/dashboard'

afterEach(() => {
  delete window.AstrBotPluginView
  delete window.AstrBotPluginPage
})

describe('reduceSyncEvent', () => {
  it('resets the run state on start', () => {
    const state = { ...initialSyncState(), status: 'done' as const, messages: ['old'] }

    const next = reduceSyncEvent(state, {
      type: 'start',
      seq: 1,
      mode: 'sync',
      platforms: 2,
      scenes: 2,
      items: 3,
    })

    expect(next.status).toBe('running')
    expect(next.platforms).toBe(2)
    expect(next.completed).toBe(0)
    expect(next.messages).toEqual([])
    expect(next.lastSeq).toBe(1)
  })

  it('appends log messages', () => {
    const next = reduceSyncEvent(initialSyncState(), {
      type: 'message',
      seq: 2,
      text: '开始同步',
    })

    expect(next.messages).toEqual(['开始同步'])
  })

  it('tracks per-platform results and progress', () => {
    let state = reduceSyncEvent(initialSyncState(), {
      type: 'start',
      seq: 1,
      platforms: 2,
      scenes: 2,
      items: 1,
    })
    state = reduceSyncEvent(state, {
      type: 'platform',
      seq: 2,
      pf_id: 'pf1',
      name: '主机器人',
      appid: '102*****89',
      index: 1,
      total: 2,
      status: 'ok',
      saved: 2,
    })
    state = reduceSyncEvent(state, {
      type: 'platform',
      seq: 3,
      pf_id: 'pf2',
      name: '备用机器人',
      appid: '555*****78',
      index: 2,
      total: 2,
      status: 'error',
      saved: 0,
      error: 'boom',
    })

    expect(state.completed).toBe(2)
    expect(state.succeeded).toBe(1)
    expect(state.failed).toBe(1)
    expect(state.platformStates.map((item) => item.pf_id)).toEqual(['pf1', 'pf2'])
    expect(state.platformStates.map((item) => item.name)).toEqual(['主机器人', '备用机器人'])
    expect(state.platformStates.map((item) => item.appid)).toEqual(['102*****89', '555*****78'])
    expect(state.platformStates[1].error).toBe('boom')
  })

  it('does not double count a replayed platform event', () => {
    let state = reduceSyncEvent(initialSyncState(), {
      type: 'start',
      seq: 1,
      platforms: 1,
      scenes: 1,
      items: 1,
    })
    const event: SyncEvent = {
      type: 'platform',
      seq: 2,
      pf_id: 'pf1',
      index: 1,
      total: 1,
      status: 'ok',
      saved: 1,
    }
    state = reduceSyncEvent(state, event)
    state = reduceSyncEvent(state, { ...event, seq: 3 })

    expect(state.completed).toBe(1)
    expect(state.succeeded).toBe(1)
  })

  it('finishes with the backend summary', () => {
    const next = reduceSyncEvent(initialSyncState(), {
      type: 'finish',
      seq: 4,
      ok: true,
      platforms: 1,
      succeeded: 1,
      failed: 0,
    })

    expect(next.status).toBe('done')
    expect(next.succeeded).toBe(1)
  })

  it('marks the run as failed with the error message', () => {
    const next = reduceSyncEvent(initialSyncState(), {
      type: 'finish',
      seq: 4,
      ok: false,
      platforms: 0,
      succeeded: 0,
      failed: 0,
      error: 'backend exploded',
    })

    expect(next.status).toBe('failed')
    expect(next.error).toBe('backend exploded')
  })
})

describe('startSync', () => {
  it('throws without a bridge so local dev cannot fake a sync', async () => {
    await expect(startSync()).rejects.toThrow('no backend')
  })

  it('posts the sync endpoint', async () => {
    const bridge = createBridgeStub()
    window.AstrBotPluginView = bridge
    vi.mocked(bridge.apiPost).mockResolvedValue({ started: true, busy: false })

    await expect(startSync()).resolves.toEqual({ started: true, busy: false })
    expect(bridge.apiPost).toHaveBeenCalledWith('sync')
  })
})

describe('subscribeSyncRun', () => {
  it('subscribes with since and forwards parsed events', async () => {
    const bridge = createBridgeStub()
    window.AstrBotPluginView = bridge
    const onEvent = vi.fn()
    const onOpen = vi.fn()

    const subscription = await subscribeSyncRun({ since: 7, onEvent, onOpen })

    expect(bridge.subscribeSSE).toHaveBeenCalledWith(
      'sync/events',
      expect.objectContaining({ onMessage: expect.any(Function), onError: expect.any(Function) }),
      { since: 7 },
    )

    // 宿主 SDK 传进来的是 { raw, parsed, ... }，parsed 已经是 JSON 对象
    const handlers = vi.mocked(bridge.subscribeSSE).mock.calls[0][1]
    handlers?.onOpen?.()
    expect(onOpen).toHaveBeenCalledTimes(1)
    handlers?.onMessage?.({
      raw: '{"type":"finish"}',
      parsed: { type: 'finish', seq: 8, ok: true, platforms: 1, succeeded: 1, failed: 0 },
      eventType: 'message',
    })
    expect(onEvent).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'finish', ok: true }),
    )

    // 非法/未知事件会被忽略
    handlers?.onMessage?.({ raw: 'null', parsed: null, eventType: 'message' })
    expect(onEvent).toHaveBeenCalledTimes(1)

    await subscription.stop()
    expect(bridge.unsubscribeSSE).toHaveBeenCalledWith('sub-1')
  })

  it('reports stream errors through onError', async () => {
    const bridge = createBridgeStub()
    window.AstrBotPluginView = bridge
    const onError = vi.fn()

    await subscribeSyncRun({ onEvent: vi.fn(), onError })

    const handlers = vi.mocked(bridge.subscribeSSE).mock.calls[0][1]
    handlers?.onError?.()
    expect(onError).toHaveBeenCalledTimes(1)
  })

  it('throws without a bridge', async () => {
    await expect(subscribeSyncRun({ onEvent: vi.fn() })).rejects.toThrow('no backend')
  })
})
