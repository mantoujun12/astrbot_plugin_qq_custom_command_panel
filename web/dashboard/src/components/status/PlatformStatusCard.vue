<script setup lang="ts">
import { useBridge } from '../../composables/useBridge'
import type { PlatformStatus, ScenePanelStatus, SceneState } from '../../types/dashboard'

const props = defineProps<{ platform: PlatformStatus }>()

const { t } = useBridge()

// scope 直接展示 QQ API 的原始取值 (c2c/group/...)，不做二次翻译
const STATE_META: Record<SceneState, { color: string; fallback: string }> = {
  synced: { color: 'success', fallback: '已同步' },
  duplicate: { color: 'error', fallback: '重复面板' },
  missing: { color: 'warning', fallback: '线上缺失' },
  failed: { color: 'error', fallback: '查询失败' },
}

function stateColor(state: SceneState): string {
  return STATE_META[state].color
}

function stateLabel(state: SceneState): string {
  return t(`pages.dashboard.status.state.${state}`, STATE_META[state].fallback)
}

// 面板 ID 后面的条目数，没有面板时返回空串
function panelDetail(scene: ScenePanelStatus): string {
  if (!scene.panel_id) {
    return ''
  }
  if (scene.items_count === undefined) {
    return scene.panel_id
  }
  return `${scene.panel_id} · ${scene.items_count} ${t('pages.dashboard.status.itemsUnit', '条')}`
}
</script>

<template>
  <v-card class="qc-card h-100" variant="outlined">
    <v-card-item class="px-5 pt-5">
      <v-card-title class="text-body-large">{{ platform.pf_id }}</v-card-title>
      <v-card-subtitle>{{ platform.platform }}</v-card-subtitle>
    </v-card-item>

    <v-card-text class="px-5 pb-4 pt-3">
      <div class="qc-metric-note mb-2">appid: {{ platform.appid }}</div>

      <v-alert v-if="platform.error" type="error" variant="tonal" density="compact" class="mb-2">
        {{ platform.error }}
      </v-alert>

      <div v-for="scene in platform.scenes" :key="scene.scope" class="qc-list-row">
        <div class="qc-row-main">
          <div class="qc-list-label">{{ scene.scope }}</div>
          <div v-if="scene.panel_id" class="qc-metric-note">{{ panelDetail(scene) }}</div>
        </div>
        <v-chip size="small" variant="tonal" :color="stateColor(scene.state)">
          {{ stateLabel(scene.state) }}
        </v-chip>
      </div>
    </v-card-text>
  </v-card>
</template>
