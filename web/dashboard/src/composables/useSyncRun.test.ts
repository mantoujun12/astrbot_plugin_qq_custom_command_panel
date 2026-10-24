import { describe, expect, it, vi } from 'vitest'
import type { PluginViewBridge, PluginViewSSEHandlers } from '../bridge'
import type { SyncEvent } from '../types/dashboard'
import { flush, installBridge, waitUntil } from '../test/helpers'

/**
 * 同步状态是模块级单例：每个用例先重置模块，再取一份全新的 composable。
 * useSyncRun 内部用的就是 useBridge 的状态，所以借它的 ready 等 bootstrap 落地。
 */
async function setup() {
  vi.resetModules()
  const { useBridge } = await import('./useBridge')
  const { useSyncRun } = await import('./useSyncRun')
  const run = useSyncRun()
  const ready = useBridge().ready
  await waitUntil(() => ready.value)
  return run
}

interface Stream {
  bridge: PluginViewBridge
  /** 每次订阅带的 since */
  subscribes: { since: number }[]
  /** 派发一条进度事件给最新那条流 */
  emit(event: SyncEvent): void
  /** 模拟宿主把流断掉 */
  failStream(): void
  /** 放行被 holdFirst 挡住的第一条流 */
  release(): void
}

/** 一个能把 SSE 握在手里的 bridge 替身 */
function streamBridge(options: { holdFirst?: boolean } = {}): Stream {
  const handlers: PluginViewSSEHandlers[] = []
  const subscribes: { since: number }[] = []
  let release = (): void => {}
  const gate = new Promise<void>((resolve) => {
    release = resolve
  })
  let opened = 0

  const bridge = installBridge({
    apiPost: vi.fn(async () => ({ started: true, busy: false })),
    subscribeSSE: vi.fn(
      async (
        _endpoint: string,
        nextHandlers?: PluginViewSSEHandlers,
        params?: Record<string, unknown>,
      ) => {
        opened += 1
        // id 必须在 await 之前定下来，否则被 hold 的那条流会拿到后来的编号
        const id = `sub-${opened}`
        handlers.push(nextHandlers ?? {})
        subscribes.push({ since: Number(params?.since ?? 0) })
        if (options.holdFirst === true && opened === 1) {
          await gate
        }
        return id
      },
    ),
    unsubscribeSSE: vi.fn(async (id: string) => ({ subscriptionId: id })),
  })

  return {
    bridge,
    subscribes,
    emit(event: SyncEvent): void {
      handlers.at(-1)?.onMessage?.({
        raw: JSON.stringify(event),
        parsed: event,
        eventType: 'message',
      })
    },
    failStream(): void {
      handlers.at(-1)?.onError?.()
    },
    release(): void {
      release()
    },
  }
}

