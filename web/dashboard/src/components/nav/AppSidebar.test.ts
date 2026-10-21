import { describe, expect, it } from 'vitest'
import AppSidebar from './AppSidebar.vue'
import { mountView } from '../../test/helpers'
import { version } from '../../../package.json'

async function mountSidebar(options: { rail?: boolean } = {}) {
  const { router } = await import('../../router')
  return mountView(AppSidebar, {
    props: {
      title: '指令面板',
      toggleIcon: 'toggle-icon',
      toggleLabel: '关闭侧边栏',
      ...options,
    },
    global: { plugins: [router] },
  })
}

describe('AppSidebar', () => {
  it('shows the title and every navigation entry in order', async () => {
    const wrapper = await mountSidebar()

    expect(wrapper.get('.qc-sidebar-brand-title').text()).toBe('指令面板')
    expect(wrapper.text()).toContain('状态概览')
    expect(wrapper.text()).toContain('机器人')
    expect(wrapper.text()).toContain('日志')
    expect(wrapper.text()).toContain('兼容性')
    expect(wrapper.text()).toContain('设置')
    expect(wrapper.findAll('a').map((link) => link.attributes('href'))).toEqual([
      expect.stringContaining('/status'),
      expect.stringContaining('/robots'),
      expect.stringContaining('/logs'),
      expect.stringContaining('/compatibility'),
      expect.stringContaining('/settings'),
    ])
  })

  it('hides the title when collapsed into a rail', async () => {
    const wrapper = await mountSidebar({ rail: true })

    expect(wrapper.find('.qc-sidebar-brand-title').exists()).toBe(false)
    expect(wrapper.get('.qc-sidebar-brand').classes()).toContain('qc-sidebar-brand--rail')
  })

  it('shows the plugin version at the bottom, and hides it in the rail', async () => {
    const wrapper = await mountSidebar()

    expect(wrapper.get('.qc-sidebar-version').text()).toBe(`v${version}`)

    const railed = await mountSidebar({ rail: true })
    expect(railed.find('.qc-sidebar-version').exists()).toBe(false)
  })

  it('asks the shell to toggle the sidebar', async () => {
    const wrapper = await mountSidebar()

    await wrapper.get('button[aria-label="关闭侧边栏"]').trigger('click')

    expect(wrapper.emitted('toggle')).toHaveLength(1)
  })
})
