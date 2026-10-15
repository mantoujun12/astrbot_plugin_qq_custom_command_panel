import { describe, expect, it } from 'vitest'
import { VTooltip } from 'vuetify/components'
import NavItem from './NavItem.vue'
import { mountView } from '../../test/helpers'

async function mountItem(options: { rail?: boolean } = {}) {
  const { router } = await import('../../router')
  return mountView(NavItem, {
    props: {
      to: '/status',
      icon: 'icon',
      labelKey: 'pages.dashboard.nav.status',
      fallback: '状态概览',
      ...options,
    },
    global: { plugins: [router] },
  })
}

describe('NavItem', () => {
  it('renders the fallback copy and links to the view', async () => {
    const wrapper = await mountItem()

    expect(wrapper.text()).toContain('状态概览')
    expect(wrapper.find('a').attributes('href')).toContain('/status')
    // rail 折叠后标题会被 Vuetify 隐藏，tooltip 必须补上无障碍名称
    expect(wrapper.findComponent(VTooltip).props('disabled')).toBe(true)
  })

  it('enables the tooltip when the sidebar is a rail', async () => {
    const wrapper = await mountItem({ rail: true })

    expect(wrapper.findComponent(VTooltip).props('disabled')).toBe(false)
  })
})
