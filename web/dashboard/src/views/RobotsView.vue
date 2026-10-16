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

let draftSeq = 0

const selectedDraft = computed(
  () => drafts.value.find((draft) => draft.key === selectedKey.value) ?? null,
)
const selectedForm = computed(() => selectedDraft.value?.form ?? emptyRobotDraft())
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
    secretMasked: robot.secret_masked,
    secretSet: robot.secret_set,
  }
}

function applyResponse(next: RobotConfigResponse, preferredAppid = ''): void {
  response.value = next
  const previousAppid = preferredAppid || selectedDraft.value?.form.appid.trim() || ''
  drafts.value = next.robots.map(createDraft)
  robotErrors.value = {}
  const matched = previousAppid
    ? drafts.value.find((draft) => draft.form.appid.trim() === previousAppid)
    : undefined
  selectedKey.value = matched?.key ?? drafts.value[0]?.key ?? ''
}

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  notice.value = ''
  try {
    const preferredAppid = selectedDraft.value?.form.appid.trim() ?? ''
    const next = await fetchRobots()
    applyResponse(next, preferredAppid)
  } catch (err) {
    response.value = null
    drafts.value = []
    selectedKey.value = ''
    robotErrors.value = {}
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    loading.value = false
  }
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

function selectRobot(key: string): void {
  selectedKey.value = key
}

function addRobot(): void {
  if (!hasBackend.value || mockMode.value) return
  const draft: RobotDraft = {
    key: `new:${++draftSeq}`,
    form: emptyRobotDraft(),
    secretMasked: '',
    secretSet: false,
  }
  drafts.value.push(draft)
  selectedKey.value = draft.key
  delete robotErrors.value[draft.key]
  error.value = ''
  notice.value = ''
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
  notice.value = t(
    'pages.dashboard.robots.removedLocal',
    '已从本地列表移除。保存后才会写入配置。',
  )
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
  if (!draft.secretSet) {
    return t('pages.dashboard.robots.secretRequired', '新机器人必须填写 ClientSecret。')
  }
  return t('pages.dashboard.robots.secretKeep', '留空表示沿用原值')
}

function secretHint(draft: RobotDraft): string | undefined {
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

async function save(options: { sync?: boolean } = {}): Promise<void> {
  if (!hasBackend.value || mockMode.value) return

  const robots: RobotConfigPayload[] = []
  const errors: Record<string, string> = {}
  let firstErrorKey = ''
  for (const draft of drafts.value) {
    const checked = validateRobotForm(draft.form, limits.value, t)
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
    return
  }

  const preferredAppid = selectedDraft.value?.form.appid.trim() ?? ''
  saving.value = true
  error.value = ''
  notice.value = ''
  try {
    const next = await saveRobots({ version: response.value?.version ?? 1, robots })
    applyResponse(next, preferredAppid)
    notice.value = t('pages.dashboard.robots.saved', '机器人配置已保存。')
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
    return
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
}

async function openImport(): Promise<void> {
  if (!hasBackend.value) return
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

async function importLegacy(): Promise<void> {
  const currentBridge = bridge.value
  if (!hasBackend.value || !currentBridge) return
  const appids = parseAppids(legacyAppidsText.value)
  if (!appids.length) {
    importError.value = t('pages.dashboard.robots.importNoAppids', '至少填写一个 AppID。')
    return
  }

  importing.value = true
  importError.value = ''
  try {
    await currentBridge.apiPost('robots/import-legacy', {
      appids,
      version: response.value?.version ?? 1,
    })
    const preferredAppid = selectedDraft.value?.form.appid.trim() ?? ''
    const next = await fetchRobots()
    applyResponse(next, preferredAppid)
    importPanel.value = false
    legacyAppidsText.value = ''
    notice.value = t(
      'pages.dashboard.robots.imported',
      '已从兼容配置导入并保存机器人配置，请检查后再同步。',
    )
  } catch (err) {
    importError.value = err instanceof Error ? err.message : String(err)
  } finally {
    importing.value = false
  }
}
</script>

<template>
  <v-container fluid class="qc-page pa-4 pa-md-6">
    <div class="qc-header">
      <div>
        <h1 class="qc-title">{{ t('pages.dashboard.robots.title', '新版配置') }}</h1>
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
          :disabled="!hasBackend"
          @click="load"
        >
          {{ t('pages.dashboard.robots.reload', '重新载入') }}
        </v-btn>
        <v-btn
          variant="tonal"
          color="primary"
          :prepend-icon="mdiImport"
          :disabled="!hasBackend || saving || importing"
          @click="openImport"
        >
          {{ t('pages.dashboard.robots.importLegacy', '从兼容配置导入') }}
        </v-btn>
        <v-btn
          variant="tonal"
          color="primary"
          :prepend-icon="mdiPlus"
          :disabled="!hasBackend || mockMode || saving"
          @click="addRobot"
        >
          {{ t('pages.dashboard.robots.addRobot', '新增机器人') }}
        </v-btn>
        <v-btn
          variant="flat"
          color="primary"
          :prepend-icon="mdiContentSave"
          :loading="saving"
          :disabled="!canSave"
          @click="save()"
        >
          {{ t('pages.dashboard.robots.save', '保存') }}
        </v-btn>
        <v-btn
          variant="flat"
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

    <v-card v-if="importPanel" class="qc-card qc-import-panel mb-4" variant="outlined">
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
          density="comfortable"
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
          variant="flat"
          :loading="importing"
          :disabled="!hasBackend || importLoading"
          @click="importLegacy"
        >
          {{ t('pages.dashboard.robots.importConfirm', '导入') }}
        </v-btn>
      </v-card-actions>
    </v-card>

    <v-row class="qc-robots-layout">
      <v-col cols="12" md="4" lg="3">
        <v-card class="qc-card qc-robot-list" variant="outlined">
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
          </v-card-text>
        </v-card>
      </v-col>

      <v-col cols="12" md="8" lg="9">
        <v-card
          v-if="!selectedDraft"
          class="qc-card qc-robot-editor qc-robot-editor--empty"
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
                    density="comfortable"
                    hide-details
                  />
                </v-col>
                <v-col cols="12" md="6">
                  <v-text-field
                    v-model="selectedForm.appid"
                    data-field="appid"
                    :disabled="!editable"
                    :label="t('pages.dashboard.robots.appid', 'AppID')"
                    variant="outlined"
                    density="comfortable"
                    hide-details
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
                    density="comfortable"
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
                    density="comfortable"
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
                          density="comfortable"
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
                          density="comfortable"
                          hide-details
                        />
                      </v-col>
                      <v-col cols="12" md="1" class="d-flex align-center justify-end">
                        <v-btn
                          icon
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
                :disabled="!editable"
                @click="removeSelectedRobot"
              >
                {{ t('pages.dashboard.robots.deleteRobot', '删除机器人配置') }}
              </v-btn>
            </v-card-actions>
          </v-card>
        </template>
      </v-col>
    </v-row>

  </v-container>
</template>
