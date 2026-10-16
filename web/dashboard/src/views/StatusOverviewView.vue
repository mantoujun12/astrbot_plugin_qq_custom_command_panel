<script setup lang="ts">
import { computed, ref, watch } from 'vue'
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
import { fetchStatus } from '../api/dashboard'
import PlatformStatusCard from '../components/status/PlatformStatusCard.vue'
import SetupGuide from '../components/status/SetupGuide.vue'
import StatCard from '../components/status/StatCard.vue'
import SyncPanel from '../components/status/SyncPanel.vue'
import { useBridge } from '../composables/useBridge'
import type { StatusResponse } from '../types/dashboard'

const { t, ready, hasBackend } = useBridge()

const status = ref<StatusResponse | null>(null)
const loading = ref(false)
const error = ref('')

// 请求代次：初始加载与手动刷新可能重叠，只允许最新一次请求写回状态，
// 否则先发的旧请求后返回会覆盖新数据，其 finally 也会误关 loading。
let loadSeq = 0

/**
 * 后端 /status 默认查询线上，属慢请求，因此只在进入页面和手动刷新时调用，不做
 * 轮询；refresh=true 时带 refresh=1 绕过后端短期缓存。
 */
async function load(options: { refresh?: boolean } = {}): Promise<void> {
  const seq = ++loadSeq
  loading.value = true
  error.value = ''
  try {
    const next = await fetchStatus(options)
    if (seq !== loadSeq) return
    status.value = next
  } catch (err) {
    if (seq !== loadSeq) return
    status.value = null
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    if (seq === loadSeq) loading.value = false
  }
}

// bridge 注入是异步的，必须等 ready 后再请求，否则真实环境会退回 mock；
// 一并监听 hasBackend，万一 bridge 在 ready 之后才补上也能重新拉取真实数据。
watch(
  [ready, hasBackend],
  ([isReady]) => {
    if (isReady) {
      void load()
    }
  },
  { immediate: true },
)

const hasPlatforms = computed(() => (status.value?.platforms.length ?? 0) > 0)
const hasItems = computed(() => (status.value?.items.count ?? 0) > 0)

// 本地 `pnpm dev` 没有 bridge，fetchStatus 会退回 mock；这里显式标注避免把假数据
// 当成真实状态，ready 之前不显示以防首屏闪烁。
const mockMode = computed(() => ready.value && !hasBackend.value)
</script>

<template>
  <v-container fluid class="qc-page pa-4 pa-md-6">
    <div class="qc-header">
      <div class="qc-header-main">
        <h1 class="qc-title">{{ t('pages.dashboard.status.title', '状态概览') }}</h1>
        <p class="qc-subtitle">
          {{
            t(
              'pages.dashboard.status.subtitle',
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
          @click="load({ refresh: true })"
        >
          {{ t('pages.dashboard.status.refresh', '刷新') }}
        </v-btn>
      </div>
    </div>

    <SyncPanel v-if="ready" class="mb-2" @finished="load({ refresh: true })" />

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
          'pages.dashboard.status.mockHint',
          '本地开发环境：展示的是 mock 数据，未连接 AstrBot 后端。',
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
      {{ t('pages.dashboard.status.loadFailed', '获取状态失败') }}: {{ error }}
    </v-alert>

    <template v-if="status">
      <v-row>
        <v-col cols="12" sm="6" lg="3">
          <StatCard
            :icon="mdiServerOutline"
            :title="t('pages.dashboard.status.cards.platforms', 'QQ 平台')"
            :value="status.platforms.length"
          />
        </v-col>
        <v-col cols="12" sm="6" lg="3">
          <StatCard
            :icon="mdiForumOutline"
            :title="t('pages.dashboard.status.cards.scenes', '生效场景')"
            :value="status.scenes.length"
            :note="status.scenes.join(' / ')"
          />
        </v-col>
        <v-col cols="12" sm="6" lg="3">
          <StatCard
            :icon="mdiFormatListBulleted"
            :title="t('pages.dashboard.status.cards.commands', '指令条目')"
            :value="status.items.count"
            :max="status.items.max"
            emphasize-at-limit
          />
        </v-col>
        <v-col cols="12" sm="6" lg="3">
          <StatCard
            :icon="mdiViewGridOutline"
            :title="t('pages.dashboard.status.cards.panels', '线上面板')"
            :value="status.panels.total"
            :max="status.panels.partial ? undefined : status.panels.max"
            :note="
              status.panels.partial
                ? t('pages.dashboard.status.panelsPartial', '部分场景查询失败，该值为下限')
                : undefined
            "
            emphasize-at-limit
          />
        </v-col>
      </v-row>

      <SetupGuide
        v-if="!hasPlatforms"
        :icon="mdiTuneVariant"
        :title="t('pages.dashboard.status.empty.platforms.title', '还没有可用的 QQ 平台')"
        :description="
          t(
            'pages.dashboard.status.empty.platforms.description',
            '到「兼容性」页填写 qq_platforms 的 appid / ClientSecret，或者到「机器人」页创建机器人。插件读不到 AstrBot 平台适配器里的机器人信息，凭证只能在这里配置。',
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
              'pages.dashboard.status.empty.commands.description',
              '尚未配置指令条目，同步会清空本插件创建的面板。请到「兼容性」或「机器人」页添加指令。',
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
