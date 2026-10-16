import { afterEach, describe, expect, it, vi } from 'vitest'
import type { DOMWrapper, VueWrapper } from '@vue/test-utils'
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
    expect(wrapper.text()).toContain('新版配置')
    expect(wrapper.text()).toContain('主机器人')
    expect(wrapper.text()).toContain('测试机器人')
    expect(wrapper.text()).toContain('场景 2 个，指令 2 条。')
    expect((field(wrapper, 'appid').element as HTMLInputElement).value).toBe('1023456789')
    expect((field(wrapper, 'secret').element as HTMLInputElement).value).toBe('')
    expect(wrapper.text()).toContain('当前：abc*****yz')
    expect(wrapper.findAll('[data-scene="c2c"] [data-field="command-name"]')).toHaveLength(1)
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

  it('adds a new robot and edits its scene commands independently', async () => {
    const { api, mount } = await loadView()
    vi.mocked(api.fetchRobots).mockResolvedValue(robotResponse())

    const wrapper = await mount()
    await button(wrapper, '新增机器人').trigger('click')
    await flush()

    expect(wrapper.findAll('.qc-robot-item')).toHaveLength(3)
    expect(wrapper.text()).toContain('未命名机器人')
    expect(wrapper.text()).toContain('0/20 条')

    await field(wrapper, 'name').setValue('新机器人')
    await field(wrapper, 'appid').setValue('1040000000')
    await field(wrapper, 'secret').setValue('new-secret')
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

  it('allows saving after removing every robot', async () => {
    const { api, mount } = await loadView()
    vi.mocked(api.fetchRobots).mockResolvedValue(robotResponse())
    const saved = robotResponse()
    saved.robots = []
    vi.mocked(api.saveRobots).mockResolvedValue(saved)

    const wrapper = await mount()
    await button(wrapper, '删除机器人配置').trigger('click')
    await button(wrapper, '删除机器人配置').trigger('click')
    await flush()

    expect(button(wrapper, '保存').attributes('disabled')).toBeUndefined()
    await button(wrapper, '保存').trigger('click')
    await waitUntil(() => vi.mocked(api.saveRobots).mock.calls.length > 0)

    expect(vi.mocked(api.saveRobots).mock.calls[0]?.[0].robots).toEqual([])
    expect(wrapper.text()).toContain('机器人配置已保存。')
  })

  it('labels mock data and disables saving, adding, and importing', async () => {
    const { api, mount } = await loadView({ withBackend: false })
    vi.mocked(api.fetchRobots).mockResolvedValue(MOCK_ROBOTS)

    const wrapper = await mount()

    expect(wrapper.text()).toContain('本地开发环境：展示的是 mock 数据，不能保存配置。')
    expect(wrapper.text()).toContain('主机器人')
    expect(button(wrapper, '保存').attributes('disabled')).toBeDefined()
    expect(button(wrapper, '保存并同步').attributes('disabled')).toBeDefined()
    expect(button(wrapper, '新增机器人').attributes('disabled')).toBeDefined()
    expect(button(wrapper, '从兼容配置导入').attributes('disabled')).toBeDefined()

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
    await waitUntil(() => vi.mocked(legacyApi.fetchConfig).mock.calls.length > 0)
    await flush()

    const textarea = wrapper.find('[data-field="legacy-appids"] textarea')
    expect((textarea.element as HTMLTextAreaElement).value).toContain('1023456789')

    await button(wrapper, '导入').trigger('click')
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
    await flush()
    expect(wrapper.find('.qc-import-panel').exists()).toBe(true)

    await button(wrapper, '取消').trigger('click')
    await flush()
    expect(wrapper.find('.qc-import-panel').exists()).toBe(false)
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
