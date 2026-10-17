<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useTheme } from 'vuetify'
import {
  mdiAlertCircleOutline,
  mdiCheckCircleOutline,
  mdiContentSave,
  mdiGithub,
  mdiInformationOutline,
} from '@mdi/js'
import { fetchConfig, saveConfig } from '../api/dashboard'
import ThemeColorField from '../components/settings/ThemeColorField.vue'
import { useBridge } from '../composables/useBridge'
import {
  DEFAULT_THEME_COLORS,
  applyThemeColors,
  isHexColor,
  resolveThemeColors,
} from '../theme'
import type { PluginConfigResponse } from '../types/dashboard'
import { PLUGIN_VERSION } from '../version'

const { t, ready, hasBackend } = useBridge()
const theme = useTheme()

const LANGUAGE_OPTIONS: string[] = ['zh-CN', 'en-US']
const GITHUB_REPOSITORY_URL =
  'https://github.com/mantoujun12/astrbot_plugin_qq_custom_command_panel'

const config = ref<PluginConfigResponse | null>(null)
const language = ref('zh-CN')
const primaryColor = ref(DEFAULT_THEME_COLORS.primary)
const secondaryColor = ref(DEFAULT_THEME_COLORS.secondary)
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const notice = ref('')

/** 本地开发没有 bridge，可以编辑预览，但不允许假装保存成功 */
const mockMode = computed(() => ready.value && !hasBackend.value)
const colorsValid = computed(
  () => isHexColor(primaryColor.value.trim()) && isHexColor(secondaryColor.value.trim()),
)
const editable = computed(() => config.value !== null && !saving.value)
const canSave = computed(() => editable.value && hasBackend.value && colorsValid.value)

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const next = await fetchConfig()
    config.value = next
    language.value = next.language
    const colors = resolveThemeColors(next)
    primaryColor.value = colors.primary
    secondaryColor.value = colors.secondary
    applyThemeColors(theme, colors)
  } catch (err) {
    config.value = null
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

// mock 模式允许直接预览配色变化，但不显示保存成功，也不写回任何配置
watch([primaryColor, secondaryColor], ([primary, secondary]) => {
  if (!mockMode.value || !isHexColor(primary.trim()) || !isHexColor(secondary.trim())) {
    return
  }
  applyThemeColors(theme, {
    primary: primary.trim().toLowerCase(),
    secondary: secondary.trim().toLowerCase(),
  })
})

/**
 * 只提交本页负责的字段：生效场景、平台凭证与指令条目都归「兼容性」页，
 * 后端按字段合并，两页不会互相覆盖。
 */
async function save(): Promise<void> {
  if (!hasBackend.value || !config.value || !colorsValid.value) {
    return
  }
  saving.value = true
  error.value = ''
  notice.value = ''
  try {
    const next = await saveConfig({
      language: language.value,
      primary_color: primaryColor.value.trim().toLowerCase(),
      secondary_color: secondaryColor.value.trim().toLowerCase(),
    })
    config.value = next
    language.value = next.language
    const colors = resolveThemeColors(next)
    primaryColor.value = colors.primary
    secondaryColor.value = colors.secondary
    applyThemeColors(theme, colors)
    notice.value = t('pages.dashboard.settings.saved', '设置已保存并生效。')
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
      <div class="qc-header-main">
        <h1 class="qc-title">{{ t('pages.dashboard.settings.title', '设置') }}</h1>
        <p class="qc-subtitle">
          {{ t('pages.dashboard.settings.subtitle', '插件级通用设置会集中在这里。') }}
        </p>
      </div>

      <div class="qc-header-actions">
        <v-btn
          variant="text"
          color="primary"
          :loading="loading"
          :disabled="!ready || loading"
          @click="load"
        >
          {{ t('pages.dashboard.settings.reload', '重新载入') }}
        </v-btn>
        <v-btn
          variant="tonal"
          color="primary"
          :loading="saving"
          :disabled="!canSave"
          :prepend-icon="mdiContentSave"
          @click="save"
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
        t('pages.dashboard.settings.mockHint', '本地开发环境：可编辑预览，但不能保存配置。')
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

    <v-card v-if="config" class="qc-card mb-4" variant="outlined">
      <v-card-item class="px-5 pt-5">
        <v-card-title class="text-body-large">
          {{ t('pages.dashboard.settings.basicTitle', '基础配置') }}
        </v-card-title>
        <v-card-subtitle>
          {{ t('pages.dashboard.settings.basicSubtitle', '日志语言只影响插件日志。') }}
        </v-card-subtitle>
      </v-card-item>

      <v-card-text class="px-5 pb-5 pt-3">
        <v-row>
          <v-col cols="12" md="12">
            <v-select
              v-model="language"
              :items="LANGUAGE_OPTIONS"
              :disabled="!editable"
              :label="t('pages.dashboard.settings.language', '日志语言')"
              variant="outlined"
              density="compact"
              hide-details
            />
          </v-col>
        </v-row>
      </v-card-text>
    </v-card>

    <v-card v-if="config" class="qc-card mb-4" variant="outlined">
      <v-card-item class="px-5 pt-5">
        <v-card-title class="text-body-large">
          {{ t('pages.dashboard.settings.themeTitle', '主题配色') }}
        </v-card-title>
        <v-card-subtitle>
          {{
            t(
              'pages.dashboard.settings.themeSubtitle',
              '调整插件视图的主色和辅助色，保存后立即应用到浅色与深色主题。',
            )
          }}
        </v-card-subtitle>
      </v-card-item>

      <v-card-text class="px-5 pb-5 pt-3">
        <v-row>
          <v-col cols="12" md="6">
            <ThemeColorField
              v-model="primaryColor"
              :label="t('pages.dashboard.settings.primaryColor', '主色')"
              :hint="t('pages.dashboard.settings.colorHint', '使用 #RRGGBB 格式。')"
              :invalid-message="
                t('pages.dashboard.settings.colorInvalid', '请输入 #RRGGBB 格式的颜色。')
              "
              :disabled="!editable"
            />
          </v-col>
          <v-col cols="12" md="6">
            <ThemeColorField
              v-model="secondaryColor"
              :label="t('pages.dashboard.settings.secondaryColor', '辅助色')"
              :hint="t('pages.dashboard.settings.colorHint', '使用 #RRGGBB 格式。')"
              :invalid-message="
                t('pages.dashboard.settings.colorInvalid', '请输入 #RRGGBB 格式的颜色。')
              "
              :disabled="!editable"
            />
          </v-col>
        </v-row>
      </v-card-text>
    </v-card>

    <v-card v-if="config" class="qc-card qc-about-plugin mb-4" variant="outlined">
      <v-card-item class="px-5 pt-5">
        <v-card-title class="text-body-large">
          {{ t('pages.dashboard.settings.aboutTitle', '关于插件') }}
        </v-card-title>
        <v-card-subtitle>
          {{ t('pages.dashboard.settings.aboutSubtitle', '插件简介与功能概览。') }}
        </v-card-subtitle>
      </v-card-item>

      <v-card-text class="px-5 pb-5 pt-3">
        <div class="d-flex flex-wrap align-center justify-space-between gap-4">
          <div>
            <div class="text-body-1 font-weight-medium">
              {{ t('pages.dashboard.settings.aboutName', 'QQ 自定义指令面板') }}
            </div>
            <p class="text-body-2 text-medium-emphasis mt-1 mb-0">
              {{
                t(
                  'pages.dashboard.settings.aboutDescription',
                  '按机器人和场景维护指令条目，并将内容同步到 QQ 官方机器人指令面板。',
                )
              }}
            </p>
          </div>
          <v-chip class="qc-about-version" color="primary" variant="tonal">
            {{ PLUGIN_VERSION }}
          </v-chip>
        </div>
      </v-card-text>
      <v-card-text class="px-5 pb-5 pt-3">
        <div class="d-flex flex-wrap align-center justify-space-between gap-4">
          <div>
            <div class="text-body-1 font-weight-medium">
              {{ t('pages.dashboard.settings.githubTitle', 'GitHub 仓库') }}
            </div>
            <p class="text-body-2 text-medium-emphasis mt-1 mb-0">
              {{
                t(
                  'pages.dashboard.settings.githubDescription',
                  '查看项目源码、更新日志与问题反馈。',
                )
              }}
            </p>
          </div>
          <v-btn
            class="qc-github-link"
            :href="GITHUB_REPOSITORY_URL"
            target="_blank"
            rel="noopener noreferrer"
            color="primary"
            variant="tonal"
            :prepend-icon="mdiGithub"
          >
            {{ t('pages.dashboard.settings.githubAction', '访问 GitHub') }}
          </v-btn>
        </div>
      </v-card-text>
    </v-card>
  </v-container>
</template>
