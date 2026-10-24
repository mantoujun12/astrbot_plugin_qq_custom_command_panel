import { afterEach, describe, expect, it, vi } from 'vitest'
import type { DOMWrapper, VueWrapper } from '@vue/test-utils'
import { VDialog, VSelect } from 'vuetify/components'
import type { PluginViewBridge } from '../bridge'
import type { PluginConfigResponse } from '../types/dashboard'
import type { RobotConfigResponse } from '../types/robotConfig'
import { MOCK_ROBOTS } from '../api/robots'
import { flush, installBridge, mountView, waitUntil } from '../test/helpers'

vi.mock('../api/dashboard', () => ({
  fetchConfig: vi.fn(),
  fetchStatus: vi.fn(),
  saveConfig: vi.fn(),
}))

vi.mock('../api/robots', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/robots')>()
  return {
    ...actual,
    fetchRobots: vi.fn(),
    saveRobots: vi.fn(),
  }
})

function robotResponse(): RobotConfigResponse {
  return {
    version: 1,
    available_scenes: ['c2c', 'group', 'channel', 'dm'],
    limits: { name_max: 14, desc_max: 30, items_max: 20 },
    robots: [
      {
        id: 'robot-1',
        name: '主机器人',
        appid: '1023456789',
        platform: 'qq_official',
        secret_masked: 'abc*****yz',
        secret_set: true,
        scenes: {
          c2c: { enabled: true, items: [{ name: 'help', desc: '查看帮助' }] },
          group: { enabled: true, items: [{ name: 'status', desc: '状态' }] },
          channel: { enabled: false, items: [] },
          dm: { enabled: false, items: [] },
        },
      },
      {
        id: 'robot-2',
        name: '测试机器人',
        appid: '1038765432',
        platform: 'qq_official_webhook',
        secret_masked: 'def*****wv',
        secret_set: true,
        scenes: {
          c2c: { enabled: false, items: [] },
          group: { enabled: true, items: [{ name: 'debug', desc: '调试' }] },
          channel: { enabled: false, items: [] },
          dm: { enabled: false, items: [] },
        },
      },
    ],
  }
}

function legacyConfig(): PluginConfigResponse {
  return {
    language: 'zh-CN',
    scenes: ['c2c'],
    available_scenes: ['c2c', 'group', 'channel', 'dm'],
    qq_platforms: [
      {
        name: '旧机器人',
        appid: '1023456789',
        platform: 'qq_official',
        secret_masked: 'abc*****yz',
        secret_set: true,
      },
    ],
    selected_commands: [{ name: 'help', desc: '查看帮助' }],
    limits: { name_max: 14, desc_max: 30, items_max: 20 },
  }
}

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

/**
 * 弹窗内容由 v-dialog 挂在 body 上，wrapper 够不到，只能按文档查。
 * 打开弹窗后先 waitUntil 等到它出现，再操作里面的控件。
 */
function dialogEl(selector: string): HTMLElement | null {
  return document.body.querySelector<HTMLElement>(selector)
}

/** 弹窗里的按钮：按可见文案精确匹配，语义与 wrapper 版一致 */
function dialogButton(label: string): Element {
  const wanted = label.replace(/\s+/g, '')
  const found = [...document.body.querySelectorAll('button')].find(
    (node) => (node.textContent ?? '').replace(/\s+/g, '') === wanted,
  )
  if (!found) {
    throw new Error(`dialog button not found: ${label}`)
  }
  return found
}

function clickInDialog(label: string): void {
  ;(dialogButton(label) as HTMLElement).click()
}

/** 多个弹窗的关闭节点会同时留在 body 里，按弹窗容器限定操作范围 */
function clickInDialogPanel(selector: string, label: string): void {
  const panel = document.body.querySelector(selector)
  if (!panel) {
    throw new Error(`dialog panel not found: ${selector}`)
  }
  const wanted = label.replace(/\s+/g, '')
  const found = [...panel.querySelectorAll('button')].find(
    (node) => (node.textContent ?? '').replace(/\s+/g, '') === wanted,
  )
  if (!found) {
    throw new Error(`dialog button not found in ${selector}: ${label}`)
  }
  ;(found as HTMLElement).click()
}

