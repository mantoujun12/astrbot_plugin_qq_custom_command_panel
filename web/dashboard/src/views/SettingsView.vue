<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import {
  mdiAlertCircleOutline,
  mdiCheckCircleOutline,
  mdiContentSave,
  mdiInformationOutline,
  mdiPlus,
  mdiTrashCanOutline,
} from '@mdi/js'
import { fetchConfig, saveConfig } from '../api/dashboard'
import { useBridge } from '../composables/useBridge'
import { useSyncRun } from '../composables/useSyncRun'
import type {
  ConfigCommand,
  ConfigPlatformPayload,
  PluginConfigPayload,
  PluginConfigResponse,
  Scene,
} from '../types/dashboard'

const { t, ready, hasBackend } = useBridge()
const router = useRouter()
const { start: startSync } = useSyncRun()

const LANGUAGE_OPTIONS: string[] = ['zh-CN', 'en-US']
const PLATFORM_TYPES = ['qq_official', 'qq_official_webhook'] as const

const config = ref<PluginConfigResponse | null>(null)
const form = ref<PluginConfigPayload | null>(null)
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const notice = ref('')

/** 本地开发没有 bridge，页面只展示 mock 并禁用编辑，不允许假装保存成功 */
const mockMode = computed(() => ready.value && !hasBackend.value)
const editable = computed(() => form.value !== null && hasBackend.value && !saving.value)

const sceneItems = computed(() =>
  (config.value?.available_scenes ?? []).map((scene: Scene) => ({
    title: t(`pages.dashboard.settings.scene.${scene}`, scene),
    value: scene,
  })),
)

const platformTypeItems = PLATFORM_TYPES.map((value) => ({
  title: t(
    `pages.dashboard.settings.platformTypeName.${value}`,
    value === 'qq_official' ? 'QQ 官方机器人' : 'QQ 官方机器人 Webhook',
  ),
  value,
}))

const limits = computed(
  () => config.value?.limits ?? { name_max: 14, desc_max: 30, items_max: 20 },
)

/** 已保存平台按 appid 建索引：新增/删除行会改变下标，占位与提示要按 appid 跟随当前行 */
const savedPlatforms = computed(
  () => new Map((config.value?.qq_platforms ?? []).map((platform) => [platform.appid, platform])),
)

function savedPlatform(appid: string) {
  return savedPlatforms.value.get(appid.trim())
}

