import { describe, expect, it, vi } from 'vitest'
import type { Ref } from 'vue'
import { VAppBar, VNavigationDrawer } from 'vuetify/components'
import type { PluginViewContext } from '../bridge'
import { flush, installBridge, mountView, waitUntil } from '../test/helpers'

/**
 * 窄屏/宽屏的判定来自 Vuetify 的 useDisplay，靠 viewport 在 happy-dom 里控制不稳，
 * 这里只把 useDisplay 换成一个可写的 ref，其余 Vuetify 能力仍走真实实现。
 */
const display = vi.hoisted(() => ({ mobile: undefined as unknown as Ref<boolean> }))

vi.mock('vuetify', async (importOriginal) => {
  const vue = await import('vue')
  display.mobile = vue.ref(false)
  const actual = await importOriginal<typeof import('vuetify')>()
  return { ...actual, useDisplay: () => ({ mobile: display.mobile }) }
})

/** AppShell 依赖 useAppShell → useBridge 的单例，所以每个用例重置模块后再引 */
async function mountShell(options: { context?: PluginViewContext; mobile?: boolean } = {}) {
  const context = options.context
  const bridge = installBridge({
    ready: vi.fn(async () => context ?? {}),
    getContext: vi.fn(() => context ?? null),
  })

  vi.resetModules()
  const { useBridge } = await import('../composables/useBridge')
  const ready = useBridge().ready
  const { default: AppShell } = await import('./AppShell.vue')
  await waitUntil(() => ready.value)

  display.mobile.value = options.mobile === true
  const wrapper = mountView(AppShell, { global: { stubs: { RouterView: true } } })
  await flush()

  return { wrapper, bridge }
}

function drawerState(wrapper: ReturnType<typeof mountView>): unknown {
  return wrapper.findComponent(VNavigationDrawer).props('modelValue')
}

describe('AppShell', () => {
  it('keeps the drawer permanent on wide screens and toggles between rail and full', async () => {
    const { wrapper } = await mountShell()

    expect(wrapper.findComponent(VAppBar).exists()).toBe(false)
    expect(wrapper.findComponent(VNavigationDrawer).props('permanent')).toBe(true)
    expect(drawerState(wrapper)).toBe(true)
    expect(wrapper.get('.qc-sidebar-brand-title').text()).toBe('指令面板')

    await wrapper.get('button[aria-label="收起侧边栏"]').trigger('click')
    expect(wrapper.get('.qc-sidebar-brand').classes()).toContain('qc-sidebar-brand--rail')
    expect(wrapper.find('button[aria-label="展开侧边栏"]').exists()).toBe(true)

    await wrapper.get('button[aria-label="展开侧边栏"]').trigger('click')
    expect(wrapper.get('.qc-sidebar-brand').classes()).not.toContain(
      'qc-sidebar-brand--rail',
    )
  })

  it('ignores drawer updates on wide screens', async () => {
    const { wrapper } = await mountShell()

    wrapper.findComponent(VNavigationDrawer).vm.$emit('update:modelValue', false)
    await flush()

    // 宽屏下抽屉常驻，只由我们自己的开关控制
    expect(drawerState(wrapper)).toBe(true)
  })

  it('swaps in an app bar on narrow screens', async () => {
    const { wrapper } = await mountShell({ mobile: true })

    expect(wrapper.findComponent(VAppBar).exists()).toBe(true)
    expect(wrapper.findComponent(VNavigationDrawer).props('temporary')).toBe(true)
    // 窄屏抽屉默认收起，标题挪到 app bar
    expect(drawerState(wrapper)).toBe(false)
    expect(wrapper.get('.v-app-bar').text()).toContain('指令面板')
    expect(wrapper.find('button[aria-label="关闭侧边栏"]').exists()).toBe(true)

    await wrapper.get('button[aria-label="打开侧边栏"]').trigger('click')
    expect(drawerState(wrapper)).toBe(true)

    await wrapper.get('button[aria-label="关闭侧边栏"]').trigger('click')
    expect(drawerState(wrapper)).toBe(false)
  })

  it('applies drawer updates on narrow screens', async () => {
    const { wrapper } = await mountShell({ mobile: true })

    wrapper.findComponent(VNavigationDrawer).vm.$emit('update:modelValue', true)
    await flush()

    expect(drawerState(wrapper)).toBe(true)
  })

  it('prefers the view title from the host context', async () => {
    const { wrapper } = await mountShell({
      context: { pageTitle: '状态概览', displayName: 'QQ 指令面板' },
    })

    expect(wrapper.get('.qc-sidebar-brand-title').text()).toBe('状态概览')
  })

  it('falls back to the plugin display name', async () => {
    const { wrapper } = await mountShell({ context: { displayName: 'QQ 指令面板' } })

    expect(wrapper.get('.qc-sidebar-brand-title').text()).toBe('QQ 指令面板')
  })

  it('follows the host theme', async () => {
    const dark = await mountShell({ context: { isDark: true } })
    expect(dark.wrapper.get('.v-application').classes()).toContain(
      'v-theme--qcPanelThemeDark',
    )

    const light = await mountShell({ context: { isDark: false } })
    expect(light.wrapper.get('.v-application').classes()).toContain('v-theme--qcPanelTheme')
  })
})
