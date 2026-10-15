import { describe, expect, it } from 'vitest'
import App from './App.vue'
import { mountView } from './test/helpers'

describe('App', () => {
  it('renders the shell', async () => {
    const { router } = await import('./router')
    const wrapper = mountView(App, {
      global: { plugins: [router], stubs: { RouterView: true } },
    })

    expect(wrapper.find('.v-application').exists()).toBe(true)
    expect(wrapper.get('.qc-sidebar-brand-title').text()).toBe('指令面板')
  })
})
