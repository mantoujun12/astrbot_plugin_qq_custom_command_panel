/**
 * 文案对账：源码里的 t(key, fallback) 与 .astrbot-plugin/i18n/*.json 必须成对维护。
 *
 * 产物里只编译进 fallback 文案，改文案只要改 JSON 并重载插件，所以 key 写错、
 * fallback 与 JSON 不一对时不会有任何构建期报错，只能在这里拦。
 */

import { existsSync, readFileSync, readdirSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { SCENES, type SceneState } from '../types/dashboard'

type Dict = Record<string, unknown>

// vitest 的 root 是 web/dashboard（见 vitest.config.ts），locale 在仓库根的
// .astrbot-plugin/ 下，所以从 cwd 往上走两级
const DASHBOARD_DIR = process.cwd()
const REPO_ROOT = resolve(DASHBOARD_DIR, '..', '..')
const I18N_DIR = join(REPO_ROOT, '.astrbot-plugin', 'i18n')
const SRC_DIR = join(DASHBOARD_DIR, 'src')

/** 场景状态枚举，与 PlatformStatusCard 的 STATE_META 对齐 */
const SCENE_STATES: SceneState[] = ['synced', 'duplicate', 'missing', 'failed']
/** 平台类型枚举，与 SettingsView 的 PLATFORM_TYPES 对齐 */
const PLATFORM_TYPES = ['qq_official', 'qq_official_webhook']

/** 匹配 `t('some.key', 'fallback')`，允许 key/fallback 跨行 */
const STATIC_CALL = /\bt\(\s*'([^']+)'\s*,\s*'([^']*)'/g

function readLocale(locale: string): Dict {
  return JSON.parse(readFileSync(join(I18N_DIR, `${locale}.json`), 'utf8')) as Dict
}

function leafKeys(value: unknown, prefix = ''): string[] {
  if (value === null || typeof value !== 'object') {
    return [prefix]
  }
  return Object.entries(value as Dict).flatMap(([key, next]) =>
    leafKeys(next, prefix ? `${prefix}.${key}` : key),
  )
}

function lookup(dict: Dict, path: string): unknown {
  return path
    .split('.')
    .reduce<unknown>(
      (node, key) =>
        node !== null && typeof node === 'object' ? (node as Dict)[key] : undefined,
      dict,
    )
}

function sourceFiles(): string[] {
  return readdirSync(SRC_DIR, { recursive: true, withFileTypes: true })
    .filter(
      (entry) =>
        entry.isFile() &&
        /\.(ts|vue)$/.test(entry.name) &&
        !entry.name.endsWith('.test.ts'),
    )
    .map((entry) => join(entry.parentPath, entry.name))
}

function staticCalls(): { file: string; key: string; fallback: string }[] {
  const calls: { file: string; key: string; fallback: string }[] = []
  for (const file of sourceFiles()) {
    const source = readFileSync(file, 'utf8')
    for (const match of source.matchAll(STATIC_CALL)) {
      calls.push({ file, key: match[1], fallback: match[2] })
    }
  }
  return calls
}

const zhCN = readLocale('zh-CN')
const enUS = readLocale('en-US')
const calls = staticCalls()

describe('locale files', () => {
  it('is reading the real locale files', () => {
    expect(existsSync(join(I18N_DIR, 'zh-CN.json'))).toBe(true)
    expect(existsSync(join(I18N_DIR, 'en-US.json'))).toBe(true)
    expect(existsSync(join(SRC_DIR, 'App.vue'))).toBe(true)
  })

  it('keeps the same key set in every locale', () => {
    expect(leafKeys(enUS).sort()).toEqual(leafKeys(zhCN).sort())
  })
})

describe('t() calls in the view source', () => {
  it('finds the calls it is supposed to check', () => {
    // 正则失效时这个断言会先红，避免整套对账变成永远通过
    expect(calls.length).toBeGreaterThan(50)
  })

  it('has a locale entry for every statically referenced key', () => {
    const missing = calls
      .filter((call) => typeof lookup(zhCN, call.key) !== 'string')
      .map((call) => `${call.file}: ${call.key}`)
      .concat(
        calls
          .filter((call) => typeof lookup(enUS, call.key) !== 'string')
          .map((call) => `en-US ${call.file}: ${call.key}`),
      )

    expect(missing).toEqual([])
  })

  it('keeps every fallback in sync with the zh-CN copy', () => {
    const drifted = calls
      .filter((call) => lookup(zhCN, call.key) !== call.fallback)
      .map((call) => `${call.file}: ${call.key}`)

    expect(drifted).toEqual([])
  })

  it('has a locale entry for every key built from an enum', () => {
    const keys = [
      ...SCENES.map((scene) => `pages.dashboard.settings.scene.${scene}`),
      ...SCENE_STATES.map((state) => `pages.dashboard.status.state.${state}`),
      ...PLATFORM_TYPES.map(
        (type) => `pages.dashboard.settings.platformTypeName.${type}`,
      ),
    ]

    const missing = keys.filter(
      (key) =>
        typeof lookup(zhCN, key) !== 'string' ||
        typeof lookup(enUS, key) !== 'string',
    )

    expect(missing).toEqual([])
  })
})
