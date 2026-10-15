import { describe, expect, it } from 'vitest'
import { reactive, ref } from 'vue'
import { toPlain } from './serialize'

describe('toPlain', () => {
  it('returns primitives and empties unchanged', () => {
    expect(toPlain('zh-CN')).toBe('zh-CN')
    expect(toPlain(1)).toBe(1)
    expect(toPlain(null)).toBeNull()
    expect(toPlain(undefined)).toBeUndefined()
  })

  it('deep copies plain data', () => {
    const source = { language: 'zh-CN', scenes: ['c2c'], nested: { name: 'pf1' } }
    const plain = toPlain(source)

    expect(plain).toEqual(source)
    expect(plain).not.toBe(source)
    expect(plain.nested).not.toBe(source.nested)
  })

  it('turns a ref value into a structured-cloneable object', () => {
    const form = ref({ language: 'zh-CN', scenes: ['c2c'], nested: { name: 'pf1' } })
    const plain = toPlain(form.value)

    // Proxy 无法被结构化克隆，快照必须是普通对象
    expect(() => structuredClone(plain)).not.toThrow()
    expect(plain).toEqual({ language: 'zh-CN', scenes: ['c2c'], nested: { name: 'pf1' } })
    expect(plain).not.toBe(form.value)
  })

  it('turns a reactive object into a structured-cloneable object', () => {
    const form = reactive({ commands: [{ name: 'help', desc: '说明' }] })
    const plain = toPlain(form)

    expect(() => structuredClone(plain)).not.toThrow()
    expect(plain.commands[0]).toEqual({ name: 'help', desc: '说明' })
    expect(plain.commands).not.toBe(form.commands)
  })
})
