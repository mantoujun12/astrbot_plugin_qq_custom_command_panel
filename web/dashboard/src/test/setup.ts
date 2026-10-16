/**
 * 测试环境兜底：每个用例结束后把宿主注入的全局状态清干净。
 *
 * bridge 是宿主通过 `window.AstrBotPluginView` 注入的全局对象，`useBridge` /
 * `useSyncRun` 又是模块级单例，残留会让下一个用例拿到上一个用例的连接状态。
 */

import { afterEach, vi } from 'vitest'

/**
 * happy-dom 没实现 visualViewport，而 Vuetify 的浮层（v-dialog / v-menu）会直接引用
 * 这个全局标识符。它写的是 `visualViewport?.addEventListener(...)`，但可选链只挡
 * null / undefined，挡不住「标识符未声明」——缺了会抛 ReferenceError 而不是静默跳过。
 */
if (!('visualViewport' in window)) {
  Object.defineProperty(window, 'visualViewport', {
    configurable: true,
    value: {
      width: 0,
      height: 0,
      offsetLeft: 0,
      offsetTop: 0,
      pageLeft: 0,
      pageTop: 0,
      scale: 1,
      addEventListener: () => {},
      removeEventListener: () => {},
    },
  })
}

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
