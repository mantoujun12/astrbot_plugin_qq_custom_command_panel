<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import {
  mdiAccountGroupOutline,
  mdiAccountOutline,
  mdiAlertCircleOutline,
  mdiContentSave,
  mdiImport,
  mdiMessageTextOutline,
  mdiPlus,
  mdiRobotOutline,
  mdiSync,
  mdiTrashCanOutline,
} from '@mdi/js'
import { fetchConfig } from '../api/dashboard'
import {
  emptyRobotDraft,
  fetchRobots,
  isRobotMock,
  robotAppidChanged,
  robotItemCount,
  robotSceneCount,
  saveRobots,
  toRobotForm,
  validateRobotForm,
} from '../api/robots'
import { useBridge } from '../composables/useBridge'
import { useSyncRun } from '../composables/useSyncRun'
import { SCENES, type ConfigLimits, type Scene } from '../types/dashboard'
import type {
  RobotConfig,
  RobotConfigForm,
  RobotConfigPayload,
  RobotConfigResponse,
} from '../types/robotConfig'

interface RobotDraft {
  key: string
  form: RobotConfigForm
  /** 后端已保存的 AppID，用于判断 AppID 是否被改动；新增机器人为空 */
  savedAppid: string
  secretMasked: string
  secretSet: boolean
}

const FALLBACK_LIMITS: ConfigLimits = { name_max: 14, desc_max: 30, items_max: 20 }
const PLATFORM_TYPES = ['qq_official', 'qq_official_webhook'] as const

const { t, ready, hasBackend, bridge } = useBridge()
const router = useRouter()
const { start: startSync } = useSyncRun()

const response = ref<RobotConfigResponse | null>(null)
const drafts = ref<RobotDraft[]>([])
const selectedKey = ref('')
const robotErrors = ref<Record<string, string>>({})
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const notice = ref('')
const importPanel = ref(false)
const importLoading = ref(false)
const importing = ref(false)
const importError = ref('')
const legacyAppidsText = ref('')
const createDialog = ref(false)
const createForm = ref<RobotConfigForm>(emptyRobotDraft())
const createError = ref('')
const deleteDialog = ref(false)
const unsavedDialog = ref(false)
const unsavedError = ref('')
const pendingAction = ref<'import' | 'reload' | null>(null)

let draftSeq = 0

// 请求代次：load 与 save 都会写同一份机器人草稿，只允许最新一次请求写回状态，
// 否则先发出的 GET 后返回时会覆盖刚保存的草稿，还会清掉校验错误与提示。
let requestSeq = 0

const selectedDraft = computed(
  () => drafts.value.find((draft) => draft.key === selectedKey.value) ?? null,
)
const selectedForm = computed(() => selectedDraft.value?.form ?? emptyRobotDraft())
const selectedAppidChanged = computed(() => {
  const draft = selectedDraft.value
  return draft ? appidChanged(draft) : false
})
const appidChangeHint = computed(() =>
  selectedAppidChanged.value
    ? t(
        'pages.dashboard.robots.appidChangeWarning',
        '修改 AppID 会改变新版配置对兼容性机器人的接管关系：原 AppID 将回退到兼容性配置，新 AppID 将接管同名兼容性配置。',
      )
    : undefined,
)
const limits = computed<ConfigLimits>(() => response.value?.limits ?? FALLBACK_LIMITS)
const mockMode = computed(
  () => ready.value && (!hasBackend.value || isRobotMock(response.value)),
)
const editable = computed(
  () => selectedDraft.value !== null && hasBackend.value && !mockMode.value && !saving.value,
)
const canSave = computed(
  () =>
    hasBackend.value &&
    !mockMode.value &&
    (drafts.value.length > 0 || (response.value?.robots.length ?? 0) > 0) &&
    !loading.value &&
    !saving.value,
)

/** 最近一次从服务端载入或保存后的草稿快照，用来判断本地是否有未保存改动 */
const baseline = ref('[]')
const hasUnsavedChanges = computed(() => snapshotDrafts(drafts.value) !== baseline.value)

const unsavedTitle = computed(() =>
  pendingAction.value === 'reload'
    ? t('pages.dashboard.robots.unsavedReloadTitle', '重新载入会丢弃未保存的修改')
    : t('pages.dashboard.robots.unsavedImportTitle', '导入会覆盖未保存的修改'),
)
const unsavedText = computed(() =>
  pendingAction.value === 'reload'
    ? t(
        'pages.dashboard.robots.unsavedReloadText',
        '当前有未保存的机器人编辑，重新载入会用服务端配置替换草稿。可以先保存，或放弃这些修改后再载入。',
      )
    : t(
        'pages.dashboard.robots.unsavedImportText',
        '当前有未保存的机器人编辑，导入会用服务端配置替换草稿，新增或修改但未保存的机器人会丢失。可以先保存，或放弃这些修改后再导入。',
      ),
)

const sceneOptions = computed(() =>
  (response.value?.available_scenes?.length ? response.value.available_scenes : SCENES).map(
    (scene) => ({
      value: scene,
      title: sceneTitle(scene),
      icon: sceneIcon(scene),
    }),
  ),
)

