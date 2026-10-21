/**
 * 插件实时日志 SSE。
 *
 * 后端保留最近 1000 条并支持 since 回放；本地 dev 没有 bridge，由页面明确
 * 展示 mock 日志，不能把 mock 数据伪装成实时连接。
 */

import { getBridge } from '../bridge'
import { toPlain } from './serialize'
import { LOG_LEVELS } from '../types/logs'
import type { LogEvent, LogLevel, LogStreamInfo } from '../types/logs'

const LOG_EVENTS_ENDPOINT = 'logs/events'

export const MOCK_LOGS: LogEvent[] = [
  {
    type: 'log',
    seq: 1,
    timestamp: '2026-10-21T02:18:04.120Z',
    level: 'debug',
    message: '已读取插件配置，开始准备面板同步。',
  },
  {
    type: 'log',
    seq: 2,
    timestamp: '2026-10-21T02:18:04.260Z',
    level: 'info',
    message: '正在同步单聊场景的指令面板。',
  },
  {
    type: 'log',
    seq: 3,
    timestamp: '2026-10-21T02:18:04.450Z',
    level: 'warning',
    message: '群聊场景的旧面板不存在，将继续创建新面板。',
  },
  {
    type: 'log',
    seq: 4,
    timestamp: '2026-10-21T02:18:04.690Z',
    level: 'error',
    message: '示例错误：频道场景同步失败。',
    traceback: 'Traceback (most recent call last):\n  ...\nRuntimeError: mock failure',
  },
  {
    type: 'log',
    seq: 5,
    timestamp: '2026-10-21T02:18:04.820Z',
    level: 'critical',
    message: '示例严重日志：需要立即检查机器人凭证。',
  },
]

export function getMockLogs(): LogEvent[] {
  return MOCK_LOGS.map((entry) => ({ ...entry }))
}

export interface LogSubscription {
  stop(): Promise<void>
}

function isLogLevel(value: unknown): value is LogLevel {
  return typeof value === 'string' && (LOG_LEVELS as readonly string[]).includes(value)
}

export function isLogEvent(value: unknown): value is LogEvent {
  if (!value || typeof value !== 'object') {
    return false
  }
  const event = value as Record<string, unknown>
  return (
    event.type === 'log' &&
    typeof event.seq === 'number' &&
    Number.isInteger(event.seq) &&
    event.seq >= 0 &&
    typeof event.timestamp === 'string' &&
    event.timestamp.length > 0 &&
    isLogLevel(event.level) &&
    typeof event.message === 'string' &&
    (event.traceback === undefined || typeof event.traceback === 'string')
  )
}

export function isLogStreamInfo(value: unknown): value is LogStreamInfo {
  if (!value || typeof value !== 'object') {
    return false
  }
  const event = value as Record<string, unknown>
  return event.type === 'stream' && typeof event.id === 'string' && typeof event.reset === 'boolean'
}

export async function subscribeLogs(options: {
  since?: number
  streamId?: string
  onEvent(event: LogEvent): void
  onStream?(info: LogStreamInfo): void
  onOpen?(): void
  onError?(error: Error): void
}): Promise<LogSubscription> {
  const bridge = getBridge()
  if (!bridge) {
    throw new Error('no backend: live logs are unavailable in local dev')
  }

  const subscriptionId = await bridge.subscribeSSE(
    LOG_EVENTS_ENDPOINT,
    {
      onOpen: () => options.onOpen?.(),
      onMessage: (message) => {
        if (isLogEvent(message.parsed)) {
          options.onEvent(message.parsed)
        } else if (isLogStreamInfo(message.parsed)) {
          options.onStream?.(message.parsed)
        } else if (
          message.parsed &&
          typeof message.parsed === 'object' &&
          (message.parsed as Record<string, unknown>).type === 'error'
        ) {
          options.onError?.(new Error('log stream rejected'))
        }
      },
      onError: () => options.onError?.(new Error('log stream error')),
    },
    toPlain({
      since: options.since ?? 0,
      ...(options.streamId ? { streamId: options.streamId } : {}),
    }),
  )

  return {
    async stop(): Promise<void> {
      await bridge.unsubscribeSSE(subscriptionId)
    },
  }
}
