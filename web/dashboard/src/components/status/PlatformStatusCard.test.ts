import { describe, expect, it } from 'vitest'
import PlatformStatusCard from './PlatformStatusCard.vue'
import type { PlatformStatus, ScenePanelStatus } from '../../types/dashboard'
import { mountView } from '../../test/helpers'

function platform(overrides: Partial<PlatformStatus> = {}): PlatformStatus {
  return {
    pf_id: '主机器人',
    appid: '102*****89',
    platform: 'qq_official',
    scenes: [{ scope: 'c2c', state: 'synced', panel_id: 'panel_1a2b3c', items_count: 3 }],
    ...overrides,
  }
}

function card(scene: ScenePanelStatus, extra: Partial<PlatformStatus> = {}) {
  return mountView(PlatformStatusCard, {
    props: { platform: platform({ ...extra, scenes: [scene] }) },
  })
}

describe('PlatformStatusCard', () => {
  it('shows the platform identity and the panel detail', () => {
    const wrapper = card({ scope: 'c2c', state: 'synced', panel_id: 'panel_1a2b3c', items_count: 3 })

    expect(wrapper.text()).toContain('主机器人')
    expect(wrapper.text()).toContain('qq_official')
    expect(wrapper.text()).toContain('appid: 102*****89')
    expect(wrapper.text()).toContain('panel_1a2b3c · 3 条')
  })

  it('shows the panel id alone when the item count is missing', () => {
    const wrapper = card({ scope: 'group', state: 'synced', panel_id: 'panel_4d5e6f' })

    expect(wrapper.text()).toContain('panel_4d5e6f')
    expect(wrapper.text()).not.toContain('条')
  })

  it.each([
    ['synced', '已同步'],
    ['duplicate', '重复面板'],
    ['missing', '线上缺失'],
    ['failed', '查询失败'],
  ] as const)('labels the %s scene', (state, label) => {
    const wrapper = card({ scope: 'c2c', state })

    expect(wrapper.text()).toContain(label)
  })

  it('shows a platform level error instead of the scene chip', () => {
    const wrapper = card({ scope: 'c2c', state: 'failed' }, { error: '平台凭证无效' })

    expect(wrapper.text()).toContain('平台凭证无效')
  })
})
