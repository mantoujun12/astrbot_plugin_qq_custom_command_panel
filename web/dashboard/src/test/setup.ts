/**
 * 测试环境兜底：每个用例结束后把宿主注入的全局状态清干净。
 *
 * bridge 是宿主通过 `window.AstrBotPluginView` 注入的全局对象，`useBridge` /
 * `useSyncRun` 又是模块级单例，残留会让下一个用例拿到上一个用例的连接状态。
 */

import { afterEach, vi } from 'vitest'

afterEach(() => {
  delete window.AstrBotPluginView
  delete window.AstrBotPluginPage
  delete document.documentElement.dataset.theme
  // Vuetify 的浮层挂在 body 上，用例之间一并清理
  document.body.innerHTML = ''
  vi.unstubAllEnvs()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  vi.useRealTimers()
})
