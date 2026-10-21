<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import {
  mdiAlertCircleOutline,
  mdiChevronDown,
  mdiChevronRight,
  mdiDeleteOutline,
  mdiMagnify,
  mdiPause,
  mdiPlay,
  mdiRefresh,
} from '@mdi/js'
import { getMockLogs, subscribeLogs } from '../api/logs'
import type { LogSubscription } from '../api/logs'
import { useBridge } from '../composables/useBridge'
import { LOG_LEVELS } from '../types/logs'
import type { LogEvent, LogLevel } from '../types/logs'

const MAX_VIEW_LOGS = 1000
const LEVEL_FALLBACKS: Record<LogLevel, string> = {
  debug: '调试',
  info: '信息',
  warning: '警告',
  error: '错误',
  critical: '严重',
}

const { ready, hasBackend, locale, t } = useBridge()
const logs = ref<LogEvent[]>([])
const pendingLogs = ref<LogEvent[]>([])
const frozenLogs = ref<LogEvent[]>([])
const paused = ref(false)
const search = ref('')
const selectedLevels = ref<LogLevel[]>([...LOG_LEVELS])
const autoScroll = ref(true)
const connection = ref<'connecting' | 'connected' | 'disconnected' | 'mock'>('connecting')
const connectionError = ref(false)
const lastSeq = ref(0)
const expandedSeqs = ref<Set<number>>(new Set())
const viewport = ref<HTMLElement | null>(null)

let subscription: LogSubscription | null = null
let generation = 0
let disposed = false

const sourceLogs = computed(() => (paused.value ? frozenLogs.value : logs.value))
const visibleLogs = computed(() => {
  const query = search.value.trim().toLocaleLowerCase(locale.value)
  const levels = new Set(selectedLevels.value)
  return sourceLogs.value.filter((entry) => {
    if (!levels.has(entry.level)) {
      return false
    }
    if (!query) {
      return true
    }
    const haystack = `${entry.message}\n${entry.traceback ?? ''}`.toLocaleLowerCase(locale.value)
    return haystack.includes(query)
  })
})
const allLevelsSelected = computed(() => selectedLevels.value.length === LOG_LEVELS.length)
const connectionLabel = computed(() => {
  if (connection.value === 'mock') {
    return t('pages.dashboard.logs.connection.mock', '本地模拟')
  }
  if (connection.value === 'connected') {
    return t('pages.dashboard.logs.connection.connected', '实时连接')
  }
  if (connection.value === 'connecting') {
    return t('pages.dashboard.logs.connection.connecting', '连接中')
  }
  return t('pages.dashboard.logs.connection.disconnected', '连接已断开')
})
const timeFormatter = computed(
  () =>
    new Intl.DateTimeFormat(locale.value, {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    }),
)

function levelLabel(level: LogLevel): string {
  return t(`pages.dashboard.logs.levels.${level}`, LEVEL_FALLBACKS[level])
}

function formatTimestamp(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : timeFormatter.value.format(date)
}

function toggleLevel(level: LogLevel): void {
  selectedLevels.value = selectedLevels.value.includes(level)
    ? selectedLevels.value.filter((item) => item !== level)
    : LOG_LEVELS.filter((item) => item === level || selectedLevels.value.includes(item))
}

function selectAllLevels(): void {
  selectedLevels.value = [...LOG_LEVELS]
}

function toggleDetails(seq: number): void {
  const next = new Set(expandedSeqs.value)
  if (next.has(seq)) {
    next.delete(seq)
  } else {
    next.add(seq)
  }
  expandedSeqs.value = next
}

function receive(entry: LogEvent): void {
  if (entry.seq <= lastSeq.value) {
    return
  }
  lastSeq.value = entry.seq
  if (paused.value) {
    pendingLogs.value = [...pendingLogs.value, entry].slice(-MAX_VIEW_LOGS)
    return
  }
  logs.value = [...logs.value, entry].slice(-MAX_VIEW_LOGS)
}

function togglePause(): void {
  if (paused.value) {
    logs.value = [...frozenLogs.value, ...pendingLogs.value].slice(-MAX_VIEW_LOGS)
    pendingLogs.value = []
    frozenLogs.value = []
    paused.value = false
    if (autoScroll.value) {
      void scrollToBottom()
    }
    return
  }
  frozenLogs.value = logs.value
  paused.value = true
}

function clearView(): void {
  logs.value = []
  frozenLogs.value = []
  pendingLogs.value = []
  expandedSeqs.value = new Set()
}

