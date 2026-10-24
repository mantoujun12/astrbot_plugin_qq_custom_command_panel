<script setup lang="ts">
import { computed, onBeforeUnmount, watch } from 'vue'
import {
  mdiAlertCircleOutline,
  mdiCheckCircleOutline,
  mdiInformationOutline,
  mdiSync,
} from '@mdi/js'
import { useBridge } from '../../composables/useBridge'
import { useSyncRun } from '../../composables/useSyncRun'
import type { SyncPlatformState } from '../../types/dashboard'

const emit = defineEmits<{ finished: [] }>()

const { t } = useBridge()
const { state, available, running, hasRun, start, attach, retry, stop } = useSyncRun()

// 进度条分母来自 start 事件；拿不到总数时用不确定进度条
const percent = computed(() =>
  state.value.platforms > 0
    ? Math.round((state.value.completed / state.value.platforms) * 100)
    : undefined,
)

const progressText = computed(() =>
  t('pages.dashboard.status.sync.progress', '进度 {completed}/{total}')
    .replace('{completed}', String(state.value.completed))
    .replace('{total}', String(state.value.platforms)),
)

const summaryText = computed(() =>
  t('pages.dashboard.status.sync.done', '同步完成：成功 {succeeded} 个平台，失败 {failed} 个')
    .replace('{succeeded}', String(state.value.succeeded))
    .replace('{failed}', String(state.value.failed)),
)

const duplicatePlatformNames = computed(() => {
  const counts = new Map<string, number>()
  for (const platform of state.value.platformStates) {
    if (platform.name) {
      counts.set(platform.name, (counts.get(platform.name) ?? 0) + 1)
    }
  }
  return new Set(
    [...counts.entries()]
      .filter(([, count]) => count > 1)
      .map(([name]) => name),
  )
})

function platformLabel(platform: SyncPlatformState): string {
  if (!platform.name) {
    return platform.appid || platform.pf_id
  }
  return duplicatePlatformNames.value.has(platform.name) && platform.appid
    ? `${platform.name} (${platform.appid})`
    : platform.name
}

function onStart(): void {
  void start({ onFinish: () => emit('finished') }).catch((error: unknown) => {
    // 触发失败（如后端未就绪）时保留在页面上提示，不改变状态机
    console.warn('[qq-command-panel] start sync failed', error)
  })
}

function onRetry(): void {
  retry(() => emit('finished'))
}

// bridge 是异步注入的，等它就绪后再接上当前进度；离开页面只退订，
// 后端任务继续跑，重新进入会回放事件缓冲。
watch(
  available,
  (isAvailable) => {
    if (isAvailable) {
      attach(() => emit('finished'))
    }
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  void stop()
})
</script>

<template>
  <v-card class="qc-card mb-4" variant="outlined">
    <v-card-item class="px-5 pt-5">
      <v-card-title class="text-body-large">
        {{ t('pages.dashboard.status.sync.title', '同步面板') }}
      </v-card-title>
      <v-card-subtitle>
        {{
          t(
            'pages.dashboard.status.sync.subtitle',
            '用当前配置把指令条目写入 QQ 面板，进度实时推送。',
          )
        }}
      </v-card-subtitle>
      <template #append>
        <div class="d-flex align-center ga-2">
          <v-btn
            v-if="state.status === 'failed' && state.error"
            variant="text"
            color="primary"
            @click="onRetry"
          >
            {{ t('pages.dashboard.status.sync.retry', '重试') }}
          </v-btn>
          <v-btn
            variant="tonal"
            color="primary"
            :disabled="!available"
            :loading="running"
            :prepend-icon="mdiSync"
            @click="onStart"
          >
            {{ t('pages.dashboard.status.sync.action', '同步面板') }}
          </v-btn>
        </div>
      </template>
    </v-card-item>

    <v-card-text class="px-5 pb-5 pt-3">
      <v-alert
        v-if="!available"
        type="info"
        variant="tonal"
        density="compact"
        class="mb-3"
        :prepend-icon="mdiInformationOutline"
      >
        {{
          t(
            'pages.dashboard.status.sync.disabledMock',
            '本地开发环境没有 AstrBot 后端，同步入口不可用。',
          )
        }}
      </v-alert>

      <template v-else>
        <div v-if="running || hasRun" class="mb-3">
          <div class="d-flex justify-space-between align-center mb-1">
            <span class="qc-metric-note">
              {{ running ? t('pages.dashboard.status.sync.running', '正在同步…') : progressText }}
            </span>
            <span v-if="state.platforms > 0" class="qc-metric-note">
              {{ state.completed }}/{{ state.platforms }}
            </span>
          </div>
          <v-progress-linear
            :model-value="percent"
            :indeterminate="percent === undefined && running"
            :color="state.status === 'failed' ? 'error' : 'primary'"
            height="8"
            rounded
          />
        </div>

        <div v-if="state.platformStates.length" class="d-flex flex-wrap ga-2 mb-3">
          <v-chip
            v-for="platform in state.platformStates"
            :key="platform.pf_id"
            size="small"
            variant="tonal"
            :color="platform.status === 'ok' ? 'success' : 'error'"
            :prepend-icon="platform.status === 'ok' ? mdiCheckCircleOutline : mdiAlertCircleOutline"
          >
            {{ platformLabel(platform) }}
          </v-chip>
        </div>

        <v-alert
          v-if="state.status === 'failed' && state.error"
          type="error"
          variant="tonal"
          density="compact"
          class="mb-3"
          :prepend-icon="mdiAlertCircleOutline"
        >
          {{ state.error }}
        </v-alert>

        <v-alert
          v-else-if="state.status === 'done'"
          type="success"
          variant="tonal"
          density="compact"
          class="mb-3"
          :prepend-icon="mdiCheckCircleOutline"
        >
          {{ summaryText }}
        </v-alert>

        <v-alert
          v-else-if="state.status === 'failed'"
          type="warning"
          variant="tonal"
          density="compact"
          class="mb-3"
          :prepend-icon="mdiAlertCircleOutline"
        >
          {{ summaryText }}
        </v-alert>

        <div v-if="state.messages.length" class="qc-sync-log">
          <div v-for="(line, index) in state.messages" :key="index" class="qc-sync-log-line">
            {{ line }}
          </div>
        </div>

        <div v-else-if="!hasRun" class="qc-metric-note">
          {{ t('pages.dashboard.status.sync.empty', '还没有同步记录。') }}
        </div>
      </template>
    </v-card-text>
  </v-card>
</template>
