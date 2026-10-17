import { afterEach, describe, expect, it, vi } from 'vitest'
import type { DOMWrapper, VueWrapper } from '@vue/test-utils'
import { VSelect } from 'vuetify/components'
import type { PluginConfigResponse } from '../types/dashboard'
import { flush, installBridge, mountView, waitUntil } from '../test/helpers'
import { vuetify } from '../plugins/vuetify'
import {
  DEFAULT_THEME_COLORS,
  THEME_LIGHT,
  applyThemeColors,
} from '../theme'
import { PLUGIN_VERSION } from '../version'

vi.mock('../api/dashboard', () => ({
  fetchStatus: vi.fn(),
  fetchConfig: vi.fn(),
  saveConfig: vi.fn(),
}))

function configFixture(overrides: Partial<PluginConfigResponse> = {}): PluginConfigResponse {
  return {
    language: 'zh-CN',
    primary_color: '#3c96ca',
    secondary_color: '#2f86bd',
    scenes: ['c2c', 'group'],
    available_scenes: ['c2c', 'group', 'channel', 'dm'],
    qq_platforms: [],
    selected_commands: [],
    limits: { name_max: 14, desc_max: 30, items_max: 20 },
    ...overrides,
  }
}

/** 按可见文案精确找按钮：Vuetify 的按钮结构不是稳定的断言目标 */
function button(wrapper: VueWrapper, label: string): DOMWrapper<Element> {
  const wanted = label.replace(/\s+/g, '')
  const found = wrapper
    .findAll('button')
    .find((node) => (node.text() ?? '').replace(/\s+/g, '') === wanted)
  if (!found) {
    throw new Error(`button not found: ${label}`)
  }
  return found
}

/** 设置页同样依赖 useBridge 的模块级单例，每个用例重置模块后再引 */
async function loadSettingsView(options: { withBackend?: boolean } = {}) {
  const bridge = options.withBackend === false ? null : installBridge()
  vi.resetModules()
  const api = await import('../api/dashboard')
  const { router } = await import('../router')
  const { default: SettingsView } = await import('./SettingsView.vue')

  return {
    bridge,
    api,
    router,
    async mount() {
      const wrapper = mountView(SettingsView, { global: { plugins: [router] } })
      await waitUntil(() => vi.mocked(api.fetchConfig).mock.calls.length > 0)
      await flush()
      return wrapper
    },
  }
}

afterEach(() => {
  applyThemeColors(vuetify.theme, DEFAULT_THEME_COLORS)
})