function loadMock(): void {
  generation += 1
  void stopSubscription()
  logs.value = getMockLogs()
  lastSeq.value = logs.value.at(-1)?.seq ?? 0
  connection.value = 'mock'
  connectionError.value = false
  if (autoScroll.value) {
    void scrollToBottom()
  }
}

async function stopSubscription(): Promise<void> {
  const current = subscription
  subscription = null
  if (!current) {
    return
  }
  try {
    await current.stop()
  } catch (err) {
    console.warn('[qq-command-panel] failed to stop log stream', err)
  }
}

async function connectLogs(since = 0): Promise<void> {
  if (!hasBackend.value) {
    loadMock()
    return
  }

  generation += 1
  const currentGeneration = generation
  await stopSubscription()
  connection.value = 'connecting'
  connectionError.value = false

  try {
    const next = await subscribeLogs({
      since,
      onOpen: () => {
        if (!disposed && currentGeneration === generation) {
          connection.value = 'connected'
          connectionError.value = false
        }
      },
      onEvent: (entry) => {
        if (!disposed && currentGeneration === generation) {
          receive(entry)
        }
      },
      onError: () => {
        if (disposed || currentGeneration !== generation) {
          return
        }
        connection.value = 'disconnected'
        connectionError.value = true
        void stopSubscription()
      },
    })
    if (disposed || currentGeneration !== generation || connectionError.value) {
      await next.stop()
      return
    }
    subscription = next
  } catch (err) {
    if (!disposed && currentGeneration === generation) {
      connection.value = 'disconnected'
      connectionError.value = true
    }
    console.warn('[qq-command-panel] failed to connect log stream', err)
  }
}

function retry(): void {
  void connectLogs(lastSeq.value)
}

function scrollToBottom(): Promise<void> {
  return nextTick(() => {
    const element = viewport.value
    if (element) {
      element.scrollTop = element.scrollHeight
    }
  })
}

function onScroll(): void {
  const element = viewport.value
  if (!element || paused.value) {
    return
  }
  const distance = element.scrollHeight - element.scrollTop - element.clientHeight
  autoScroll.value = distance <= 24
}

watch(
  [ready, hasBackend],
  ([isReady, backendReady]) => {
    if (!isReady) {
      return
    }
    if (backendReady) {
      void connectLogs(0)
    } else {
      loadMock()
    }
  },
  { immediate: true },
)

watch(
  [autoScroll, () => visibleLogs.value.length, () => visibleLogs.value.at(-1)?.seq],
  ([follow]) => {
    if (follow && !paused.value) {
      void scrollToBottom()
    }
  },
)

onBeforeUnmount(() => {
  disposed = true
  generation += 1
  void stopSubscription()
})
</script>