/** 给弹窗里的输入框赋值并派发 input，等价于 wrapper 上的 setValue */
async function typeInDialog(selector: string, value: string): Promise<void> {
  const el = document.body.querySelector<HTMLInputElement>(selector)
  if (!el) {
    throw new Error(`dialog input not found: ${selector}`)
  }
  el.value = value
  el.dispatchEvent(new Event('input'))
  await flush()
}

/** 模板里「从兼容配置导入」在前、「新增机器人」在后 */
const IMPORT_DIALOG = 0
const CREATE_DIALOG = 1
const DELETE_DIALOG = 2

/**
 * 弹窗是否打开看 v-model，而不是等 DOM 消失。
 * Vuetify 浮层关闭要走 leave transition，内容只在 onAfterLeave 里回收，而测试环境把
 * transition stub 掉了、钩子不触发，节点会一直留着——那是实现细节，不是「没关」。
 */
function dialogModel(wrapper: VueWrapper, index: number): boolean {
  return wrapper.findAllComponents(VDialog)[index]?.props('modelValue') as boolean
}

function field(wrapper: VueWrapper, name: string): DOMWrapper<Element> {
  const found = wrapper.find(`[data-field="${name}"] input`)
  if (!found.exists()) {
    throw new Error(`field not found: ${name}`)
  }
  return found
}

function scene(wrapper: VueWrapper, name: string): DOMWrapper<Element> {
  const found = wrapper.find(`[data-scene="${name}"]`)
  if (!found.exists()) {
    throw new Error(`scene not found: ${name}`)
  }
  return found
}

async function loadView(
  options: { withBackend?: boolean; bridge?: Partial<PluginViewBridge> } = {},
) {
  const bridge = options.withBackend === false ? null : installBridge(options.bridge)
  vi.resetModules()
  const api = await import('../api/robots')
  const legacyApi = await import('../api/dashboard')
  const { router } = await import('../router')
  const { default: RobotsView } = await import('./RobotsView.vue')

  return {
    bridge,
    api,
    legacyApi,
    router,
    async mount() {
      const wrapper = mountView(RobotsView, { global: { plugins: [router] } })
      await waitUntil(() => vi.mocked(api.fetchRobots).mock.calls.length > 0)
      await flush()
      return wrapper
    },
  }
}

afterEach(() => {
  delete window.AstrBotPluginView
  delete window.AstrBotPluginPage
  vi.clearAllMocks()
})