const platformTypeItems = computed(() =>
  PLATFORM_TYPES.map((value) => ({
    title: platformTitle(value),
    value,
  })),
)

const robotSelectItems = computed(() =>
  drafts.value.map((draft) => ({
    value: draft.key,
    title: robotName(draft),
    subtitle: `${appidText(draft.form.appid)} ${robotMeta(draft)}`,
  })),
)

function sceneTitle(scene: Scene): string {
  if (scene === 'c2c') return t('pages.dashboard.robots.scene.c2c', '单聊')
  if (scene === 'group') return t('pages.dashboard.robots.scene.group', '群聊')
  if (scene === 'channel') return t('pages.dashboard.robots.scene.channel', '文字子频道')
  return t('pages.dashboard.robots.scene.dm', '频道私信')
}

function sceneIcon(scene: Scene): string {
  if (scene === 'c2c') return mdiAccountOutline
  if (scene === 'group') return mdiAccountGroupOutline
  if (scene === 'channel') return mdiMessageTextOutline
  return mdiRobotOutline
}

function platformTitle(platform: string): string {
  if (platform === 'qq_official_webhook') {
    return t(
      'pages.dashboard.robots.platformTypeName.qq_official_webhook',
      'QQ 官方机器人 Webhook',
    )
  }
  return t('pages.dashboard.robots.platformTypeName.qq_official', 'QQ 官方机器人')
}

function createDraft(robot: RobotConfig, index: number): RobotDraft {
  return {
    key: robot.id ? `robot:${robot.id}` : `robot:${index}`,
    form: toRobotForm(robot),
    savedAppid: robot.appid,
    secretMasked: robot.secret_masked,
    secretSet: robot.secret_set,
  }
}

function appidChanged(draft: RobotDraft): boolean {
  return robotAppidChanged(draft.form, draft.savedAppid)
}

/**
 * 草稿的结构化快照：只保留会随保存提交的内容，并按固定顺序序列化，
 * 这样新增 / 删除 / 修改任意字段（含未提交的 secret）都能被识别。
 */
function snapshotDrafts(list: RobotDraft[]): string {
  return JSON.stringify(
    list.map((draft) => ({
      id: draft.form.id,
      name: draft.form.name.trim(),
      appid: draft.form.appid.trim(),
      platform: draft.form.platform,
      secret: draft.form.secret.trim(),
      scenes: SCENES.map((scene) => {
        const config = draft.form.scenes[scene]
        return {
          scene,
          enabled: config?.enabled ?? false,
          items: (config?.items ?? []).map((item) => ({
            name: item.name.trim(),
            desc: item.desc.trim(),
          })),
        }
      }),
    })),
  )
}

function applyResponse(next: RobotConfigResponse, preferredAppid = ''): void {
  response.value = next
  const previousAppid = preferredAppid || selectedDraft.value?.form.appid.trim() || ''
  drafts.value = next.robots.map(createDraft)
  baseline.value = snapshotDrafts(drafts.value)
  robotErrors.value = {}
  const matched = previousAppid
    ? drafts.value.find((draft) => draft.form.appid.trim() === previousAppid)
    : undefined
  selectedKey.value = matched?.key ?? drafts.value[0]?.key ?? ''
}

async function load(): Promise<void> {
  const seq = ++requestSeq
  loading.value = true
  error.value = ''
  notice.value = ''
  try {
    const preferredAppid = selectedDraft.value?.form.appid.trim() ?? ''
    const next = await fetchRobots()
    if (seq !== requestSeq) return
    applyResponse(next, preferredAppid)
  } catch (err) {
    if (seq !== requestSeq) return
    response.value = null
    drafts.value = []
    baseline.value = snapshotDrafts(drafts.value)
    selectedKey.value = ''
    robotErrors.value = {}
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    if (seq === requestSeq) loading.value = false
  }
}

/** 「重新载入」和导入一样会整体替换草稿，有未保存改动时先让用户确认 */
function requestReload(): void {
  if (!hasBackend.value) return
  if (hasUnsavedChanges.value) {
    pendingAction.value = 'reload'
    unsavedError.value = ''
    unsavedDialog.value = true
    return
  }
  void load()
}

watch(
  [ready, hasBackend],
  ([isReady]) => {
    if (isReady) {
      void load()
    }
  },
  { immediate: true },
)

function selectRobot(key: string | null): void {
  if (key) {
    selectedKey.value = key
  }
}

/** 新增机器人走弹窗：先填基础信息，创建后再去配各场景的指令条目。
    mock 下也允许打开与创建——这里只动本地草稿，不落库，可以放心预览。 */
function openCreate(): void {
  createForm.value = emptyRobotDraft()
  createError.value = ''
  createDialog.value = true
}

function closeCreate(): void {
  createDialog.value = false
  createError.value = ''
}

