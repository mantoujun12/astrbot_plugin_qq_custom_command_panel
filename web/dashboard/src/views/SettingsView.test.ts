import { describe, expect, it } from 'vitest'
import { mountView, installBridge } from '../test/helpers'
import SettingsView from './SettingsView.vue'

describe('SettingsView', () => {
  it('renders the settings placeholder with a work-in-progress notice', async () => {
    installBridge()
    const { router } = await import('../router')
    const wrapper = mountView(SettingsView, { global: { plugins: [router] } })

    expect(wrapper.get('.qc-title').text()).toBe('设置')
    expect(wrapper.text()).toContain('插件级通用设置会集中在这里。')
    expect(wrapper.text()).toContain('功能施工中')
    expect(wrapper.text()).toContain('这个页面还在建设中，后续会提供插件级通用设置。')
    expect(wrapper.find('.qc-wip').exists()).toBe(true)
  })
})
