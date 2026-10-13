/**
 * 视图与 AstrBot bridge 的接口: 主题 (isDark)、语言 (locale)、翻译 (t)。
 *
 * bridge 和上下文全局只有一份, 导航和视图共享。本地开发没有 bridge,
 * 此时 t() 退回调用方传入的 fallback 文案, isDark 跟随系统偏好, 保证
 * `pnpm dev` 下界面依然完整可读。
 */

import { computed, ref, shallowRef } from 'vue'
import { waitForBridge } from '../bridge'
import type { PluginViewBridge, PluginViewContext } from '../bridge'

const bridge = shallowRef<PluginViewBridge | null>(null)
const context = shallowRef<PluginViewContext | null>(null)
const ready = ref(false)

/** 初始主题: 优先用 AstrBot 预注入的 <html data-theme>, 避免首屏闪一下 */
function initialIsDark(): boolean {
  const attr = document.documentElement.dataset.theme
  if (attr) {
    return attr === 'dark'
  }
  return window.matchMedia('(prefers-color-scheme: dark)').matches
}

const isDark = ref(initialIsDark())

let started = false

function applyContext(next: PluginViewContext): void {
  context.value = next
  if (typeof next.isDark === 'boolean') {
    isDark.value = next.isDark
  }
}

async function bootstrap(): Promise<void> {
  // dev 下不会出现 bridge, 少等一会, 避免白屏
  const found = await waitForBridge(import.meta.env.DEV ? 300 : 3000)
  if (!found) {
    ready.value = true
    return
  }

  bridge.value = found
  // 先订阅上下文变化, 再拉取初始上下文: 即使初始拉取失败, 后续变化仍能生效
  found.onContext(() => {
    const next = found.getContext()
    if (next) {
      applyContext(next)
    }
  })
  try {
    applyContext(await found.ready())
  } catch (err) {
    // 上下文拉取失败不应阻塞视图: bridge 已经可用, 按默认主题/语言继续渲染
    console.warn('[qq-command-panel] bridge ready() failed', err)
  }
  ready.value = true
}

export function useBridge() {
  if (!started) {
    started = true
    void bootstrap()
  }

  const locale = computed(() => context.value?.locale ?? 'zh-CN')

  /**
   * 是否已连上 AstrBot 后端。
   *
   * bridge 由宿主异步注入: 只有 ready 后 bridge 非空, 视图才真的能调到插件
   * 后端; 本地 `pnpm dev` 没有 bridge, 恒为 false (调用方据此退回 mock)。
   */
  const hasBackend = computed(() => bridge.value !== null)

  function t(key: string, fallback?: string): string {
    // 读一下 locale, 让调用方在语言切换 (context 变化) 时重新求值
    void locale.value
    return bridge.value ? bridge.value.t(key, fallback) : (fallback ?? key)
  }

  return { bridge, context, ready, hasBackend, isDark, locale, t }
}
