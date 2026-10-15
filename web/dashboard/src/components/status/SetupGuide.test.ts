import { describe, expect, it } from 'vitest'
import SetupGuide from './SetupGuide.vue'
import { mountView } from '../../test/helpers'

describe('SetupGuide', () => {
  it('renders the title and the description', () => {
    const wrapper = mountView(SetupGuide, {
      props: { title: '还没有可用的 QQ 平台', description: '到「设置」页填写 qq_platforms。' },
    })

    expect(wrapper.text()).toContain('还没有可用的 QQ 平台')
    expect(wrapper.text()).toContain('到「设置」页填写 qq_platforms。')
  })
})