describe('SettingsView', () => {
  it('loads the basic configuration into the form', async () => {
    const { api, mount } = await loadSettingsView()
    vi.mocked(api.fetchConfig).mockResolvedValue(configFixture())

    const wrapper = await mount()

    expect(api.fetchConfig).toHaveBeenCalledTimes(1)
    expect(wrapper.get('.qc-title').text()).toBe('设置')
    expect(wrapper.text()).toContain('基础配置')
    expect(wrapper.text()).toContain('日志语言')
    expect(wrapper.text()).toContain('主题配色')
    expect(wrapper.text()).toContain('主色')
    expect(wrapper.text()).toContain('辅助色')
    expect(wrapper.text()).toContain('关于插件')
    expect(wrapper.text()).toContain('QQ 自定义指令面板')
    expect(wrapper.text()).toContain(PLUGIN_VERSION)
    expect(wrapper.text()).toContain('GitHub 仓库')
    const repositoryLink = wrapper
      .findAll('a')
      .find((node) => node.text().replace(/\s+/g, '') === '访问GitHub')
    expect(repositoryLink?.attributes('href')).toBe(
      'https://github.com/mantoujun12/astrbot_plugin_qq_custom_command_panel',
    )
    expect(repositoryLink?.attributes('target')).toBe('_blank')
    // 生效场景已挪回「兼容性」页，这里只剩日志语言
    expect(wrapper.text()).not.toContain('生效场景')

    const selects = wrapper.findAllComponents(VSelect)
    expect(selects).toHaveLength(1)
    expect(selects[0]?.props('modelValue')).toBe('zh-CN')
    expect(wrapper.findAll('.qc-color-trigger')).toHaveLength(2)
  })

  it('submits only the fields this page owns', async () => {
    const { api, mount } = await loadSettingsView()
    vi.mocked(api.fetchConfig).mockResolvedValue(configFixture())
    vi.mocked(api.saveConfig).mockResolvedValue(
      configFixture({
        language: 'en-US',
        primary_color: '#112233',
        secondary_color: '#445566',
        scenes: ['c2c'],
      }),
    )

    const wrapper = await mount()
    // v-select 的下拉挂在 body 上，直接驱动 model 比点浮层稳
    wrapper.findAllComponents(VSelect)[0]?.vm.$emit('update:modelValue', 'en-US')
    const colorFields = wrapper.findAllComponents({ name: 'ThemeColorField' })
    colorFields[0]?.vm.$emit('update:modelValue', '#112233')
    colorFields[1]?.vm.$emit('update:modelValue', '#445566')

    await button(wrapper, '保存').trigger('click')
    await waitUntil(() => vi.mocked(api.saveConfig).mock.calls.length > 0)
    await flush()

    // 生效场景、平台凭证与指令条目都归「兼容性」页，这里不能带上，否则会覆盖那边的改动
    expect(api.saveConfig).toHaveBeenCalledWith({
      language: 'en-US',
      primary_color: '#112233',
      secondary_color: '#445566',
    })
    expect(wrapper.text()).toContain('设置已保存并生效。')
    expect(vuetify.theme.themes.value[THEME_LIGHT]?.colors.primary).toBe('#112233')
    expect(vuetify.theme.themes.value[THEME_LIGHT]?.colors.secondary).toBe('#445566')
  })

  it('keeps the form editable but disables save for an invalid color', async () => {
    const { api, mount } = await loadSettingsView()
    vi.mocked(api.fetchConfig).mockResolvedValue(configFixture())

    const wrapper = await mount()
    wrapper
      .findAllComponents({ name: 'ThemeColorField' })[0]
      ?.vm.$emit('update:modelValue', 'not-a-color')
    await flush()

    expect(wrapper.text()).toContain('请输入 #RRGGBB 格式的颜色。')
    expect(button(wrapper, '保存').attributes('disabled')).toBeDefined()
    expect(wrapper.findAllComponents({ name: 'ThemeColorField' })[0]?.props('disabled')).toBe(
      false,
    )
  })

  it('reports a failed load and keeps saving disabled', async () => {
    const { api, mount } = await loadSettingsView()
    vi.mocked(api.fetchConfig).mockRejectedValue(new Error('config failed'))

    const wrapper = await mount()

    expect(wrapper.text()).toContain('config failed')
    expect(wrapper.find('.qc-card').exists()).toBe(false)
    expect(button(wrapper, '保存').attributes('disabled')).toBeDefined()
  })

  it('labels mock data and refuses to fake a save in local dev', async () => {
    const { api, mount } = await loadSettingsView({ withBackend: false })
    vi.mocked(api.fetchConfig).mockResolvedValue(configFixture())

    const wrapper = await mount()

    expect(wrapper.text()).toContain('本地开发环境：可编辑预览，但不能保存配置。')
    expect(button(wrapper, '保存').attributes('disabled')).toBeDefined()
    expect(wrapper.findAll('.qc-color-trigger')[0]?.attributes('disabled')).toBeUndefined()
    expect(wrapper.findAllComponents({ name: 'ThemeColorField' })[0]?.props('disabled')).toBe(
      false,
    )

    wrapper
      .findAllComponents({ name: 'ThemeColorField' })[0]
      ?.vm.$emit('update:modelValue', '#112233')
    await flush()

    expect(vuetify.theme.themes.value[THEME_LIGHT]?.colors.primary).toBe('#112233')

    await button(wrapper, '保存').trigger('click')
    await flush()

    expect(api.saveConfig).not.toHaveBeenCalled()
    expect(wrapper.text()).not.toContain('设置已保存并生效。')
  })

  it('reloads the config on demand', async () => {
    const { api, mount } = await loadSettingsView()
    vi.mocked(api.fetchConfig).mockResolvedValue(configFixture())

    const wrapper = await mount()
    await button(wrapper, '重新载入').trigger('click')
    await waitUntil(() => vi.mocked(api.fetchConfig).mock.calls.length === 2)

    expect(api.fetchConfig).toHaveBeenCalledTimes(2)
  })
})
