<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  mdiAlertCircleOutline,
  mdiFormatListBulleted,
  mdiForumOutline,
  mdiInformationOutline,
  mdiRefresh,
  mdiServerOutline,
  mdiTuneVariant,
  mdiViewGridOutline,
} from '@mdi/js'
import { fetchStatus, hasBackend } from '../api/dashboard'
import PlatformStatusCard from '../components/status/PlatformStatusCard.vue'
import SetupGuide from '../components/status/SetupGuide.vue'
import StatCard from '../components/status/StatCard.vue'
import { useBridge } from '../composables/useBridge'
import type { StatusResponse } from '../types/dashboard'

const { t } = useBridge()

const status = ref<StatusResponse | null>(null)
const loading = ref(false)
const error = ref('')

/**
 * 后端 /status 默认查询线上 (每个平台 4 次 QQ API), 属于慢请求,
 * 因此只在进入页面和用户点刷新时调用, 不做轮询。
 */
async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    status.value = await fetchStatus()
  } catch (err) {
    status.value = null
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    loading.value = false
  }
}

onMounted(load)

const hasPlatforms = computed(() => (status.value?.platforms.length ?? 0) > 0)
const hasItems = computed(() => (status.value?.items.count ?? 0) > 0)

// 本地 `pnpm dev` 没有 bridge, fetchStatus 会退回 mock 数据, 这里显式标注,
// 避免把假数据当成真实线上状态
const mockMode = !hasBackend()
</script>

<template>
  <v-container fluid class="qc-page pa-4 pa-md-6">
    <div class="qc-header">
      <div>
        <h1 class="qc-title">{{ t('views.dashboard.status.title', '状态概览') }}</h1>
        <p class="qc-subtitle">
          {{
            t(
              'views.dashboard.status.subtitle',
              '查看各 QQ 平台与线上指令面板的当前状态。',
            )
          }}
        </p>
      </div>

      <div class="qc-header-actions">
        <v-btn
          variant="text"
          color="primary"
          :loading="loading"
          :prepend-icon="mdiRefresh"
          @click="load"
        >
          {{ t('views.dashboard.status.refresh', '刷新') }}
        </v-btn>
      </div>
    </div>

    <v-progress-linear v-if="loading" indeterminate color="primary" class="mb-4" />

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
          'views.dashboard.status.mockHint',
          '本地开发环境: 展示的是 mock 数据, 未连接 AstrBot 后端。',
        )
      }}
    </v-alert>

    <v-alert
      v-if="error"
      type="error"
      variant="tonal"
      class="mb-4"
      :prepend-icon="mdiAlertCircleOutline"
    >
      {{ t('views.dashboard.status.loadFailed', '获取状态失败') }}: {{ error }}
    </v-alert>

    <template v-if="status">
      <v-row>
        <v-col cols="12" sm="6" lg="3">
          <StatCard
            :icon="mdiServerOutline"
            :title="t('views.dashboard.status.cards.platforms', 'QQ 平台')"
            :value="status.platforms.length"
          />
        </v-col>
        <v-col cols="12" sm="6" lg="3">
          <StatCard
            :icon="mdiForumOutline"
            :title="t('views.dashboard.status.cards.scenes', '生效场景')"
            :value="status.scenes.length"
            :note="status.scenes.join(' / ')"
          />
        </v-col>
        <v-col cols="12" sm="6" lg="3">
          <StatCard
            :icon="mdiFormatListBulleted"
            :title="t('views.dashboard.status.cards.commands', '指令条目')"
            :value="status.items.count"
            :max="status.items.max"
            emphasize-at-limit
          />
        </v-col>
        <v-col cols="12" sm="6" lg="3">
          <StatCard
            :icon="mdiViewGridOutline"
            :title="t('views.dashboard.status.cards.panels', '线上面板')"
            :value="status.panels.total"
            :max="status.panels.max"
            emphasize-at-limit
          />
        </v-col>
      </v-row>

      <SetupGuide
        v-if="!hasPlatforms"
        :icon="mdiTuneVariant"
        :title="t('views.dashboard.status.empty.platforms.title', '还没有可用的 QQ 平台')"
        :description="
          t(
            'views.dashboard.status.empty.platforms.description',
            '在插件配置的 qq_platforms 里填写 appid / ClientSecret, 或在 AstrBot 平台配置里启用 qq_official 适配器。',
          )
        "
      />

      <template v-else>
        <v-alert
          v-if="!hasItems"
          type="warning"
          variant="tonal"
          class="mb-4"
          :prepend-icon="mdiAlertCircleOutline"
        >
          {{
            t(
              'views.dashboard.status.empty.commands.description',
              '尚未配置指令条目, 同步会清空本插件创建的面板。请在插件配置的 selected_commands 里添加条目。',
            )
          }}
        </v-alert>

        <v-row>
          <v-col
            v-for="platform in status.platforms"
            :key="platform.pf_id"
            cols="12"
            md="6"
            xl="4"
          >
            <PlatformStatusCard :platform="platform" />
          </v-col>
        </v-row>
      </template>
    </template>
  </v-container>
</template>