<template>
  <v-container fluid class="qc-page qc-logs-page pa-4 pa-md-6">
    <header class="qc-header">
      <div class="qc-header-main">
        <h1 class="qc-title">{{ t('pages.dashboard.logs.title', '日志') }}</h1>
        <p class="qc-subtitle">
          {{
            t(
              'pages.dashboard.logs.subtitle',
              '实时查看本插件输出的日志，最多保留当前进程最近 1000 条。',
            )
          }}
        </p>
      </div>
      <div class="qc-header-actions">
        <span
          class="qc-log-connection"
          :class="`qc-log-connection--${connection}`"
          role="status"
        >
          {{ connectionLabel }}
        </span>
      </div>
    </header>

    <v-alert
      v-if="!hasBackend && ready"
      class="qc-logs-alert"
      type="info"
      variant="tonal"
      density="comfortable"
    >
      {{
        t(
          'pages.dashboard.logs.mockHint',
          '本地开发环境：展示的是 mock 日志，未连接 AstrBot 后端。',
        )
      }}
    </v-alert>

    <v-alert
      v-if="connectionError"
      class="qc-logs-alert qc-logs-alert--error"
      type="error"
      variant="tonal"
      density="comfortable"
      :icon="mdiAlertCircleOutline"
    >
      {{ t('pages.dashboard.logs.connectionError', '日志流已中断，点击工具栏里的重新连接继续接收。') }}
    </v-alert>

    <v-card class="qc-card qc-logs-card" variant="outlined">
      <div class="qc-logs-toolbar">
        <v-text-field
          v-model="search"
          class="qc-log-search"
          :label="t('pages.dashboard.logs.search', '搜索日志')"
          :placeholder="t('pages.dashboard.logs.searchPlaceholder', '搜索消息或堆栈内容')"
          :prepend-inner-icon="mdiMagnify"
          density="compact"
          variant="outlined"
          hide-details
          clearable
        />

        <div
          class="qc-log-levels"
          role="group"
          :aria-label="t('pages.dashboard.logs.levelFilter', '日志等级过滤')"
        >
          <v-btn
            class="qc-log-level-all"
            :variant="allLevelsSelected ? 'flat' : 'tonal'"
            size="small"
            @click="selectAllLevels"
          >
            {{ t('pages.dashboard.logs.allLevels', '全部') }}
          </v-btn>
          <v-btn
            v-for="level in LOG_LEVELS"
            :key="level"
            class="qc-log-level"
            :class="[
              `qc-log-level--${level}`,
              { 'qc-log-level--active': selectedLevels.includes(level) },
            ]"
            :variant="selectedLevels.includes(level) ? 'flat' : 'text'"
            size="small"
            @click="toggleLevel(level)"
          >
            {{ levelLabel(level) }}
          </v-btn>
        </div>

        <div class="qc-log-actions">
          <v-btn
            class="qc-log-pause"
            :prepend-icon="paused ? mdiPlay : mdiPause"
            variant="tonal"
            size="small"
            @click="togglePause"
          >
            {{
              paused
                ? pendingLogs.length
                  ? t('pages.dashboard.logs.resumeWithPending', '继续（{count} 条待显示）')
                      .replace('{count}', String(pendingLogs.length))
                  : t('pages.dashboard.logs.resume', '继续')
                : t('pages.dashboard.logs.pause', '暂停')
            }}
          </v-btn>
          <v-switch
            v-model="autoScroll"
            class="qc-log-autoscroll"
            :label="t('pages.dashboard.logs.autoScroll', '自动滚动')"
            color="primary"
            density="compact"
            hide-details
          />
          <v-btn
            class="qc-log-clear"
            :icon="mdiDeleteOutline"
            :aria-label="t('pages.dashboard.logs.clear', '清空当前视图')"
            variant="text"
            size="small"
            @click="clearView"
          />
          <v-btn
            v-if="connection === 'disconnected'"
            class="qc-log-retry"
            :prepend-icon="mdiRefresh"
            variant="tonal"
            size="small"
            @click="retry"
          >
            {{ t('pages.dashboard.logs.retry', '重新连接') }}
          </v-btn>
        </div>
      </div>

      <div class="qc-logs-summary">
        <span>
          {{
            t('pages.dashboard.logs.count', '显示 {visible} / {total} 条')
              .replace('{visible}', String(visibleLogs.length))
              .replace('{total}', String(sourceLogs.length))
          }}
        </span>
        <span v-if="paused" class="qc-log-paused-note">
          {{ t('pages.dashboard.logs.paused', '已暂停显示，后台仍在收集日志。') }}
        </span>
      </div>

      <div ref="viewport" class="qc-log-viewport" @scroll.passive="onScroll">
        <div v-if="visibleLogs.length === 0" class="qc-logs-empty">
          <div class="qc-logs-empty-title">
            {{
              sourceLogs.length
                ? t('pages.dashboard.logs.noMatches', '没有符合筛选条件的日志。')
                : t('pages.dashboard.logs.empty', '还没有日志，等待插件输出。')
            }}
          </div>
          <div class="qc-logs-empty-hint">
            {{
              t(
                'pages.dashboard.logs.emptyHint',
                '同步面板、保存配置或切换日志语言后，新的插件日志会显示在这里。',
              )
            }}
          </div>
        </div>

        <article
          v-for="entry in visibleLogs"
          :key="entry.seq"
          class="qc-log-row"
          :class="`qc-log-row--${entry.level}`"
        >
          <time class="qc-log-time" :datetime="entry.timestamp">
            {{ formatTimestamp(entry.timestamp) }}
          </time>
          <span class="qc-log-level-badge" :class="`qc-log-level-badge--${entry.level}`">
            {{ levelLabel(entry.level) }}
          </span>
          <div class="qc-log-content">
            <div class="qc-log-message">{{ entry.message }}</div>
            <button
              v-if="entry.traceback"
              class="qc-log-detail-toggle"
              type="button"
              @click="toggleDetails(entry.seq)"
            >
              <v-icon
                :icon="expandedSeqs.has(entry.seq) ? mdiChevronDown : mdiChevronRight"
                size="16"
              />
              {{
                expandedSeqs.has(entry.seq)
                  ? t('pages.dashboard.logs.hideTraceback', '收起堆栈')
                  : t('pages.dashboard.logs.showTraceback', '展开堆栈')
              }}
            </button>
            <pre v-if="entry.traceback && expandedSeqs.has(entry.seq)" class="qc-log-traceback">{{
              entry.traceback
            }}</pre>
          </div>
        </article>
      </div>
    </v-card>
  </v-container>
</template>
