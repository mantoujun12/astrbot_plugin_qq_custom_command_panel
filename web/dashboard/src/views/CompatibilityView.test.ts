import { describe, expect, it, vi } from 'vitest'
import type { DOMWrapper, VueWrapper } from '@vue/test-utils'
import { VSelect } from 'vuetify/components'
import type { PluginConfigResponse } from '../types/dashboard'
import { flush, installBridge, mountView, waitUntil, deferred } from '../test/helpers'

vi.mock('../api/dashboard', () => ({
  fetchStatus: vi.fn(),
  fetchConfig: vi.fn(),
  saveConfig: vi.fn(),
}))

function configFixture(overrides: Partial<PluginConfigResponse> = {}): PluginConfigResponse {
  return {
    language: 'zh-CN',
    scenes: ['c2c', 'group'],
    available_scenes: ['c2c', 'group', 'channel', 'dm'],
    qq_platforms: [
      {
        name: '主机器人',
        appid: '1023456789',
        platform: 'qq_official',
        secret_masked: 'abc*****yz',
        secret_set: true,
      },
    ],
    selected_commands: [
      { name: 'help', desc: '查看帮助' },
      { name: 'ping', desc: '连通性测试' },
    ],
    limits: { name_max: 14, desc_max: 30, items_max: 20 },
    ...overrides,
  }
}

/** 按可见文案精确找按钮：Vuetify 的按钮结构不是稳定的断言目标 */
function button(wrapper: VueWrapper, label: string): DOMWrapper<Element> {
  const wanted = label.replace(/\s+/g, '')
  const found = wrapper
    .findAll('button')
    .find((node) => (node.text() ?? '').replace(/\s+/g, '') === wanted)
  if (!found) {
    throw new Error(`button not found: ${label}`)
  }
  return found
}

/** 指令行的输入框：指令名 maxlength=name_max、描述 maxlength=desc_max */
const NAME_INPUTS = 'input[maxlength="14"]'
const DESC_INPUTS = 'input[maxlength="30"]'

/**
 * 兼容性页同样依赖 useBridge / useSyncRun 的模块级单例，每个用例重置模块后再引。
 */
async function loadCompatibilityView(options: { withBackend?: boolean } = {}) {
  const bridge = options.withBackend === false ? null : installBridge()
  vi.resetModules()
  const api = await import('../api/dashboard')
  const { router } = await import('../router')
  const { default: CompatibilityView } = await import('./CompatibilityView.vue')

  return {
    bridge,
    api,
    router,
    async mount() {
      const wrapper = mountView(CompatibilityView, { global: { plugins: [router] } })
      await waitUntil(() => vi.mocked(api.fetchConfig).mock.calls.length > 0)
      await flush()
      return wrapper
    },
  }
}

