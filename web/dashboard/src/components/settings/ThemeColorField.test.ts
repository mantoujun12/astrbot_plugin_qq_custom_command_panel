import { describe, expect, it } from 'vitest'
import { VColorPicker } from 'vuetify/components'
import ThemeColorField from './ThemeColorField.vue'
import { flush, mountView } from '../../test/helpers'

function mountField(overrides: Record<string, unknown> = {}) {
  return mountView(ThemeColorField, {
    props: {
      modelValue: '#3c96ca',
      label: '主色',
      hint: '使用 #RRGGBB 格式。',
      invalidMessage: '请输入 #RRGGBB 格式的颜色。',
      ...overrides,
    },
  })
}

describe('ThemeColorField', () => {
  it('keeps manual HEX input working', async () => {
    const wrapper = mountField()

    await wrapper.get('input[type="text"]').setValue('#AABBCC')

    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual(['#AABBCC'])
    expect(wrapper.get('.qc-color-trigger').attributes('aria-label')).toBe('主色')
  })

  it('opens a Vuetify color picker and normalizes its value', async () => {
    const wrapper = mountField()

    await wrapper.get('.qc-color-trigger').trigger('click')
    await flush()

    const picker = wrapper.findComponent(VColorPicker)
    expect(picker.exists()).toBe(true)
    expect(picker.props('modelValue')).toBe('#3c96ca')

    picker.vm.$emit('update:modelValue', '#AABBCC')
    await flush()

    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual(['#aabbcc'])
  })

  it('ignores non-HEX values from the picker', async () => {
    const wrapper = mountField()
    await wrapper.get('.qc-color-trigger').trigger('click')
    await flush()

    const picker = wrapper.findComponent(VColorPicker)
    picker.vm.$emit('update:modelValue', 'not-a-color')
    await flush()

    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
  })

  it('disables the trigger when the field is disabled', () => {
    const wrapper = mountField({ disabled: true })

    expect(wrapper.get('.qc-color-trigger').attributes('disabled')).toBeDefined()
    expect(wrapper.get('input[type="text"]').attributes('disabled')).toBeDefined()
  })
})
