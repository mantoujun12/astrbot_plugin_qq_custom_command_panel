import { describe, expect, it } from 'vitest'
import StatCard from './StatCard.vue'
import { mountView } from '../../test/helpers'

describe('StatCard', () => {
  it('renders the label and the value', () => {
    const card = mountView(StatCard, { props: { title: 'QQ 平台', value: 2 } })

    expect(card.get('.qc-metric-label').text()).toBe('QQ 平台')
    expect(card.get('.qc-metric-value').text()).toBe('2')
    expect(card.find('.qc-metric-note').exists()).toBe(false)
  })

  it('renders the icon as a corner watermark', () => {
    const withIcon = mountView(StatCard, {
      props: { title: 'QQ 平台', value: 2, icon: 'icon-qq' },
    })

    expect(withIcon.find('.qc-stat-watermark .v-icon').exists()).toBe(true)

    const withoutIcon = mountView(StatCard, { props: { title: 'QQ 平台', value: 2 } })
    expect(withoutIcon.find('.qc-stat-watermark').exists()).toBe(false)
  })

  it('keeps the value neutral below the limit without rendering a note', () => {
    const card = mountView(StatCard, { props: { title: '指令条目', value: 3, max: 20 } })

    expect(card.find('.qc-metric-note').exists()).toBe(false)
    expect(card.get('.qc-metric-value').classes()).not.toContain('text-error')
  })

  it('highlights the value once it reaches the limit', () => {
    const atLimit = mountView(StatCard, {
      props: { title: '指令条目', value: 20, max: 20, emphasizeAtLimit: true },
    })
    const belowLimit = mountView(StatCard, {
      props: { title: '线上面板', value: 39, max: 40, emphasizeAtLimit: true },
    })

    expect(atLimit.get('.qc-metric-value').classes()).toContain('text-error')
    expect(belowLimit.get('.qc-metric-value').classes()).not.toContain('text-error')
  })

  it('keeps the value neutral when no capacity exists', () => {
    const card = mountView(StatCard, {
      props: { title: '指令条目', value: 0, max: 0, emphasizeAtLimit: true },
    })

    expect(card.get('.qc-metric-value').classes()).not.toContain('text-error')
  })
})
