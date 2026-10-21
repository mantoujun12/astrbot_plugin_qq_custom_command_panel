/** Dashboard 日志页的数据契约，对应 core/log_stream.py 的 LogEntry。 */

export const LOG_LEVELS = ['debug', 'info', 'warning', 'error', 'critical'] as const

export type LogLevel = (typeof LOG_LEVELS)[number]

export interface LogEvent {
  type: 'log'
  seq: number
  /** UTC ISO 8601，展示时按 WebUI locale 转成本地时间 */
  timestamp: string
  level: LogLevel
  message: string
  traceback?: string
}

export interface LogStreamInfo {
  type: 'stream'
  id: string
  reset: boolean
}