function confirmCreate(): void {
  const checked = validateRobotForm(createForm.value, limits.value, t)
  if (!checked.ok) {
    createError.value = checked.reason
    return
  }
  const secret = createForm.value.secret.trim()
  const draft: RobotDraft = {
    key: `new:${++draftSeq}`,
    form: {
      ...emptyRobotDraft(),
      name: createForm.value.name.trim(),
      appid: createForm.value.appid.trim(),
      platform: createForm.value.platform,
      secret,
    },
    savedAppid: '',
    secretMasked: '',
    secretSet: Boolean(secret),
  }
  drafts.value.push(draft)
  selectedKey.value = draft.key
  delete robotErrors.value[draft.key]
  error.value = ''
  notice.value = ''
  closeCreate()
}

function openDelete(): void {
  deleteDialog.value = true
}

function closeDelete(): void {
  deleteDialog.value = false
}

function removeSelectedRobot(): void {
  const index = drafts.value.findIndex((draft) => draft.key === selectedKey.value)
  if (index < 0) return
  const [removed] = drafts.value.splice(index, 1)
  if (removed) {
    delete robotErrors.value[removed.key]
  }
  const next = drafts.value[index] ?? drafts.value[index - 1] ?? null
  selectedKey.value = next?.key ?? ''
  notice.value = mockMode.value
    ? t(
        'pages.dashboard.robots.removedMock',
        '已从本地列表移除（预览），不会写入配置。',
      )
    : t(
        'pages.dashboard.robots.removedLocal',
        '已从本地列表移除。保存后才会写入配置。',
      )
}

function confirmDelete(): void {
  removeSelectedRobot()
  closeDelete()
}

function addSceneItem(scene: Scene): void {
  const config = selectedDraft.value?.form.scenes[scene]
  if (!config || config.items.length >= limits.value.items_max) return
  config.items.push({ name: '', desc: '' })
}

function removeSceneItem(scene: Scene, index: number): void {
  selectedDraft.value?.form.scenes[scene].items.splice(index, 1)
}

function sceneItemCount(scene: Scene): number {
  return selectedDraft.value?.form.scenes[scene].items.length ?? 0
}

function sceneCountText(scene: Scene): string {
  return t('pages.dashboard.robots.scene.itemsCount', '{count}/{max} 条')
    .replace('{count}', String(sceneItemCount(scene)))
    .replace('{max}', String(limits.value.items_max))
}

function sceneLimitsText(): string {
  return t(
    'pages.dashboard.robots.scene.limits',
    '指令名 ≤ {name} 字，描述 ≤ {desc} 字。',
  )
    .replace('{name}', String(limits.value.name_max))
    .replace('{desc}', String(limits.value.desc_max))
}

function robotMeta(draft: RobotDraft): string {
  return t('pages.dashboard.robots.robotSummary', '场景 {scenes} 个，指令 {items} 条。')
    .replace('{scenes}', String(robotSceneCount(draft.form)))
    .replace('{items}', String(robotItemCount(draft.form)))
}

function appidText(appid: string): string {
  return t('pages.dashboard.robots.appidLabel', 'AppID：{appid}').replace(
    '{appid}',
    appid.trim() || '—',
  )
}

function robotName(draft: RobotDraft): string {
  return draft.form.name.trim() || t('pages.dashboard.robots.untitledRobot', '未命名机器人')
}

function secretPlaceholder(draft: RobotDraft): string {
  if (appidChanged(draft)) {
    return ''
  }
  if (!draft.secretSet) {
    return t('pages.dashboard.robots.secretRequired', '新机器人必须填写 ClientSecret。')
  }
  return t('pages.dashboard.robots.secretKeep', '留空表示沿用原值')
}

function secretHint(draft: RobotDraft): string | undefined {
  if (appidChanged(draft)) {
    return t(
      'pages.dashboard.robots.secretRequiredForAppidChange',
      '修改 AppID 后必须重新填写 ClientSecret。',
    )
  }
  if (draft.secretMasked) {
    return t('pages.dashboard.robots.secretSaved', '当前：{masked}').replace(
      '{masked}',
      draft.secretMasked,
    )
  }
  if (draft.secretSet) {
    return t(
      'pages.dashboard.robots.secretSetNoMask',
      '已保存 ClientSecret，留空表示沿用原值。',
    )
  }
  return undefined
}

type SaveResult =
  | { ok: true }
  | { ok: false; reason: 'validation' | 'request'; message?: string }

