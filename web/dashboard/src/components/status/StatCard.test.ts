import { describe, expect, it } from 'vitest'
import StatCard from './StatCard.vue'
import { mountView } from '../../test/helpers'

describe('StatCard', () => {
  it('renders the label and the value', () => {
    const card = mountView(StatCard, { props: { title: 'QQ 平台', value: 2 } })

    expect(card.get('.qc-metric-label').text()).toBe('QQ 平台')
    expect(card.get('.qc-metric-value').text()).toBe('2')
    // 既没上限也没备注时不渲染备注行
    expect(card.find('.qc-metric-note').exists()).toBe(false)
  })

  it('turns max into a note and keeps the value neutral below the limit', () => {
    const card = mountView(StatCard, { props: { title: '指令条目', value: 3, max: 20 } })

    expect(card.get('.qc-metric-note').text()).toBe('上限 20')
    expect(card.get('.qc-metric-value').classes()).not.toContain('text-error')
  })

  it('lets an explicit note win over the max note', () => {
    const card = mountView(StatCard, {
      props: { title: '线上面板', value: 5, note: '部分场景查询失败，该值为下限' },
    })

    expect(card.get('.qc-metric-note').text()).toBe('部分场景查询失败，该值为下限')
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
})
