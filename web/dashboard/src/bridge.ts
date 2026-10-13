/**
 * AstrBot 插件视图 bridge (window.AstrBotPluginView) 的类型与访问入口。
 *
 * AstrBot 注入该 SDK 供页面与后端通信、读取主题与语言；本地 `pnpm dev` 没有注入，
 * 这里统一返回 null，由调用方降级。
 */

export interface PluginViewContext {
  pluginName?: string
  displayName?: string
  pageName?: string
  pageTitle?: string
  /** WebUI 当前语言，例如 zh-CN */
  locale?: string
  i18n?: Record<string, unknown>
  isDark?: boolean
}

/** 只声明本视图用到的 bridge 能力，其余 API 用到时再补 */
export interface PluginViewBridge {
  ready(): Promise<PluginViewContext>
  getContext(): PluginViewContext | null
  getLocale(): string
  t(key: string, fallback?: string): string
  onContext(handler: () => void): () => void
  apiGet(endpoint: string, params?: Record<string, unknown>): Promise<unknown>
  apiPost(endpoint: string, body?: unknown): Promise<unknown>
}

declare global {
  interface Window {
    AstrBotPluginView?: PluginViewBridge
    AstrBotPluginPage?: PluginViewBridge
  }
}

/** 读取 bridge；不在 AstrBot 里（或 SDK 还没注入）时返回 null */
export function getBridge(): PluginViewBridge | null {
  return window.AstrBotPluginView ?? window.AstrBotPluginPage ?? null
}

/**
 * 等待 bridge 注入。
 *
 * SDK 与视图 HTML 一起返回但脚本执行时机不保证，所以轮询等待一段时间；
 * 超时返回 null（本地开发或注入失败）交给调用方降级。
 * `intervalMs` 用于首次超时后的后台重试。
 */
export function waitForBridge(
  timeoutMs: number,
  intervalMs = 50,
): Promise<PluginViewBridge | null> {
  const existing = getBridge()
  if (existing) {
    return Promise.resolve(existing)
  }

  return new Promise((resolve) => {
    const deadline = Date.now() + timeoutMs
    const tick = (): void => {
      const bridge = getBridge()
      if (bridge) {
        resolve(bridge)
        return
      }
      if (Date.now() >= deadline) {
        resolve(null)
        return
      }
      setTimeout(tick, intervalMs)
    }
    tick()
  })
}
