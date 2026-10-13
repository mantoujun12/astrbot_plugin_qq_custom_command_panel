<script setup lang="ts">
import { computed } from 'vue'
import { useBridge } from '../../composables/useBridge'
import type { PlatformStatus, ScenePanelStatus, SceneState } from '../../types/dashboard'

const props = defineProps<{ platform: PlatformStatus }>()

const { t } = useBridge()

const sourceLabel = computed(() =>
  t(
    `views.dashboard.status.source.${props.platform.source}`,
    props.platform.source === 'schema' ? '插件配置' : 'AstrBot 平台配置',
  ),
)

// scope 直接展示 QQ API 的原始取值 (c2c/group/...), 不做二次翻译
const STATE_META: Record<SceneState, { color: string; fallback: string }> = {
  synced: { color: 'success', fallback: '已同步' },
  missing: { color: 'warning', fallback: '线上缺失' },
  failed: { color: 'error', fallback: '查询失败' },
}

function stateColor(state: SceneState): string {
  return STATE_META[state].color
}

function stateLabel(state: SceneState): string {
  return t(`views.dashboard.status.state.${state}`, STATE_META[state].fallback)
}

function itemsSuffix(scene: ScenePanelStatus): string {
  if (scene.items_count === undefined) {
    return ''
  }
  return ` · ${scene.items_count} ${t('views.dashboard.status.itemsUnit', '条')}`
}
</script>

<template>
  <v-card variant="outlined" class="h-100">
    <v-card-item :subtitle="platform.platform">
      <v-card-title class="text-body-large">{{ platform.pf_id }}</v-card-title>
      <template #append>
        <v-chip size="small" variant="tonal">{{ sourceLabel }}</v-chip>
      </template>
    </v-card-item>

    <v-divider />

    <v-card-text>
      <div class="text-body-small text-medium-emphasis mb-2">appid: {{ platform.appid }}</div>

      <v-alert v-if="platform.error" type="error" variant="tonal" density="compact" class="mb-2">
        {{ platform.error }}
      </v-alert>

      <v-list density="compact" class="py-0">
        <v-list-item v-for="scene in platform.scenes" :key="scene.scope">
          <v-list-item-title>{{ scene.scope }}</v-list-item-title>
          <v-list-item-subtitle v-if="scene.panel_id">
            {{ scene.panel_id }}{{ itemsSuffix(scene) }}
          </v-list-item-subtitle>
          <template #append>
            <v-chip size="small" variant="tonal" :color="stateColor(scene.state)">
              {{ stateLabel(scene.state) }}
            </v-chip>
          </template>
        </v-list-item>
      </v-list>
    </v-card-text>
  </v-card>
</template>