describe('RobotsView', () => {
  it('loads the robot list and first editor', async () => {
    const { api, mount } = await loadView()
    vi.mocked(api.fetchRobots).mockResolvedValue(robotResponse())

    const wrapper = await mount()

    expect(api.fetchRobots).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('机器人')
    expect(wrapper.text()).toContain('主机器人')
    expect(wrapper.text()).toContain('测试机器人')
    expect(wrapper.text()).toContain('场景 2 个，指令 2 条。')
    expect((field(wrapper, 'appid').element as HTMLInputElement).value).toBe('1023456789')
    expect((field(wrapper, 'secret').element as HTMLInputElement).value).toBe('')
    expect(wrapper.text()).toContain('当前：abc*****yz')
    expect(wrapper.findAll('[data-scene="c2c"] [data-field="command-name"]')).toHaveLength(1)
  })

  it('combines robot selection and configuration in one responsive shell', async () => {
    const { api, mount } = await loadView()
    vi.mocked(api.fetchRobots).mockResolvedValue(robotResponse())

    const wrapper = await mount()
    const shell = wrapper.find('.qc-robots-shell')

    expect(wrapper.find('.qc-robots-page').exists()).toBe(true)
    expect(shell.exists()).toBe(true)
    expect(shell.find('[data-pane="list"]').exists()).toBe(true)
    expect(shell.find('[data-pane="editor"]').exists()).toBe(true)
    expect(shell.findAll('.qc-robots-divider--desktop')).toHaveLength(1)
    expect(shell.findAll('.qc-robots-divider--mobile')).toHaveLength(1)
    expect(shell.find('.qc-robot-card-list').exists()).toBe(true)
    expect(shell.find('.qc-robot-select').exists()).toBe(true)
  })

  it('switches between robots and keeps each robot scenes isolated', async () => {
    const { api, mount } = await loadView()
    vi.mocked(api.fetchRobots).mockResolvedValue(robotResponse())

    const wrapper = await mount()
    await wrapper.findAll('.qc-robot-item')[1]?.trigger('click')
    await flush()

    expect((field(wrapper, 'appid').element as HTMLInputElement).value).toBe('1038765432')
    expect(scene(wrapper, 'group').text()).toContain('1/20 条')
    expect(scene(wrapper, 'c2c').text()).toContain('0/20 条')
    expect(wrapper.findAll('[data-scene="group"] [data-field="command-name"]')).toHaveLength(1)

    await wrapper.findAll('.qc-robot-item')[0]?.trigger('click')
    await flush()

    expect((field(wrapper, 'appid').element as HTMLInputElement).value).toBe('1023456789')
    expect(scene(wrapper, 'c2c').text()).toContain('1/20 条')
  })

  it('switches robots from the compact select', async () => {
    const { api, mount } = await loadView()
    vi.mocked(api.fetchRobots).mockResolvedValue(robotResponse())

    const wrapper = await mount()
    const select = wrapper.find('.qc-robot-select').findComponent(VSelect)

    expect(select.props('modelValue')).toBe('robot:robot-1')
    select.vm.$emit('update:modelValue', 'robot:robot-2')
    await flush()

    expect((field(wrapper, 'appid').element as HTMLInputElement).value).toBe('1038765432')

    select.vm.$emit('update:modelValue', null)
    await flush()

    expect((field(wrapper, 'appid').element as HTMLInputElement).value).toBe('1038765432')
  })

  it('adds a new robot and edits its scene commands independently', async () => {
    const { api, mount } = await loadView()
    vi.mocked(api.fetchRobots).mockResolvedValue(robotResponse())

    const wrapper = await mount()
    // 新增机器人走弹窗：先填基础信息，再点创建
    await button(wrapper, '新增机器人').trigger('click')
    await waitUntil(() => dialogEl('.qc-robot-create') !== null)
    await typeInDialog('[data-field="create-name"] input', '新机器人')
    await typeInDialog('[data-field="create-appid"] input', '1040000000')
    await typeInDialog('[data-field="create-secret"] input', 'new-secret')
    clickInDialog('创建')
    await flush()

    expect(wrapper.findAll('.qc-robot-item')).toHaveLength(3)
    expect(wrapper.text()).toContain('新机器人')
    expect(wrapper.text()).toContain('0/20 条')

    await scene(wrapper, 'c2c').find('input[type="checkbox"]').setValue(true)
    await scene(wrapper, 'c2c').find('[data-action="add-command"]').trigger('click')
    await flush()
    await scene(wrapper, 'c2c')
      .find('[data-field="command-name"] input')
      .setValue('new-help')
    await scene(wrapper, 'c2c')
      .find('[data-field="command-desc"] input')
      .setValue('新帮助')

    await wrapper.findAll('.qc-robot-item')[0]?.trigger('click')
    await flush()
    expect(scene(wrapper, 'c2c').text()).toContain('1/20 条')
    expect(scene(wrapper, 'c2c').text()).not.toContain('new-help')

    await wrapper.findAll('.qc-robot-item')[2]?.trigger('click')
    await flush()
    expect(scene(wrapper, 'c2c').text()).toContain('1/20 条')
    expect(
      (scene(wrapper, 'c2c').find('[data-field="command-name"] input')
        .element as HTMLInputElement).value,
    ).toBe('new-help')
  })

  it('shows a scene validation error when enabling an empty scene', async () => {
    const { api, mount } = await loadView()
    vi.mocked(api.fetchRobots).mockResolvedValue(robotResponse())

    const wrapper = await mount()
    await scene(wrapper, 'channel').find('input[type="checkbox"]').setValue(true)
    await button(wrapper, '保存').trigger('click')
    await flush()

    expect(wrapper.text()).toContain('启用的场景至少需要 1 条指令。')
    expect(api.saveRobots).not.toHaveBeenCalled()
  })

  it('saves the normalized payload and refreshes from the response', async () => {
    const { api, mount } = await loadView()
    const loaded = robotResponse()
    vi.mocked(api.fetchRobots).mockResolvedValue(loaded)

    const saved = robotResponse()
    saved.robots[0].name = '主机器人'
    saved.robots[0].scenes.c2c.items[0] = { name: 'help', desc: '帮助' }
    vi.mocked(api.saveRobots).mockResolvedValue(saved)

    const wrapper = await mount()
    await field(wrapper, 'name').setValue('  主机器人  ')
    await scene(wrapper, 'c2c')
      .find('[data-field="command-desc"] input')
      .setValue('  帮助  ')

    await button(wrapper, '保存').trigger('click')
    await waitUntil(() => vi.mocked(api.saveRobots).mock.calls.length > 0)
    await flush()

    expect(api.saveRobots).toHaveBeenCalledWith({
      version: 1,
      robots: [
        {
          id: 'robot-1',
          name: '主机器人',
          appid: '1023456789',
          platform: 'qq_official',
          secret: '',
          scenes: {
            c2c: { enabled: true, items: [{ name: 'help', desc: '帮助' }] },
            group: { enabled: true, items: [{ name: 'status', desc: '状态' }] },
            channel: { enabled: false, items: [] },
            dm: { enabled: false, items: [] },
          },
        },
        {
          id: 'robot-2',
          name: '测试机器人',
          appid: '1038765432',
          platform: 'qq_official_webhook',
          secret: '',
          scenes: {
            c2c: { enabled: false, items: [] },
            group: { enabled: true, items: [{ name: 'debug', desc: '调试' }] },
            channel: { enabled: false, items: [] },
            dm: { enabled: false, items: [] },
          },
        },
      ],
    })
    expect(wrapper.text()).toContain('机器人配置已保存。')
    expect((field(wrapper, 'secret').element as HTMLInputElement).value).toBe('')
  })

  it('keeps an existing secret empty and posts it empty', async () => {
    const { api, mount } = await loadView()
    vi.mocked(api.fetchRobots).mockResolvedValue(robotResponse())
    vi.mocked(api.saveRobots).mockResolvedValue(robotResponse())

    const wrapper = await mount()
    await button(wrapper, '保存').trigger('click')
    await waitUntil(() => vi.mocked(api.saveRobots).mock.calls.length > 0)

    const [payload] = vi.mocked(api.saveRobots).mock.calls[0]
    expect(payload.robots[0]?.secret).toBe('')
    expect((field(wrapper, 'secret').element as HTMLInputElement).value).toBe('')
  })

  it('warns and requires a new secret when an existing AppID changes', async () => {
    const { api, mount } = await loadView()
    vi.mocked(api.fetchRobots).mockResolvedValue(robotResponse())
    vi.mocked(api.saveRobots).mockResolvedValue(robotResponse())

    const wrapper = await mount()
    await field(wrapper, 'appid').setValue('1099999999')
    await flush()

    expect(wrapper.text()).toContain('修改 AppID 会改变新版配置对兼容性机器人的接管关系')
    expect(wrapper.text()).toContain('修改 AppID 后必须重新填写 ClientSecret。')

    await button(wrapper, '保存').trigger('click')
    await flush()

    expect(api.saveRobots).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('修改 AppID 后必须重新填写 ClientSecret。')

    await field(wrapper, 'secret').setValue('new-secret')
    await button(wrapper, '保存').trigger('click')
    await waitUntil(() => vi.mocked(api.saveRobots).mock.calls.length > 0)

    const [payload] = vi.mocked(api.saveRobots).mock.calls[0]
    expect(payload.robots[0]).toMatchObject({
      id: 'robot-1',
      appid: '1099999999',
      secret: 'new-secret',
    })
  })

  it('allows saving after removing every robot', async () => {
    const { api, mount } = await loadView()
    vi.mocked(api.fetchRobots).mockResolvedValue(robotResponse())
    const saved = robotResponse()
    saved.robots = []
    vi.mocked(api.saveRobots).mockResolvedValue(saved)

    const wrapper = await mount()
    await button(wrapper, '删除机器人配置').trigger('click')
    await waitUntil(() => dialogEl('.qc-robot-delete') !== null)
    clickInDialog('确认删除')
    await flush()
    await button(wrapper, '删除机器人配置').trigger('click')
    await waitUntil(() => dialogEl('.qc-robot-delete') !== null)
    clickInDialog('确认删除')
    await flush()

    expect(button(wrapper, '保存').attributes('disabled')).toBeUndefined()
    await button(wrapper, '保存').trigger('click')
    await waitUntil(() => vi.mocked(api.saveRobots).mock.calls.length > 0)

    expect(vi.mocked(api.saveRobots).mock.calls[0]?.[0].robots).toEqual([])
    expect(wrapper.text()).toContain('机器人配置已保存。')
  })

  it('asks for confirmation before deleting a robot', async () => {
    const { api, mount } = await loadView()
    vi.mocked(api.fetchRobots).mockResolvedValue(robotResponse())

    const wrapper = await mount()
    await button(wrapper, '删除机器人配置').trigger('click')
    await waitUntil(() => dialogEl('.qc-robot-delete') !== null)

    expect(dialogEl('.qc-robot-delete')?.textContent).toContain('主机器人')
    expect(dialogEl('.qc-robot-delete')?.textContent).toContain('1023456789')
    expect(wrapper.findAll('.qc-robot-item')).toHaveLength(2)

    clickInDialog('取消')
    await flush()

    expect(dialogModel(wrapper, DELETE_DIALOG)).toBe(false)
    expect(wrapper.findAll('.qc-robot-item')).toHaveLength(2)

    await button(wrapper, '删除机器人配置').trigger('click')
    clickInDialog('确认删除')
    await flush()

    expect(dialogModel(wrapper, DELETE_DIALOG)).toBe(false)
    expect(wrapper.findAll('.qc-robot-item')).toHaveLength(1)
    expect(wrapper.text()).toContain('已从本地列表移除。保存后才会写入配置。')
  })

  it('keeps saving disabled in mock but still lets local dialogs open', async () => {
    const { api, legacyApi, mount } = await loadView({ withBackend: false })
    vi.mocked(api.fetchRobots).mockResolvedValue(MOCK_ROBOTS)
    vi.mocked(legacyApi.fetchConfig).mockResolvedValue(legacyConfig())

    const wrapper = await mount()

    expect(wrapper.text()).toContain('本地开发环境：展示的是 mock 数据，不能保存配置。')
    expect(wrapper.text()).toContain('主机器人')
    // 落库动作在 mock 下必须禁用
    expect(button(wrapper, '保存').attributes('disabled')).toBeDefined()
    expect(button(wrapper, '保存并同步').attributes('disabled')).toBeDefined()

    // 但本地交互弹窗要能打开，方便在开发环境里点着看
    expect(button(wrapper, '新增机器人').attributes('disabled')).toBeUndefined()
    expect(button(wrapper, '从兼容配置导入').attributes('disabled')).toBeUndefined()
    expect(button(wrapper, '删除机器人配置').attributes('disabled')).toBeUndefined()

    await button(wrapper, '新增机器人').trigger('click')
    await waitUntil(() => dialogEl('.qc-robot-create') !== null)
    clickInDialog('取消')
    await flush()
    expect(dialogModel(wrapper, CREATE_DIALOG)).toBe(false)

    await button(wrapper, '删除机器人配置').trigger('click')
    await waitUntil(() => dialogEl('.qc-robot-delete') !== null)
    expect(dialogEl('.qc-robot-delete')?.textContent).toContain('主机器人')
    expect(dialogEl('.qc-robot-delete')?.textContent).toContain('1023456789')
    expect(dialogButton('确认删除')).toBeDefined()
    clickInDialogPanel('.qc-robot-delete', '取消')
    await flush()
    expect(dialogModel(wrapper, DELETE_DIALOG)).toBe(false)

    // 确认删除只改本地预览，提示语不能承诺一次在 mock 下不可能发生的保存
    await button(wrapper, '删除机器人配置').trigger('click')
    await waitUntil(() => dialogEl('.qc-robot-delete') !== null)
    clickInDialogPanel('.qc-robot-delete', '确认删除')
    await flush()
    expect(dialogModel(wrapper, DELETE_DIALOG)).toBe(false)
    expect(wrapper.findAll('.qc-robot-item')).toHaveLength(1)
    expect(wrapper.text()).toContain('已从本地列表移除（预览），不会写入配置。')
    expect(wrapper.text()).not.toContain('保存后才会写入配置。')

    await button(wrapper, '从兼容配置导入').trigger('click')
    await waitUntil(() => dialogEl('.qc-import-panel') !== null)
    // 导入本身要写后端，mock 下仍然禁用
    expect(dialogButton('导入').hasAttribute('disabled')).toBe(true)

    await button(wrapper, '保存').trigger('click')
    await flush()
    expect(api.saveRobots).not.toHaveBeenCalled()
    expect(wrapper.text()).not.toContain('机器人配置已保存。')
  })

  it('imports legacy appids, reloads robots, and shows the import result', async () => {
    const { api, legacyApi, mount } = await loadView()
    vi.mocked(api.fetchRobots).mockResolvedValue(robotResponse())
    vi.mocked(legacyApi.fetchConfig).mockResolvedValue(legacyConfig())
    vi.mocked(api.saveRobots).mockResolvedValue(robotResponse())

    const wrapper = await mount()
    vi.mocked(api.fetchRobots).mockResolvedValue(robotResponse())

    await button(wrapper, '从兼容配置导入').trigger('click')
    await waitUntil(() => dialogEl('.qc-import-panel') !== null)
    await waitUntil(() => vi.mocked(legacyApi.fetchConfig).mock.calls.length > 0)
    await flush()

    const textarea = dialogEl('[data-field="legacy-appids"] textarea') as HTMLTextAreaElement
    expect(textarea.value).toContain('1023456789')

    clickInDialog('导入')
    await waitUntil(() => vi.mocked(api.fetchRobots).mock.calls.length === 2)
    await flush()

    expect(wrapper.text()).toContain('已从兼容配置导入并保存机器人配置，请检查后再同步。')
    expect(window.AstrBotPluginView?.apiPost).toHaveBeenCalledWith('robots/import-legacy', {
      appids: ['1023456789'],
      version: 1,
    })
  })

  it('saves before starting sync and jumps to the status page', async () => {
    const { api, mount, router } = await loadView()
    vi.mocked(api.fetchRobots).mockResolvedValue(robotResponse())
    vi.mocked(api.saveRobots).mockResolvedValue(robotResponse())

    const wrapper = await mount()
    await button(wrapper, '保存并同步').trigger('click')
    await waitUntil(() => router.currentRoute.value.name === 'status')

    expect(api.saveRobots).toHaveBeenCalledTimes(1)
    expect(window.AstrBotPluginView?.apiPost).toHaveBeenCalledWith('sync')
  })

  it('reports a failed load and clears the editor', async () => {
    const { api, mount } = await loadView()
    vi.mocked(api.fetchRobots).mockRejectedValue(new Error('robot list failed'))

    const wrapper = await mount()

    expect(wrapper.text()).toContain('robot list failed')
    expect(wrapper.text()).toContain('还没有机器人，先新增一台。')
    expect(button(wrapper, '保存').attributes('disabled')).toBeDefined()
  })

  it('toggles a scene and adds or removes its own command rows', async () => {
    const { api, mount } = await loadView()
    vi.mocked(api.fetchRobots).mockResolvedValue(robotResponse())
    vi.mocked(api.saveRobots).mockResolvedValue(robotResponse())

    const wrapper = await mount()
    const channel = scene(wrapper, 'channel')

    await channel.find('input[type="checkbox"]').setValue(true)
    await flush()
    expect(channel.text()).toContain('这个场景还没有指令条目。')

    await channel.find('[data-action="add-command"]').trigger('click')
    await flush()
    expect(channel.findAll('[data-field="command-name"]')).toHaveLength(1)

    // 新增空指令后保存会被本地校验拦下
    await button(wrapper, '保存').trigger('click')
    await flush()
    expect(api.saveRobots).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('指令名不能为空。')

    await channel.find('[data-action="remove-command"]').trigger('click')
    await flush()
    expect(channel.findAll('[data-field="command-name"]')).toHaveLength(0)
  })

  it('closes the import panel without importing anything', async () => {
    const { api, mount } = await loadView()
    vi.mocked(api.fetchRobots).mockResolvedValue(robotResponse())

    const wrapper = await mount()
    await button(wrapper, '从兼容配置导入').trigger('click')
    await waitUntil(() => dialogEl('.qc-import-panel') !== null)

    clickInDialog('取消')
    await flush()
    expect(dialogModel(wrapper, IMPORT_DIALOG)).toBe(false)
    expect(window.AstrBotPluginView?.apiPost).not.toHaveBeenCalled()
  })

  it('shows the backend error when saving is rejected', async () => {
    const { api, mount } = await loadView()
    vi.mocked(api.fetchRobots).mockResolvedValue(robotResponse())
    vi.mocked(api.saveRobots).mockRejectedValue(new Error('duplicate appid'))

    const wrapper = await mount()
    await button(wrapper, '保存').trigger('click')
    await waitUntil(() => vi.mocked(api.saveRobots).mock.calls.length > 0)
    await flush()

    expect(wrapper.text()).toContain('duplicate appid')
    expect(wrapper.text()).not.toContain('机器人配置已保存。')
  })
})