describe('CompatibilityView', () => {
  it('loads the config into the form', async () => {
    const { api, mount } = await loadCompatibilityView()
    vi.mocked(api.fetchConfig).mockResolvedValue(configFixture())

    const wrapper = await mount()

    expect(api.fetchConfig).toHaveBeenCalledTimes(1)
    // 一行平台 + 两条指令
    expect(wrapper.findAll('.qc-config-item')).toHaveLength(1)
    expect(wrapper.findAll(NAME_INPUTS)).toHaveLength(2)
    expect(wrapper.findAll(DESC_INPUTS)).toHaveLength(2)
    expect(wrapper.text()).toContain('生效场景')
    expect(wrapper.text()).toContain('QQ 平台凭证')
    expect(wrapper.text()).toContain('指令条目')
    // 日志语言在「设置」页
    expect(wrapper.text()).not.toContain('日志语言')
    // secret 只回掩码：输入框留空，旁边的提示说明沿用原值
    const secret = wrapper.find('input[type="password"]')
    expect((secret.element as HTMLInputElement).value).toBe('')
    expect(secret.attributes('placeholder')).toBe('留空表示沿用原值')
    expect(wrapper.text()).toContain('当前：abc*****yz')
  })

  it('reports a failed load and keeps saving disabled', async () => {
    const { api, mount } = await loadCompatibilityView()
    vi.mocked(api.fetchConfig).mockRejectedValue(new Error('config failed'))

    const wrapper = await mount()

    expect(wrapper.text()).toContain('config failed')
    expect(wrapper.findAll('.qc-config-item')).toHaveLength(0)
    expect(button(wrapper, '保存').attributes('disabled')).toBeDefined()
  })

  it('labels mock data and refuses to fake a save in local dev', async () => {
    const { api, mount } = await loadCompatibilityView({ withBackend: false })
    vi.mocked(api.fetchConfig).mockResolvedValue(configFixture())

    const wrapper = await mount()

    expect(wrapper.text()).toContain('本地开发环境：展示的是 mock 数据，不能保存配置。')
    expect(button(wrapper, '保存').attributes('disabled')).toBeDefined()
    expect(wrapper.find(NAME_INPUTS).attributes('disabled')).toBeDefined()

    await button(wrapper, '保存').trigger('click')
    await flush()

    expect(api.saveConfig).not.toHaveBeenCalled()
    expect(wrapper.text()).not.toContain('配置已保存并生效。')
  })

  it('adds and removes platform rows', async () => {
    const { api, mount } = await loadCompatibilityView()
    vi.mocked(api.fetchConfig).mockResolvedValue(configFixture())

    const wrapper = await mount()

    await button(wrapper, '添加平台').trigger('click')
    expect(wrapper.findAll('.qc-config-item')).toHaveLength(2)

    await wrapper.findAll('.qc-config-item')[0]?.find('button').trigger('click')
    expect(wrapper.findAll('.qc-config-item')).toHaveLength(1)
  })

  it('adds and removes command rows and hides the add button at the limit', async () => {
    const { api, mount } = await loadCompatibilityView()
    vi.mocked(api.fetchConfig).mockResolvedValue(
      configFixture({ limits: { name_max: 14, desc_max: 30, items_max: 2 } }),
    )

    const wrapper = await mount()

    // 已经到上限：加不了，按钮直接禁用
    expect(button(wrapper, '添加指令').attributes('disabled')).toBeDefined()

    // 删除按钮：平台行在前、指令行在后，取最后一个才是指令行
    const deletes = wrapper
      .findAll('button')
      .filter((node) => node.attributes('aria-label') === '删除')
    expect(deletes).toHaveLength(3)
    await deletes.at(-1)?.trigger('click')
    expect(wrapper.findAll(NAME_INPUTS)).toHaveLength(1)

    await button(wrapper, '添加指令').trigger('click')
    expect(wrapper.findAll(NAME_INPUTS)).toHaveLength(2)
  })

  it('follows the appid when deciding what the secret field means', async () => {
    const { api, mount } = await loadCompatibilityView()
    vi.mocked(api.fetchConfig).mockResolvedValue(configFixture())

    const wrapper = await mount()
    const appidInput = wrapper.findAll('.qc-config-item input')[1]
    expect(appidInput).toBeDefined()

    await appidInput?.setValue('1038765432')
    expect(wrapper.find('input[type="password"]').attributes('placeholder')).toBe(
      '新增平台必须填写',
    )
    expect(wrapper.text()).not.toContain('当前：abc*****yz')

    await appidInput?.setValue('1023456789')
    expect(wrapper.find('input[type="password"]').attributes('placeholder')).toBe(
      '留空表示沿用原值',
    )
  })

  it('shows the local validation error instead of calling the backend', async () => {
    const { api, mount } = await loadCompatibilityView()
    vi.mocked(api.fetchConfig).mockResolvedValue(configFixture())

    const wrapper = await mount()

    await button(wrapper, '添加平台').trigger('click')
    await button(wrapper, '保存').trigger('click')
    await flush()

    expect(wrapper.text()).toContain('平台 appid 不能为空。')
    expect(api.saveConfig).not.toHaveBeenCalled()
  })

  it('saves the trimmed config and refills the form from the response', async () => {
    const { api, mount } = await loadCompatibilityView()
    vi.mocked(api.fetchConfig).mockResolvedValue(configFixture())
    vi.mocked(api.saveConfig).mockResolvedValue(
      configFixture({ selected_commands: [{ name: 'help', desc: '查看帮助' }] }),
    )

    const wrapper = await mount()
    await wrapper.findAll(NAME_INPUTS)[1]?.setValue('  ping  ')

    await button(wrapper, '保存').trigger('click')
    await waitUntil(() => vi.mocked(api.saveConfig).mock.calls.length > 0)
    await flush()

    expect(api.saveConfig).toHaveBeenCalledWith({
      scenes: ['c2c', 'group'],
      qq_platforms: [
        { name: '主机器人', appid: '1023456789', platform: 'qq_official', secret: '' },
      ],
      selected_commands: [
        { name: 'help', desc: '查看帮助' },
        { name: 'ping', desc: '连通性测试' },
      ],
    })
    // 回填用的是后端返回的配置：secret 依旧是掩码，输入框保持空白
    expect(wrapper.text()).toContain('配置已保存并生效。')
    expect(wrapper.findAll(NAME_INPUTS)).toHaveLength(1)
    expect((wrapper.find('input[type="password"]').element as HTMLInputElement).value).toBe('')
  })

  it('shows the backend error when saving is rejected', async () => {
    const { api, mount } = await loadCompatibilityView()
    vi.mocked(api.fetchConfig).mockResolvedValue(configFixture())
    vi.mocked(api.saveConfig).mockRejectedValue(new Error('language：fr-FR 不是支持的语言'))

    const wrapper = await mount()
    await button(wrapper, '保存').trigger('click')
    await waitUntil(() => vi.mocked(api.saveConfig).mock.calls.length > 0)
    await flush()

    expect(wrapper.text()).toContain('language：fr-FR 不是支持的语言')
    expect(wrapper.text()).not.toContain('配置已保存并生效。')
  })

  it('writes every field edit back into the submitted payload', async () => {
    const { api, mount } = await loadCompatibilityView()
    vi.mocked(api.fetchConfig).mockResolvedValue(configFixture())
    vi.mocked(api.saveConfig).mockResolvedValue(configFixture())

    const wrapper = await mount()
    // v-select 的下拉挂在 body 上，直接驱动 model 比点浮层稳
    const selects = wrapper.findAllComponents(VSelect)
    expect(selects).toHaveLength(2)
    selects[0]?.vm.$emit('update:modelValue', ['c2c'])
    selects[1]?.vm.$emit('update:modelValue', 'qq_official_webhook')

    const platformFields = wrapper.findAll('.qc-config-item input')
    await platformFields[0]?.setValue('  主号  ')
    await platformFields[2]?.setValue('  新secret  ')
    await wrapper.findAll(DESC_INPUTS)[0]?.setValue('  帮助  ')

    await button(wrapper, '保存').trigger('click')
    await waitUntil(() => vi.mocked(api.saveConfig).mock.calls.length > 0)

    expect(api.saveConfig).toHaveBeenCalledWith({
      scenes: ['c2c'],
      qq_platforms: [
        {
          name: '主号',
          appid: '1023456789',
          platform: 'qq_official_webhook',
          secret: '新secret',
        },
      ],
      selected_commands: [
        { name: 'help', desc: '帮助' },
        { name: 'ping', desc: '连通性测试' },
      ],
    })
  })

  it('triggers a sync and jumps to the status page when saving and syncing', async () => {
    const { api, bridge, mount, router } = await loadCompatibilityView()
    vi.mocked(api.fetchConfig).mockResolvedValue(configFixture())
    vi.mocked(api.saveConfig).mockResolvedValue(configFixture())

    const wrapper = await mount()
    await button(wrapper, '保存并同步').trigger('click')
    await waitUntil(() => router.currentRoute.value.name === 'status')

    expect(api.saveConfig).toHaveBeenCalledTimes(1)
    expect(bridge?.apiPost).toHaveBeenCalledWith('sync')
  })

  it('reloads the config on demand', async () => {
    const { api, mount } = await loadCompatibilityView()
    vi.mocked(api.fetchConfig).mockResolvedValue(configFixture())

    const wrapper = await mount()
    await button(wrapper, '重新载入').trigger('click')
    await waitUntil(() => vi.mocked(api.fetchConfig).mock.calls.length === 2)

    expect(api.fetchConfig).toHaveBeenCalledTimes(2)
  })

  it('ignores a stale reload that resolves after the save', async () => {
    const { api, mount } = await loadCompatibilityView()
    vi.mocked(api.fetchConfig).mockResolvedValue(configFixture())
    vi.mocked(api.saveConfig).mockResolvedValue(
      configFixture({ selected_commands: [{ name: 'saved', desc: '保存后的指令' }] }),
    )

    const wrapper = await mount()
    const stale = deferred<PluginConfigResponse>()
    vi.mocked(api.fetchConfig).mockReturnValueOnce(stale.promise)

    await button(wrapper, '重新载入').trigger('click')
    await waitUntil(() => vi.mocked(api.fetchConfig).mock.calls.length === 2)

    await button(wrapper, '保存').trigger('click')
    await waitUntil(() => vi.mocked(api.saveConfig).mock.calls.length > 0)
    await flush()
    expect(wrapper.findAll(NAME_INPUTS)).toHaveLength(1)

    // 先发出的 GET 在保存之后才返回，不能把表单覆盖回保存前的两条指令
    stale.resolve(configFixture())
    await flush()

    expect(wrapper.findAll(NAME_INPUTS)).toHaveLength(1)
    expect((wrapper.findAll(DESC_INPUTS)[0]?.element as HTMLInputElement).value).toBe(
      '保存后的指令',
    )
    expect(wrapper.text()).toContain('配置已保存并生效。')
  })

  it('disables reload while a save is in flight', async () => {
    const { api, mount } = await loadCompatibilityView()
    vi.mocked(api.fetchConfig).mockResolvedValue(configFixture())
    const pendingSave = deferred<PluginConfigResponse>()
    vi.mocked(api.saveConfig).mockReturnValueOnce(pendingSave.promise)

    const wrapper = await mount()
    await button(wrapper, '保存').trigger('click')
    await waitUntil(() => vi.mocked(api.saveConfig).mock.calls.length > 0)

    expect(button(wrapper, '重新载入').attributes('disabled')).toBeDefined()

    pendingSave.resolve(configFixture())
    await flush()

    expect(button(wrapper, '重新载入').attributes('disabled')).toBeUndefined()
  })
})