describe('useSyncRun', () => {
  it('reports sync as unavailable without a backend', async () => {
    const run = await setup()

    expect(run.available.value).toBe(false)
    await expect(run.start()).rejects.toThrow('no backend')

    // attach / retry 在本地开发里是静默空转，不能改状态
    run.attach()
    run.retry()
    await flush()

    expect(run.state.value.status).toBe('idle')
    expect(run.hasRun.value).toBe(false)
  })

  it('starts a run, reduces the stream and stops on finish', async () => {
    const stream = streamBridge()
    const run = await setup()

    expect(run.available.value).toBe(true)
    const onFinish = vi.fn()
    await run.start({ onFinish })

    expect(stream.bridge.apiPost).toHaveBeenCalledWith('sync')
    expect(stream.subscribes).toEqual([{ since: 0 }])
    // 还没收到 start 事件，进度卡片不应该先切成「正在同步」
    expect(run.running.value).toBe(false)

    stream.emit({ type: 'start', seq: 1, platforms: 2, scenes: 2, items: 3 })
    await flush()
    expect(run.state.value.status).toBe('running')
    expect(run.running.value).toBe(true)
    expect(run.hasRun.value).toBe(true)

    stream.emit({
      type: 'platform',
      seq: 2,
      pf_id: 'pf1',
      index: 1,
      total: 2,
      status: 'ok',
      saved: 2,
    })
    stream.emit({ type: 'message', seq: 3, text: '同步完成' })
    await flush()
    expect(run.state.value.completed).toBe(1)
    expect(run.state.value.succeeded).toBe(1)
    expect(run.state.value.messages).toEqual(['同步完成'])

    stream.emit({
      type: 'finish',
      seq: 4,
      ok: true,
      platforms: 2,
      succeeded: 1,
      failed: 0,
    })
    await flush()

    expect(run.state.value.status).toBe('done')
    expect(run.running.value).toBe(false)
    expect(onFinish).toHaveBeenCalledTimes(1)
    // 收到 finish 就退订，不等宿主关闭流
    expect(stream.bridge.unsubscribeSSE).toHaveBeenCalledWith('sub-1')
  })

  it('keeps the page usable when only the progress stream fails', async () => {
    installBridge({
      apiPost: vi.fn(async () => ({ started: true, busy: true })),
      subscribeSSE: vi.fn(async () => {
        throw new Error('progress stream unavailable')
      }),
    })
    const run = await setup()

    await run.start()

    expect(run.state.value.status).toBe('failed')
    expect(run.state.value.error).toBe('progress stream unavailable')
    expect(run.available.value).toBe(true)
  })

  it('attaches once per page entry and forwards finish', async () => {
    const stream = streamBridge()
    const run = await setup()

    const onFinish = vi.fn()
    run.attach(onFinish)
    run.attach(onFinish)
    await flush()

    expect(stream.bridge.subscribeSSE).toHaveBeenCalledTimes(1)
    expect(stream.subscribes).toEqual([{ since: 0 }])

    stream.emit({
      type: 'finish',
      seq: 2,
      ok: true,
      platforms: 1,
      succeeded: 1,
      failed: 0,
    })
    await flush()

    expect(run.state.value.status).toBe('done')
    expect(onFinish).toHaveBeenCalledTimes(1)
  })

  it('surfaces a failed attach', async () => {
    installBridge({
      subscribeSSE: vi.fn(async () => {
        throw new Error('sse down')
      }),
    })
    const run = await setup()

    run.attach()
    await flush()

    expect(run.state.value.status).toBe('failed')
    expect(run.state.value.error).toBe('sse down')
  })

  it('returns to idle when the stream closes without a run', async () => {
    const stream = streamBridge()
    const run = await setup()

    const onFinish = vi.fn()
    run.attach(onFinish)
    await flush()

    stream.emit({ type: 'start', seq: 1, platforms: 1, scenes: 1, items: 1 })
    await flush()
    expect(run.state.value.status).toBe('running')

    // 插件重启后缓冲为空：后端补发 reason=idle 的 finish
    stream.emit({
      type: 'finish',
      seq: 1,
      ok: false,
      reason: 'idle',
      platforms: 0,
      succeeded: 0,
      failed: 0,
    })
    await flush()

    expect(run.state.value.status).toBe('idle')
    expect(run.running.value).toBe(false)
    expect(run.hasRun.value).toBe(false)
    // 这不是一次真实运行结束，不触发状态页刷新
    expect(onFinish).not.toHaveBeenCalled()
    expect(stream.bridge.unsubscribeSSE).toHaveBeenCalledWith('sub-1')
  })

  it('surfaces a stream error', async () => {
    const stream = streamBridge()
    const run = await setup()

    run.attach()
    await flush()
    stream.failStream()
    await flush()

    expect(run.state.value.status).toBe('failed')
    expect(run.state.value.error).toBe('sync stream error')
  })

  it('resumes from the last seq when the user retries', async () => {
    const stream = streamBridge()
    const run = await setup()

    run.attach()
    await flush()
    stream.emit({ type: 'start', seq: 7, platforms: 1, scenes: 1, items: 1 })
    await flush()
    expect(run.state.value.lastSeq).toBe(7)

    const onFinish = vi.fn()
    run.retry(onFinish)
    await flush()

    expect(stream.subscribes.at(-1)).toEqual({ since: 7 })
  })

  it('drops a stale subscription when a newer one wins', async () => {
    const stream = streamBridge({ holdFirst: true })
    const run = await setup()

    // 第一条流被握在宿主手里，用户这时又点了同步
    run.attach()
    await flush()
    await run.start()
    stream.release()
    await flush()

    expect(stream.subscribes).toHaveLength(2)
    // 只保留第二条，第一条拿到 id 后立刻退订
    expect(stream.bridge.unsubscribeSSE).toHaveBeenCalledWith('sub-1')
    expect(stream.bridge.unsubscribeSSE).toHaveBeenCalledTimes(1)
  })

  it('stops the current subscription on demand', async () => {
    const stream = streamBridge()
    const run = await setup()

    run.attach()
    await flush()
    await run.stop()
    await run.stop()

    expect(stream.bridge.unsubscribeSSE).toHaveBeenCalledWith('sub-1')
    expect(stream.bridge.unsubscribeSSE).toHaveBeenCalledTimes(1)
  })
})