function toForm(source: PluginConfigResponse): PluginConfigPayload {
  return {
    language: source.language,
    scenes: [...source.scenes],
    qq_platforms: source.qq_platforms.map((platform) => ({
      name: platform.name,
      appid: platform.appid,
      platform: platform.platform,
      secret: '',
    })),
    selected_commands: source.selected_commands.map((command) => ({ ...command })),
  }
}

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const next = await fetchConfig()
    config.value = next
    form.value = toForm(next)
  } catch (err) {
    config.value = null
    form.value = null
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

function addPlatform(): void {
  form.value?.qq_platforms.push({
    name: '',
    appid: '',
    platform: 'qq_official',
    secret: '',
  })
}

function removePlatform(index: number): void {
  form.value?.qq_platforms.splice(index, 1)
}

function addCommand(): void {
  if (!form.value || form.value.selected_commands.length >= limits.value.items_max) {
    return
  }
  form.value.selected_commands.push({ name: '', desc: '' })
}

function removeCommand(index: number): void {
  form.value?.selected_commands.splice(index, 1)
}

/** 与后端 normalize_config_payload 对齐的本地校验，尽早给出提示 */
function validate(): string {
  const payload = form.value
  if (!payload) {
    return t('pages.dashboard.settings.notLoaded', '配置尚未载入。')
  }
  if (payload.selected_commands.length > limits.value.items_max) {
    return t('pages.dashboard.settings.commandsTooMany', '指令条目超出上限。')
  }
  const commands: ConfigCommand[] = []
  for (const command of payload.selected_commands) {
    if (!command.name.trim()) {
      return t('pages.dashboard.settings.commandNameRequired', '指令名不能为空。')
    }
    if (command.name.length > limits.value.name_max) {
      return t('pages.dashboard.settings.commandNameTooLong', '指令名超出长度上限。')
    }
    if (command.desc.length > limits.value.desc_max) {
      return t('pages.dashboard.settings.commandDescTooLong', '指令描述超出长度上限。')
    }
    commands.push({ name: command.name.trim(), desc: command.desc.trim() })
  }
  const platforms: ConfigPlatformPayload[] = []
  const savedSecret = new Map(
    (config.value?.qq_platforms ?? []).map((platform) => [platform.appid, platform]),
  )
  for (const platform of payload.qq_platforms) {
    const appid = platform.appid.trim()
    if (!appid) {
      return t('pages.dashboard.settings.platformAppidRequired', '平台 appid 不能为空。')
    }
    if (!platform.secret.trim() && !savedSecret.get(appid)?.secret_set) {
      return t(
        'pages.dashboard.settings.platformSecretRequired',
        '新增平台必须填写 ClientSecret。',
      )
    }
    platforms.push({
      name: platform.name.trim(),
      appid,
      platform: platform.platform,
      secret: platform.secret.trim(),
    })
  }
  payload.selected_commands = commands
  payload.qq_platforms = platforms
  return ''
}

async function save(options: { sync?: boolean } = {}): Promise<void> {
  if (!form.value || !hasBackend.value) {
    return
  }
  const problem = validate()
  if (problem) {
    error.value = problem
    notice.value = ''
    return
  }

  saving.value = true
  error.value = ''
  notice.value = ''
  try {
    const next = await saveConfig(form.value)
    config.value = next
    form.value = toForm(next)
    notice.value = t('pages.dashboard.settings.saved', '配置已保存并生效。')
    if (options.sync) {
      // 同步入口在状态页，跳过去展示实时进度
      await startSync()
      await router.push({ name: 'status' })
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <v-container fluid class="qc-page pa-4 pa-md-6">
    <div class="qc-header">
      <div>
        <h1 class="qc-title">{{ t('pages.dashboard.settings.title', '设置') }}</h1>
        <p class="qc-subtitle">
          {{
            t(
              'pages.dashboard.settings.subtitle',
              '在这里维护写入 QQ 指令面板的内容与平台凭证，保存后立即生效。',
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
          {{ t('pages.dashboard.settings.reload', '重新载入') }}
        </v-btn>
        <v-btn
          variant="tonal"
          color="primary"
          :loading="saving"
          :disabled="!editable"
          @click="save({ sync: true })"
        >
          {{ t('pages.dashboard.settings.saveAndSync', '保存并同步') }}
        </v-btn>
        <v-btn
          variant="flat"
          color="primary"
          :loading="saving"
          :disabled="!editable"
          :prepend-icon="mdiContentSave"
          @click="save()"
        >
          {{ t('pages.dashboard.settings.save', '保存') }}
        </v-btn>
      </div>
    </div>

    <v-alert
      v-if="mockMode"
      type="info"
      variant="tonal"
      density="compact"
      class="mb-4"
      :prepend-icon="mdiInformationOutline"
    >
      {{
        t(
          'pages.dashboard.settings.mockHint',
          '本地开发环境：展示的是 mock 数据，不能保存配置。',
        )
      }}
    </v-alert>

    <v-alert
      v-if="error"
      type="error"
      variant="tonal"
      density="compact"
      class="mb-4"
      :prepend-icon="mdiAlertCircleOutline"
    >
      {{ error }}
    </v-alert>

    <v-alert
      v-if="notice"
      type="success"
      variant="tonal"
      density="compact"
      class="mb-4"
      :prepend-icon="mdiCheckCircleOutline"
    >
      {{ notice }}
    </v-alert>

    <v-progress-linear v-if="loading" indeterminate color="primary" class="mb-4" />

    <template v-if="form">
      <v-card class="qc-card mb-4" variant="outlined">
        <v-card-item class="px-5 pt-5">
          <v-card-title class="text-body-large">
            {{ t('pages.dashboard.settings.basicTitle', '基础配置') }}
          </v-card-title>
          <v-card-subtitle>
            {{
              t(
                'pages.dashboard.settings.basicSubtitle',
                '日志语言只影响插件日志；场景决定指令面板在哪些会话里生效。',
              )
            }}
          </v-card-subtitle>
        </v-card-item>
        <v-card-text class="px-5 pb-5 pt-3">
          <v-row>
            <v-col cols="12" md="4">
              <v-select
                v-model="form.language"
                :items="LANGUAGE_OPTIONS"
                :disabled="!editable"
                :label="t('pages.dashboard.settings.language', '日志语言')"
                variant="outlined"
                density="comfortable"
                hide-details
              />
            </v-col>
            <v-col cols="12" md="8">
              <v-select
                v-model="form.scenes"
                :items="sceneItems"
                :disabled="!editable"
                :label="t('pages.dashboard.settings.scenes', '生效场景')"
                variant="outlined"
                density="comfortable"
                multiple
                chips
                hide-details
              />
            </v-col>
          </v-row>
        </v-card-text>
      </v-card>

      <v-card class="qc-card mb-4" variant="outlined">
        <v-card-item class="px-5 pt-5">
          <v-card-title class="text-body-large">
            {{ t('pages.dashboard.settings.platformsTitle', 'QQ 平台凭证') }}
          </v-card-title>
          <v-card-subtitle>
            {{
              t(
                'pages.dashboard.settings.platformsSubtitle',
                '插件只能读取这里的凭证，AstrBot 平台适配器里的机器人信息不会同步过来；ClientSecret 留空表示沿用原值。',
              )
            }}
          </v-card-subtitle>
          <template #append>
            <v-btn
              variant="text"
              color="primary"
              :disabled="!editable"
              :prepend-icon="mdiPlus"
              @click="addPlatform"
            >
              {{ t('pages.dashboard.settings.addPlatform', '添加平台') }}
            </v-btn>
          </template>
        </v-card-item>

        <v-card-text class="px-5 pb-5 pt-3">
          <div v-if="!form.qq_platforms.length" class="qc-metric-note">
            {{
              t(
                'pages.dashboard.settings.noPlatforms',
                '还没有平台，先添加一个 appid + ClientSecret。',
              )
            }}
          </div>

          <div
            v-for="(platform, index) in form.qq_platforms"
            :key="index"
            class="qc-config-item mb-3"
          >
            <v-row>
              <v-col cols="12" md="3">
                <v-text-field
                  v-model="platform.name"
                  :disabled="!editable"
                  :label="t('pages.dashboard.settings.platformName', '备注（可选）')"
                  variant="outlined"
                  density="comfortable"
                  hide-details
                />
              </v-col>
              <v-col cols="12" md="3">
                <v-text-field
                  v-model="platform.appid"
                  :disabled="!editable"
                  label="AppID"
                  variant="outlined"
                  density="comfortable"
                  hide-details
                />
              </v-col>
              <v-col cols="12" md="3">
                <v-text-field
                  v-model="platform.secret"
                  :disabled="!editable"
                  type="password"
                  :label="t('pages.dashboard.settings.platformSecret', 'ClientSecret')"
                  :placeholder="
                    savedPlatform(platform.appid)?.secret_set
                      ? t('pages.dashboard.settings.secretKeep', '留空表示沿用原值')
                      : t('pages.dashboard.settings.secretRequired', '新增平台必须填写')
                  "
                  :hint="
                    savedPlatform(platform.appid)?.secret_masked
                      ? t('pages.dashboard.settings.secretSaved', '当前：{masked}').replace(
                          '{masked}',
                          savedPlatform(platform.appid)?.secret_masked ?? '',
                        )
                      : undefined
                  "
                  persistent-hint
                  variant="outlined"
                  density="comfortable"
                />
              </v-col>
              <v-col cols="12" md="2">
                <v-select
                  v-model="platform.platform"
                  :items="platformTypeItems"
                  :disabled="!editable"
                  :label="t('pages.dashboard.settings.platformType', '平台类型')"
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
                  :disabled="!editable"
                  :aria-label="t('pages.dashboard.settings.remove', '删除')"
                  @click="removePlatform(index)"
                >
                  <v-icon :icon="mdiTrashCanOutline" size="20" />
                </v-btn>
              </v-col>
            </v-row>
          </div>
        </v-card-text>
      </v-card>

      <v-card class="qc-card mb-4" variant="outlined">
        <v-card-item class="px-5 pt-5">
          <v-card-title class="text-body-large">
            {{ t('pages.dashboard.settings.commandsTitle', '指令条目') }}
          </v-card-title>
          <v-card-subtitle>
            {{
              t('pages.dashboard.settings.commandsSubtitle', '最多 {items} 条，指令名 ≤ {name} 字，描述 ≤ {desc} 字。')
                .replace('{items}', String(limits.items_max))
                .replace('{name}', String(limits.name_max))
                .replace('{desc}', String(limits.desc_max))
            }}
          </v-card-subtitle>
          <template #append>
            <v-btn
              variant="text"
              color="primary"
              :disabled="
                !editable || form.selected_commands.length >= limits.items_max
              "
              :prepend-icon="mdiPlus"
              @click="addCommand"
            >
              {{ t('pages.dashboard.settings.addCommand', '添加指令') }}
            </v-btn>
          </template>
        </v-card-item>

        <v-card-text class="px-5 pb-5 pt-3">
          <div v-if="!form.selected_commands.length" class="qc-metric-note">
            {{
              t(
                'pages.dashboard.settings.noCommands',
                '没有指令条目时，同步会清空本插件创建的面板。',
              )
            }}
          </div>

          <v-row v-for="(command, index) in form.selected_commands" :key="index">
            <v-col cols="12" md="5">
              <v-text-field
                v-model="command.name"
                :disabled="!editable"
                :maxlength="limits.name_max"
                :counter="limits.name_max"
                :label="t('pages.dashboard.settings.commandName', '指令名')"
                variant="outlined"
                density="comfortable"
                hide-details
              />
            </v-col>
            <v-col cols="12" md="6">
              <v-text-field
                v-model="command.desc"
                :disabled="!editable"
                :maxlength="limits.desc_max"
                :counter="limits.desc_max"
                :label="t('pages.dashboard.settings.commandDesc', '指令描述')"
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
                :disabled="!editable"
                :aria-label="t('pages.dashboard.settings.remove', '删除')"
                @click="removeCommand(index)"
              >
                <v-icon :icon="mdiTrashCanOutline" size="20" />
              </v-btn>
            </v-col>
          </v-row>
        </v-card-text>
      </v-card>
    </template>
  </v-container>
</template>
