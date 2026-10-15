/**
 * 组件测试的公共工具。
 *
 * 挂载统一走 @vue/test-utils 的 mount，并带上真实的 Vuetify 实例（见
 * ../plugins/vuetify.ts），这样主题名、图标集与断点和运行时一致。
 * 断言只允许基于文本、自有 class、属性与 emit，不要断言 Vuetify 的内部结构。
 */

import { mount, type MountingOptions, type VueWrapper } from '@vue/test-utils'
import { nextTick, type Component } from 'vue'
import { vi } from 'vitest'
import { vuetify } from '../plugins/vuetify'
import type { PluginViewBridge } from '../bridge'

/** 等 Vue 完成一轮渲染，并让同一 tick 里的 promise 链落地 */
export async function flush(): Promise<void> {
  await nextTick()
  await Promise.resolve()
  await nextTick()
}

/** 挂载一个视图/组件，默认装上真实 Vuetify；需要路由的用例自己传 router */
export function mountView(
  component: Component,
  options: MountingOptions<Record<string, unknown>> = {},
): VueWrapper {
  const globalOptions = options.global ?? {}
  return mount(component, {
    ...options,
    global: {
      ...globalOptions,
      plugins: [vuetify, ...(globalOptions.plugins ?? [])],
    },
  })
}

/**
 * 供测试注入的最小 bridge，覆盖视图真正用到的方法。
 *
 * `t()` 默认回 fallback，与本地 `pnpm dev` 的行为一致；要断言「确实走了宿主
 * 翻译」时用 overrides 覆盖 t。
 */
export function createBridgeStub(overrides: Partial<PluginViewBridge> = {}): PluginViewBridge {
  return {
    ready: vi.fn(async () => ({})),
    getContext: vi.fn(() => null),
    getLocale: vi.fn(() => 'zh-CN'),
    t: vi.fn((key: string, fallback?: string) => fallback ?? key),
    onContext: vi.fn(() => () => {}),
    apiGet: vi.fn(async () => null),
    apiPost: vi.fn(async () => null),
    subscribeSSE: vi.fn(async () => 'sub-1'),
    unsubscribeSSE: vi.fn(async () => ({ subscriptionId: 'sub-1' })),
    ...overrides,
  }
}

/** 注入 bridge 替身并返回它 */
export function installBridge(overrides: Partial<PluginViewBridge> = {}): PluginViewBridge {
  const bridge = createBridgeStub(overrides)
  window.AstrBotPluginView = bridge
  return bridge
}

/**
 * 轮询等待某个条件成立，再放行一轮渲染。
 *
 * useBridge 的首轮 bootstrap 在 dev 下要等 300ms（见 composables/useBridge.ts），
 * 固定 sleep 在慢机器上会飘，所以统一用条件等待：既快又不 flaky。
 */
export async function waitUntil(
  predicate: () => boolean,
  timeoutMs = 2000,
): Promise<void> {
  const deadline = Date.now() + timeoutMs
  while (!predicate()) {
    if (Date.now() > deadline) {
      throw new Error('waitUntil timed out')
    }
    await new Promise((resolve) => setTimeout(resolve, 20))
  }
  await flush()
}