async function save(options: { sync?: boolean } = {}): Promise<SaveResult> {
  if (!hasBackend.value || mockMode.value) {
    return { ok: false, reason: 'request' }
  }

  const robots: RobotConfigPayload[] = []
  const errors: Record<string, string> = {}
  let firstErrorKey = ''
  for (const draft of drafts.value) {
    const checked = validateRobotForm(draft.form, limits.value, t, {
      savedAppid: draft.savedAppid,
    })
    if (!checked.ok) {
      errors[draft.key] = checked.reason
      if (!firstErrorKey) firstErrorKey = draft.key
      continue
    }
    robots.push(checked.payload)
  }

  robotErrors.value = errors
  if (firstErrorKey) {
    selectedKey.value = firstErrorKey
    error.value = ''
    notice.value = ''
    return { ok: false, reason: 'validation' }
  }

  const preferredAppid = selectedDraft.value?.form.appid.trim() ?? ''
  // 保存会写回服务端最新结果，先让仍在路上的 load 失效，避免它稍后覆盖草稿
  const seq = ++requestSeq
  loading.value = false
  saving.value = true
  error.value = ''
  notice.value = ''
  try {
    const next = await saveRobots({ version: response.value?.version ?? 1, robots })
    if (seq !== requestSeq) return { ok: false, reason: 'request' }
    applyResponse(next, preferredAppid)
    notice.value = t('pages.dashboard.robots.saved', '机器人配置已保存。')
  } catch (err) {
    if (seq !== requestSeq) return { ok: false, reason: 'request' }
    const message = err instanceof Error ? err.message : String(err)
    error.value = message
    return { ok: false, reason: 'request', message }
  } finally {
    saving.value = false
  }

  if (options.sync) {
    try {
      await startSync()
      await router.push({ name: 'status' })
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
    }
  }
  return { ok: true }
}

async function openImport(): Promise<void> {
  // mock 下也允许打开：fetchConfig 会回退到 mock 数据，可以先看流程；
  // 真正的导入动作仍需要后端，由弹窗里的按钮单独把关
  importPanel.value = true
  importError.value = ''
  importLoading.value = true
  try {
    const legacy = await fetchConfig()
    legacyAppidsText.value = legacy.qq_platforms
      .map((platform) => platform.appid.trim())
      .filter(Boolean)
      .join('\n')
    if (!legacyAppidsText.value) {
      importError.value = t(
        'pages.dashboard.robots.importEmpty',
        '兼容配置里没有可导入的 AppID，请手动填写。',
      )
    }
  } catch (err) {
    importError.value = err instanceof Error ? err.message : String(err)
  } finally {
    importLoading.value = false
  }
}

function parseAppids(value: string): string[] {
  const seen = new Set<string>()
  const result: string[] = []
  for (const item of value.split(/[\s,，]+/)) {
    const appid = item.trim()
    if (!appid || seen.has(appid)) continue
    seen.add(appid)
    result.push(appid)
  }
  return result
}

function closeImport(): void {
  importPanel.value = false
  importError.value = ''
}

async function importLegacy(
  options: { confirmed?: boolean; discarded?: boolean } = {},
): Promise<void> {
  const currentBridge = bridge.value
  if (!hasBackend.value || !currentBridge) return
  const appids = parseAppids(legacyAppidsText.value)
  if (!appids.length) {
    importError.value = t('pages.dashboard.robots.importNoAppids', '至少填写一个 AppID。')
    return
  }

  // 导入会整体替换本地草稿：先让用户决定保存、放弃还是取消，避免静默丢改动
  if (hasUnsavedChanges.value && !options.confirmed) {
    pendingAction.value = 'import'
    unsavedError.value = ''
    unsavedDialog.value = true
    return
  }

  // 导入会写回服务端并重载草稿：先领取代次，让仍在路上的 load 失效，
  // 否则旧 GET 稍后返回时会把刚导入的结果覆盖回导入前的快照。
  const seq = ++requestSeq
  loading.value = false
  importing.value = true
  importError.value = ''
  try {
    await currentBridge.apiPost('robots/import-legacy', {
      appids,
      version: response.value?.version ?? 1,
    })
    if (seq !== requestSeq) return
    const preferredAppid = selectedDraft.value?.form.appid.trim() ?? ''
    const next = await fetchRobots()
    if (seq !== requestSeq) return
    applyResponse(next, preferredAppid)
    importPanel.value = false
    legacyAppidsText.value = ''
    notice.value = options.discarded
      ? t(
          'pages.dashboard.robots.importedDiscarded',
          '已从兼容配置导入并保存机器人配置，未保存的本地修改已丢弃。',
        )
      : t(
          'pages.dashboard.robots.imported',
          '已从兼容配置导入并保存机器人配置，请检查后再同步。',
        )
  } catch (err) {
    if (seq !== requestSeq) return
    importError.value = err instanceof Error ? err.message : String(err)
  } finally {
    if (seq === requestSeq) importing.value = false
  }
}

function cancelUnsaved(): void {
  pendingAction.value = null
  unsavedError.value = ''
  unsavedDialog.value = false
}

/** 未保存改动的三个出口：先保存、放弃本地改动，或取消当前操作 */
async function continuePending(strategy: 'save' | 'discard'): Promise<void> {
  const target = pendingAction.value
  if (!target) return

  unsavedError.value = ''
  if (strategy === 'save') {
    const result = await save()
    if (!result.ok) {
      // 校验失败时弹窗挡住了页面，需要提示用户先取消弹窗去改；
      // 请求失败则直接展示真实原因（例如 409 版本冲突），不要伪装成校验错误
      if (result.reason === 'validation') {
        unsavedError.value = t(
          'pages.dashboard.robots.unsavedSaveFailed',
          '保存失败，请先取消弹窗并处理页面上的校验错误后再继续。',
        )
      } else {
        unsavedError.value =
          result.message ??
          t('pages.dashboard.robots.unsavedSaveRequestFailed', '保存失败，请稍后重试。')
      }
      return
    }
  }

  pendingAction.value = null
  unsavedDialog.value = false
  if (target === 'import') {
    await importLegacy({ confirmed: true, discarded: strategy === 'discard' })
  } else {
    await load()
  }
}
</script>

