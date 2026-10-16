<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  mdiAlertCircleOutline,
  mdiCheckCircleOutline,
  mdiContentSave,
  mdiInformationOutline,
} from '@mdi/js'
import { fetchConfig, saveConfig } from '../api/dashboard'
import { useBridge } from '../composables/useBridge'
import type { PluginConfigResponse } from '../types/dashboard'

const { t, ready, hasBackend } = useBridge()

const LANGUAGE_OPTIONS: string[] = ['zh-CN', 'en-US']

const config = ref<PluginConfigResponse | null>(null)
const language = ref('zh-CN')
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const notice = ref('')

/** 本地开发没有 bridge，页面只展示 mock 并禁用编辑，不允许假装保存成功 */
const mockMode = computed(() => ready.value && !hasBackend.value)
const editable = computed(() => config.value !== null && hasBackend.value && !saving.value)

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const next = await fetchConfig()
    config.value = next
    language.value = next.language
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

/** 只提交本页负责的字段：生效场景、平台凭证与指令条目都归「兼容性」页，
    后端按字段合并，两页不会互相覆盖 */
async function save(): Promise<void> {
  if (!hasBackend.value || !config.value) {
    return
  }
  saving.value = true
  error.value = ''
  notice.value = ''
  try {
    const next = await saveConfig({ language: language.value })
    config.value = next
    language.value = next.language
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
        t('pages.dashboard.settings.mockHint', '本地开发环境：展示的是 mock 数据，不能保存配置。')
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
          <v-col cols="12" sm="6" md="4">
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
  </v-container>
</template>
