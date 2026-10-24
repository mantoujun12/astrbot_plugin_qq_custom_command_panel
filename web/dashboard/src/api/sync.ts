/**
 * 同步入口与 SSE 进度流。
 *
 * 后端把同步任务跑在后台（见 core/sync_runner.py），这里只负责触发、
 * 订阅事件，并把事件规约成页面可直接渲染的状态。
 */

import { getBridge } from '../bridge'
import { toPlain } from './serialize'
import type { SyncEvent, SyncRunState } from '../types/dashboard'

/** 对应后端 `/<plugin_name>/sync` */
const SYNC_ENDPOINT = 'sync'

/** 对应后端 `/<plugin_name>/sync/events`（SSE）*/
const SYNC_EVENTS_ENDPOINT = 'sync/events'

export interface StartSyncResult {
  started: boolean
  busy: boolean
}

export interface SyncSubscription {
  stop(): Promise<void>
}

export function initialSyncState(): SyncRunState {
  return {
    status: 'idle',
    platforms: 0,
    completed: 0,
    succeeded: 0,
    failed: 0,
    messages: [],
    platformStates: [],
    lastSeq: 0,
    error: '',
  }
}

function isSyncEvent(value: unknown): value is SyncEvent {
  if (!value || typeof value !== 'object') {
    return false
  }
  const type = (value as { type?: unknown }).type
  return type === 'message' || type === 'start' || type === 'platform' || type === 'finish'
}

/**
 * 把一条进度事件规约成新的运行状态（纯函数，便于单测）。
 *
 * start 事件会重置整轮状态，所以即使因为重连接收了重复的事件也能得到一致结果。
 */
export function reduceSyncEvent(state: SyncRunState, event: SyncEvent): SyncRunState {
  const next: SyncRunState = { ...state, lastSeq: Math.max(state.lastSeq, event.seq) }

  if (event.type === 'start') {
    return {
      ...next,
      status: 'running',
      platforms: event.platforms,
      completed: 0,
      succeeded: 0,
      failed: 0,
      messages: [],
      platformStates: [],
      error: '',
    }
  }

  if (event.type === 'message') {
    return { ...next, messages: [...next.messages, event.text] }
  }

  if (event.type === 'platform') {
    const platformStates = [
      ...next.platformStates.filter((item) => item.pf_id !== event.pf_id),
      {
        pf_id: event.pf_id,
        name: event.name ?? '',
        appid: event.appid ?? '',
        index: event.index,
        status: event.status,
        saved: event.saved,
        error: event.error ?? '',
      },
    ].sort((a, b) => a.index - b.index)
    return {
      ...next,
      platformStates,
      completed: platformStates.length,
      succeeded: platformStates.filter((item) => item.status === 'ok').length,
      failed: platformStates.filter((item) => item.status === 'error').length,
    }
  }

  if (event.reason === 'idle') {
    // 后端在缓冲为空 / 任务被取消时补发的终止事件：订阅流没有对应的一次运行，
    // 清掉上一轮的残留状态（尤其是 running），让页面回到可重新同步的 idle
    return initialSyncState()
  }

  return {
    ...next,
    status: event.ok ? 'done' : 'failed',
    platforms: event.platforms || next.platforms,
    succeeded: event.succeeded,
    failed: event.failed,
    error: event.error ?? '',
  }
}

/** 触发一次同步；已有任务在跑时 busy 为 true，此时可以直接订阅进度 */
export async function startSync(): Promise<StartSyncResult> {
  const bridge = getBridge()
  if (!bridge) {
    throw new Error('no backend: sync is unavailable in local dev')
  }
  return (await bridge.apiPost(SYNC_ENDPOINT)) as StartSyncResult
}

/**
 * 订阅同步进度流。
 *
 * `since` 之前的 seq 不会重放，用于断线/刷新后续看；后端在本轮事件发完后关闭流，
 * 前端收到 finish 事件即可停止订阅。
 */
export async function subscribeSyncRun(options: {
  since?: number
  onEvent(event: SyncEvent): void
  onOpen?(): void
  onError?(error: Error): void
}): Promise<SyncSubscription> {
  const bridge = getBridge()
  if (!bridge) {
    throw new Error('no backend: sync progress is unavailable in local dev')
  }

  const subscriptionId = await bridge.subscribeSSE(
    SYNC_EVENTS_ENDPOINT,
    {
      onOpen: () => options.onOpen?.(),
      onMessage: (message) => {
        if (isSyncEvent(message.parsed)) {
          options.onEvent(message.parsed)
        }
      },
      onError: () => options.onError?.(new Error('sync stream error')),
    },
    toPlain({ since: options.since ?? 0 }),
  )

  return {
    async stop(): Promise<void> {
      await bridge.unsubscribeSSE(subscriptionId)
    },
  }
}