<template>
  <v-container fluid class="qc-page qc-robots-page pa-4 pa-md-6">
    <div class="qc-header">
      <div class="qc-header-main">
        <h1 class="qc-title">{{ t('pages.dashboard.robots.title', '机器人') }}</h1>
        <p class="qc-subtitle">
          {{
            t(
              'pages.dashboard.robots.subtitle',
              '按机器人维护不同场景下的指令条目，每台机器人独立生效。',
            )
          }}
        </p>
      </div>

      <div class="qc-header-actions">
        <v-btn
          variant="text"
          color="primary"
          :loading="loading"
          :disabled="!hasBackend || saving || importing"
          @click="requestReload"
        >
          {{ t('pages.dashboard.robots.reload', '重新载入') }}
        </v-btn>
        <v-btn
          variant="tonal"
          color="primary"
          :prepend-icon="mdiImport"
          :disabled="saving || importing"
          @click="openImport"
        >
          {{ t('pages.dashboard.robots.importLegacy', '从兼容配置导入') }}
        </v-btn>
        <v-btn
          variant="tonal"
          color="primary"
          :prepend-icon="mdiPlus"
          :disabled="saving"
          @click="openCreate"
        >
          {{ t('pages.dashboard.robots.addRobot', '新增机器人') }}
        </v-btn>
        <v-btn
          variant="tonal"
          color="primary"
          :prepend-icon="mdiContentSave"
          :loading="saving"
          :disabled="!canSave"
          @click="save()"
        >
          {{ t('pages.dashboard.robots.save', '保存') }}
        </v-btn>
        <v-btn
          variant="tonal"
          color="primary"
          :prepend-icon="mdiSync"
          :loading="saving"
          :disabled="!canSave"
          @click="save({ sync: true })"
        >
          {{ t('pages.dashboard.robots.saveAndSync', '保存并同步') }}
        </v-btn>
      </div>
    </div>

    <v-progress-linear v-if="loading" class="mb-4" color="primary" indeterminate />

    <v-alert
      v-if="mockMode"
      class="qc-mock-hint mb-4"
      type="info"
      variant="tonal"
      :icon="mdiAlertCircleOutline"
    >
      {{
        t(
          'pages.dashboard.robots.mockHint',
          '本地开发环境：展示的是 mock 数据，不能保存配置。',
        )
      }}
    </v-alert>

    <v-alert v-if="error" class="mb-4" type="error" variant="tonal">
      {{ error }}
    </v-alert>
    <v-alert v-if="notice" class="mb-4" type="success" variant="tonal">
      {{ notice }}
    </v-alert>

    <v-dialog v-model="importPanel" max-width="560">
      <v-card class="qc-import-panel" variant="flat" rounded="lg">
        <v-card-item class="px-5 pt-5">
          <v-card-title class="text-body-large">
            {{ t('pages.dashboard.robots.importTitle', '从兼容配置导入') }}
          </v-card-title>
          <v-card-subtitle>
            {{
              t(
                'pages.dashboard.robots.importSubtitle',
                '选择或填写要导入的旧版平台 AppID，每个 AppID 单独一行或使用逗号分隔。',
              )
            }}
          </v-card-subtitle>
        </v-card-item>
        <v-card-text class="px-5 pt-2">
          <v-textarea
            v-model="legacyAppidsText"
            class="qc-import-appids"
            data-field="legacy-appids"
            :disabled="importing"
            :loading="importLoading"
            :label="t('pages.dashboard.robots.importAppids', 'AppID 列表')"
            variant="outlined"
            density="compact"
            rows="4"
            hide-details
          />
          <v-alert v-if="importError" class="mt-3" type="error" variant="tonal" density="compact">
            {{ importError }}
          </v-alert>
        </v-card-text>
        <v-card-actions class="px-5 pb-5">
          <v-spacer />
          <v-btn variant="text" :disabled="importing" @click="closeImport">
            {{ t('pages.dashboard.robots.cancel', '取消') }}
          </v-btn>
          <v-btn
            color="primary"
            variant="tonal"
            :loading="importing"
            :disabled="!hasBackend || importLoading"
            @click="importLegacy()"
          >
            {{ t('pages.dashboard.robots.importConfirm', '导入') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="createDialog" max-width="560">
      <v-card class="qc-robot-create" variant="flat" rounded="lg">
        <v-card-item class="px-5 pt-5">
          <v-card-title class="text-body-large">
            {{ t('pages.dashboard.robots.addRobot', '新增机器人') }}
          </v-card-title>
          <v-card-subtitle>
            {{
              t(
                'pages.dashboard.robots.createSubtitle',
                '先填名称与平台凭证；创建后再去配置各场景的指令条目。',
              )
            }}
          </v-card-subtitle>
        </v-card-item>
        <v-card-text class="px-5 pt-2">
          <v-text-field
            v-model="createForm.name"
            class="mb-3"
            data-field="create-name"
            :maxlength="limits.name_max"
            :counter="limits.name_max"
            :label="t('pages.dashboard.robots.name', '机器人名称')"
            variant="outlined"
            density="compact"
            hide-details
          />
          <v-text-field
            v-model="createForm.appid"
            class="mb-3"
            data-field="create-appid"
            label="AppID"
            variant="outlined"
            density="compact"
            hide-details
          />
          <v-text-field
            v-model="createForm.secret"
            class="mb-3"
            data-field="create-secret"
            type="password"
            :label="t('pages.dashboard.robots.secret', 'ClientSecret')"
            variant="outlined"
            density="compact"
            hide-details
          />
          <v-select
            v-model="createForm.platform"
            data-field="create-platform"
            :items="platformTypeItems"
            :label="t('pages.dashboard.robots.platformType', '平台类型')"
            variant="outlined"
            density="compact"
            hide-details
          />
          <v-alert v-if="createError" class="mt-3" type="error" variant="tonal" density="compact">
            {{ createError }}
          </v-alert>
        </v-card-text>
        <v-card-actions class="px-5 pb-5">
          <v-spacer />
          <v-btn variant="text" @click="closeCreate">
            {{ t('pages.dashboard.robots.cancel', '取消') }}
          </v-btn>
          <v-btn color="primary" variant="tonal" @click="confirmCreate">
            {{ t('pages.dashboard.robots.createConfirm', '创建') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="deleteDialog" max-width="480">
      <v-card class="qc-robot-delete" variant="flat" rounded="lg">
        <v-card-item class="px-5 pt-5">
          <v-card-title class="text-body-large">
            {{ t('pages.dashboard.robots.deleteConfirmTitle', '删除机器人配置？') }}
          </v-card-title>
          <v-card-subtitle>
            {{ selectedForm.name }}
            <span v-if="selectedForm.appid">（{{ selectedForm.appid }}）</span>
          </v-card-subtitle>
        </v-card-item>
        <v-card-text>
          <div>
            {{
              t(
                'pages.dashboard.robots.deleteConfirmText',
                '删除后需要保存才会写入配置，QQ 线上已有的指令面板不会被清理。',
              )
            }}
          </div>
        </v-card-text>
        <v-card-actions class="px-5 pb-5">
          <v-spacer />
          <v-btn variant="text" @click="closeDelete">
            {{ t('pages.dashboard.robots.cancel', '取消') }}
          </v-btn>
          <v-btn color="error" variant="tonal" @click="confirmDelete">
            {{ t('pages.dashboard.robots.deleteConfirm', '确认删除') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="unsavedDialog" max-width="520">
      <v-card class="qc-robot-unsaved" variant="flat" rounded="lg">
        <v-card-item class="px-5 pt-5">
          <v-card-title class="text-body-large">{{ unsavedTitle }}</v-card-title>
        </v-card-item>
        <v-card-text class="px-5 pt-2">
          <div>{{ unsavedText }}</div>
          <v-alert
            v-if="unsavedError"
            class="mt-3"
            type="error"
            variant="tonal"
            density="compact"
          >
            {{ unsavedError }}
          </v-alert>
        </v-card-text>
        <v-card-actions class="px-5 pb-5">
          <v-spacer />
          <v-btn variant="text" :disabled="saving || importing" @click="cancelUnsaved">
            {{ t('pages.dashboard.robots.cancel', '取消') }}
          </v-btn>
          <v-btn
            variant="text"
            color="error"
            :disabled="saving || importing"
            @click="continuePending('discard')"
          >
            {{ t('pages.dashboard.robots.unsavedDiscard', '放弃修改并继续') }}
          </v-btn>
          <v-btn
            color="primary"
            variant="tonal"
            :loading="saving"
            :disabled="importing"
            @click="continuePending('save')"
          >
            {{ t('pages.dashboard.robots.unsavedSave', '保存并继续') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-card class="qc-card qc-robots-layout qc-robots-shell" variant="outlined">
      <section class="qc-robots-pane qc-robot-list" data-pane="list">
        <v-card-item class="px-5 pt-5">
          <v-card-title class="text-body-large">
            {{ t('pages.dashboard.robots.listTitle', '机器人') }}
          </v-card-title>
          <v-card-subtitle>
            {{ t('pages.dashboard.robots.listSubtitle', '选择一台机器人编辑它的场景指令。') }}
          </v-card-subtitle>
        </v-card-item>

        <v-card-text class="px-5 pb-5 pt-2">
          <div v-if="!drafts.length" class="qc-metric-note">
            {{ t('pages.dashboard.robots.emptyRobots', '还没有机器人，先新增一台。') }}
          </div>

          <div v-else class="qc-robot-card-list">
            <v-card
              v-for="draft in drafts"
              :key="draft.key"
              class="qc-config-item qc-robot-item mb-3"
              :class="{ 'qc-robot-item--active': draft.key === selectedKey }"
              :variant="draft.key === selectedKey ? 'tonal' : 'flat'"
              :color="draft.key === selectedKey ? 'primary' : undefined"
              role="button"
              tabindex="0"
              @click="selectRobot(draft.key)"
              @keydown.enter.prevent="selectRobot(draft.key)"
              @keydown.space.prevent="selectRobot(draft.key)"
            >
              <div class="d-flex align-center ga-3">
                <v-icon :icon="mdiRobotOutline" size="22" />
                <div class="qc-row-main flex-grow-1">
                  <div class="font-weight-medium">{{ robotName(draft) }}</div>
                  <div class="qc-metric-note">{{ appidText(draft.form.appid) }}</div>
                  <div class="qc-metric-note">{{ robotMeta(draft) }}</div>
                </div>
              </div>
              <v-alert
                v-if="robotErrors[draft.key]"
                class="qc-robot-error mt-3"
                type="error"
                variant="tonal"
                density="compact"
              >
                {{ robotErrors[draft.key] }}
              </v-alert>
            </v-card>
          </div>

          <div v-if="drafts.length" class="qc-robot-select">
            <v-select
              :model-value="selectedKey"
              :items="robotSelectItems"
              :label="t('pages.dashboard.robots.listTitle', '机器人')"
              :menu-props="{ maxHeight: 320 }"
              :prepend-inner-icon="mdiRobotOutline"
              variant="outlined"
              density="comfortable"
              hide-details
              @update:model-value="selectRobot"
            >
              <template #item="{ props, item }">
                <v-list-item v-bind="props" :subtitle="item.subtitle" role="option" />
              </template>
            </v-select>
            <v-alert
              v-if="selectedDraft && robotErrors[selectedDraft.key]"
              class="qc-robot-error mt-3"
              type="error"
              variant="tonal"
              density="compact"
            >
              {{ robotErrors[selectedDraft.key] }}
            </v-alert>
          </div>
        </v-card-text>
      </section>

      <v-divider class="qc-robots-divider qc-robots-divider--desktop" vertical />
      <v-divider class="qc-robots-divider qc-robots-divider--mobile" />

      <section class="qc-robots-pane qc-robot-editor" data-pane="editor">
        <v-card
          v-if="!selectedDraft"
          class="qc-card qc-robot-editor--empty"
          variant="outlined"
        >
          <v-card-text class="qc-metric-note py-8">
            {{ t('pages.dashboard.robots.editorEmpty', '请选择或新增一台机器人。') }}
          </v-card-text>
        </v-card>

        <template v-else>
          <v-alert
            v-if="robotErrors[selectedDraft.key]"
            class="qc-robot-error mb-4"
            type="error"
            variant="tonal"
          >
            {{ robotErrors[selectedDraft.key] }}
          </v-alert>

          <v-card class="qc-card qc-robot-basic mb-4" variant="outlined">
            <v-card-item class="px-5 pt-5">
              <v-card-title class="text-body-large">
                {{ t('pages.dashboard.robots.basicTitle', '基础信息') }}
              </v-card-title>
              <v-card-subtitle>
                {{
                  t(
                    'pages.dashboard.robots.basicSubtitle',
                    '名称、AppID 与平台凭证只用于这台机器人。',
                  )
                }}
              </v-card-subtitle>
            </v-card-item>

            <v-card-text class="px-5 pb-5 pt-3">
              <v-row>
                <v-col cols="12" md="6">
                  <v-text-field
                    v-model="selectedForm.name"
                    data-field="name"
                    :disabled="!editable"
                    :maxlength="limits.name_max"
                    :counter="limits.name_max"
                    :label="t('pages.dashboard.robots.name', '机器人名称')"
                    variant="outlined"
                    density="compact"
                    hide-details
                  />
                </v-col>
                <v-col cols="12" md="6">
                  <v-text-field
                    v-model="selectedForm.appid"
                    data-field="appid"
                    :disabled="!editable"
                    :hide-details="!selectedAppidChanged"
                    :persistent-hint="selectedAppidChanged"
                    :hint="appidChangeHint"
                    :label="t('pages.dashboard.robots.appid', 'AppID')"
                    variant="outlined"
                    density="compact"
                  />
                </v-col>
                <v-col cols="12" md="8">
                  <v-text-field
                    v-model="selectedForm.secret"
                    data-field="secret"
                    :disabled="!editable"
                    type="password"
                    :placeholder="secretPlaceholder(selectedDraft)"
                    :hint="secretHint(selectedDraft)"
                    persistent-hint
                    :label="t('pages.dashboard.robots.secret', 'ClientSecret')"
                    variant="outlined"
                    density="compact"
                  />
                </v-col>
                <v-col cols="12" md="4">
                  <v-select
                    v-model="selectedForm.platform"
                    data-field="platform"
                    :disabled="!editable"
                    :items="platformTypeItems"
                    :label="t('pages.dashboard.robots.platformType', '平台类型')"
                    variant="outlined"
                    density="compact"
                    hide-details
                  />
                </v-col>
              </v-row>
            </v-card-text>
          </v-card>

          <v-card class="qc-card qc-robot-scenes" variant="outlined">
            <v-card-item class="px-5 pt-5">
              <v-card-title class="text-body-large">
                {{ t('pages.dashboard.robots.scenesTitle', '场景指令') }}
              </v-card-title>
              <v-card-subtitle>
                {{
                  t(
                    'pages.dashboard.robots.scenesSubtitle',
                    '每个场景独立维护指令条目；启用后至少保留 1 条。',
                  )
                }}
              </v-card-subtitle>
            </v-card-item>

            <v-card-text class="px-5 pb-5 pt-3">
              <div
                v-for="scene in sceneOptions"
                :key="scene.value"
                class="qc-config-item qc-scene-editor mb-4"
                :data-scene="scene.value"
              >
                <div class="d-flex align-center flex-wrap ga-3">
                  <v-switch
                    v-model="selectedForm.scenes[scene.value].enabled"
                    data-field="scene-enabled"
                    color="primary"
                    inset
                    hide-details
                    :disabled="!editable"
                    :label="scene.title"
                  />
                  <v-icon :icon="scene.icon" size="20" class="qc-metric-note" />
                  <v-spacer />
                  <v-chip size="small" variant="tonal">
                    {{ sceneCountText(scene.value) }}
                  </v-chip>
                </div>

                <div class="qc-metric-note">{{ sceneLimitsText() }}</div>

                <template v-if="selectedForm.scenes[scene.value].enabled">
                  <div
                    v-if="!selectedForm.scenes[scene.value].items.length"
                    class="qc-metric-note"
                  >
                    {{ t('pages.dashboard.robots.scene.noItems', '这个场景还没有指令条目。') }}
                  </div>

                  <div
                    v-for="(item, index) in selectedForm.scenes[scene.value].items"
                    :key="index"
                    class="qc-config-item qc-scene-command mt-3"
                  >
                    <v-row>
                      <v-col cols="12" md="5">
                        <v-text-field
                          v-model="item.name"
                          data-field="command-name"
                          :disabled="!editable"
                          :maxlength="limits.name_max"
                          :counter="limits.name_max"
                          :label="t('pages.dashboard.robots.scene.commandName', '指令名')"
                          variant="outlined"
                          density="compact"
                          hide-details
                        />
                      </v-col>
                      <v-col cols="12" md="6">
                        <v-text-field
                          v-model="item.desc"
                          data-field="command-desc"
                          :disabled="!editable"
                          :maxlength="limits.desc_max"
                          :counter="limits.desc_max"
                          :label="t('pages.dashboard.robots.scene.commandDesc', '指令描述')"
                          variant="outlined"
                          density="compact"
                          hide-details
                        />
                      </v-col>
                      <v-col cols="12" md="1" class="d-flex align-center justify-end">
                        <v-btn
                          icon
                          size="small"
                          variant="text"
                          color="error"
                          data-action="remove-command"
                          :disabled="!editable"
                          :aria-label="
                            t('pages.dashboard.robots.scene.removeItem', '删除指令')
                          "
                          @click="removeSceneItem(scene.value, index)"
                        >
                          <v-icon :icon="mdiTrashCanOutline" size="20" />
                        </v-btn>
                      </v-col>
                    </v-row>
                  </div>

                  <v-btn
                    class="mt-3"
                    variant="text"
                    color="primary"
                    data-action="add-command"
                    :prepend-icon="mdiPlus"
                    :disabled="
                      !editable ||
                      selectedForm.scenes[scene.value].items.length >= limits.items_max
                    "
                    @click="addSceneItem(scene.value)"
                  >
                    {{ t('pages.dashboard.robots.scene.addItem', '添加指令') }}
                  </v-btn>
                </template>

                <div v-else class="qc-metric-note">
                  {{
                    t(
                      'pages.dashboard.robots.scene.disabledHint',
                      '场景未启用，开启后可管理指令条目。',
                    )
                  }}
                </div>
              </div>
            </v-card-text>
          </v-card>

          <v-card class="qc-card qc-robot-danger mt-4" variant="outlined">
            <v-card-item class="px-5 pt-5">
              <v-card-title class="text-body-large">
                {{ t('pages.dashboard.robots.dangerTitle', '删除机器人配置') }}
              </v-card-title>
            </v-card-item>
            <v-card-text class="px-5 pt-2">
              <v-alert
                type="warning"
                variant="tonal"
                density="compact"
                :icon="mdiAlertCircleOutline"
              >
                {{
                  t(
                    'pages.dashboard.robots.dangerText',
                    '删除只移除这里的配置，不会清理 QQ 线上已有的指令面板。',
                  )
                }}
              </v-alert>
            </v-card-text>
            <v-card-actions class="px-5 pb-5">
              <v-btn
                color="error"
                variant="tonal"
                :prepend-icon="mdiTrashCanOutline"
                :disabled="!selectedDraft || saving"
                @click="openDelete"
              >
                {{ t('pages.dashboard.robots.deleteRobot', '删除机器人配置') }}
              </v-btn>
            </v-card-actions>
          </v-card>
        </template>
      </section>
    </v-card>

  </v-container>
</template>
