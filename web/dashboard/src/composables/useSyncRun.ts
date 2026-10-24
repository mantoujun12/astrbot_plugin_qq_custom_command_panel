/**
 * 同步运行状态的全局单例。
 *
 * 状态页的同步卡片和设置页的「保存并同步」共用同一份状态：设置页触发同步后
 * 跳到状态页，进度卡片接着显示，不需要重新触发。
 */

import { computed, readonly, ref } from 'vue'
import {
  initialSyncState,
  reduceSyncEvent,
  startSync,
  subscribeSyncRun,
  type SyncSubscription,
} from '../api/sync'
import { useBridge } from './useBridge'
import type { SyncRunState } from '../types/dashboard'

const state = ref<SyncRunState>(initialSyncState())
const attaching = ref(false)

let subscription: SyncSubscription | null = null
let attachSeq = 0

/** 只释放已建立的订阅，不递增 attachSeq，供 subscribe 交接旧流时使用 */
async function releaseSubscription(): Promise<void> {
  const current = subscription
  subscription = null
  if (current) {
    await current.stop()
  }
}

/** 停止订阅，并让所有尚未建立的订阅失效（它们拿到 id 后会自行退订） */
async function stopSubscription(): Promise<void> {
  attachSeq += 1
  await releaseSubscription()
}

function setError(error: unknown): void {
  state.value = {
    ...state.value,
    status: 'failed',
    error: error instanceof Error ? error.message : String(error),
  }
}

/**
 * 订阅进度流。
 *
 * since 之前的 seq 不会重放：0 表示回放整个事件缓冲（页面首次进入时能看到上一轮
 * 结果），续订时传当前 lastSeq 只取新事件。
 */
async function subscribe(since: number, onFinish?: () => void): Promise<void> {
  const seq = ++attachSeq
  await releaseSubscription()
  if (seq !== attachSeq) {
    // 退订旧流期间被停止或被新订阅接管，这一条不再建立
    return
  }
  const next = await subscribeSyncRun({
    since,
    onEvent: (event) => {
      if (seq !== attachSeq) return
      state.value = reduceSyncEvent(state.value, event)
      if (event.type === 'finish') {
        void stopSubscription()
        // idle 只是“当前没有可续看的运行”，不是一次真实同步结束，无需刷新状态页
        if (event.reason !== 'idle') {
          onFinish?.()
        }
      }
    },
    onError: (error) => {
      if (seq !== attachSeq) return
      state.value = { ...state.value, status: 'failed', error: error.message }
    },
  })
  if (seq !== attachSeq) {
    // 期间又发起了新的订阅，丢弃这一个，避免持有两条流
    await next.stop()
    return
  }
  subscription = next
}

export function useSyncRun() {
  const { hasBackend } = useBridge()

  /** 只有连上 AstrBot 后端才能同步，mock 模式下入口禁用 */
  const available = computed(() => hasBackend.value)
  const running = computed(() => state.value.status === 'running')
  const hasRun = computed(() => state.value.status !== 'idle')

  /** 触发同步并订阅进度；已有任务在跑时直接接管进度显示 */
  async function start(options: { onFinish?: () => void } = {}): Promise<void> {
    if (!hasBackend.value) {
      throw new Error('no backend: sync is unavailable in local dev')
    }
    await startSync()
    try {
      await subscribe(0, options.onFinish)
    } catch (error) {
      // 任务已经在跑了，这里失败只影响进度展示，页面要能看到原因并能重连
      setError(error)
    }
  }

  /** 进入页面时接上当前进度；任务已结束时回放上一轮结果 */
  function attach(onFinish?: () => void): void {
    if (!hasBackend.value || attaching.value) {
      return
    }
    attaching.value = true
    void subscribe(0, onFinish)
      .catch(setError)
      .finally(() => {
        attaching.value = false
      })
  }

  /** 手动重连：从已收到的位置继续 */
  function retry(onFinish?: () => void): void {
    if (!hasBackend.value) {
      return
    }
    void subscribe(state.value.lastSeq, onFinish).catch(setError)
  }

  return {
    state: readonly(state),
    available,
    running,
    hasRun,
    start,
    attach,
    retry,
    stop: stopSubscription,
  }
}
