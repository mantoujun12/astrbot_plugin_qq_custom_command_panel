import { describe, expect, it } from 'vitest'
import { defineComponent, h } from 'vue'
import { mdiCheckCircleOutline } from '@mdi/js'
import { VIcon, VRow } from 'vuetify/components'
import { useDisplay, useTheme } from 'vuetify'
import { THEME_DARK, THEME_LIGHT } from '../theme'
import { mountView } from '../test/helpers'

/** 把 Vuetify 实例上的配置读出来渲染成属性，避免断言内部对象结构 */
const Probe = defineComponent({
  name: 'VuetifyProbe',
  setup() {
    const theme = useTheme()
    const display = useDisplay()
    return () =>
      h('div', [
        h('span', { 'data-theme': theme.global.name.value }),
        h('span', { 'data-themes': Object.keys(theme.themes.value).join(',') }),
        h('span', { 'data-thresholds': JSON.stringify(display.thresholds.value) }),
        h('span', { 'data-mobile-breakpoint': String(display.mobileBreakpoint.value) }),
        h(VIcon, { icon: mdiCheckCircleOutline, class: 'probe-icon' }),
      ])
  },
})

describe('vuetify instance', () => {
  it('renders mdi icons as inline svg instead of an icon font', () => {
    const wrapper = mountView(Probe)

    const path = wrapper.get('.probe-icon svg path')
    expect(path.attributes('d')).toBe(mdiCheckCircleOutline)
  })

  it('registers both panel themes and starts light', () => {
    const wrapper = mountView(Probe)

    expect(wrapper.get('[data-theme]').attributes('data-theme')).toBe(THEME_LIGHT)
    const themes = wrapper.get('[data-themes]').attributes('data-themes') ?? ''
    expect(themes.split(',')).toContain(THEME_LIGHT)
    expect(themes.split(',')).toContain(THEME_DARK)
  })

  it('tightens the grid gutter for every row via defaults', () => {
    const wrapper = mountView(
      defineComponent({
        name: 'RowProbe',
        setup: () => () => h(VRow, null, { default: () => h('div') }),
      }),
    )

    // defaults 里没生效的话会是 v-row--density-default（24px 沟槽）
    expect(wrapper.get('.v-row').classes()).toContain('v-row--density-comfortable')
  })

  it('restores the Vuetify 3 breakpoints the host uses', () => {
    const wrapper = mountView(Probe)

    expect(wrapper.get('[data-thresholds]').attributes('data-thresholds')).toBe(
      JSON.stringify({ xs: 0, sm: 600, md: 960, lg: 1280, xl: 1920, xxl: 2560 }),
    )
    // 窄屏切换临时抽屉的界线取 md（960px），与宿主页面层的 959.98px 一致
    expect(wrapper.get('[data-mobile-breakpoint]').attributes('data-mobile-breakpoint')).toBe(
      'md',
    )
  })

})
