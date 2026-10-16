<script setup lang="ts">
import { computed } from 'vue'
import { useBridge } from '../../composables/useBridge'

const props = defineProps<{
  title: string
  value: number
  /** 上限（例如 QQ 侧 20 条指令 / 20 个面板）；传了就在备注里说明 */
  max?: number
  /** 覆盖默认备注 */
  note?: string
  icon?: string
  /** 到达上限时用 error 色高亮数值 */
  emphasizeAtLimit?: boolean
}>()

const { t } = useBridge()

const warn = computed(
  () => props.emphasizeAtLimit === true && props.max !== undefined && props.value >= props.max,
)

const noteText = computed(() => {
  if (props.note !== undefined) {
    return props.note
  }
  return props.max === undefined ? undefined : `${t('pages.dashboard.status.limit', '上限')} ${props.max}`
})
</script>

<!-- 指标卡用填充底（机器人卡与同步面板仍是描边），图标做右下角水印 -->
<template>
  <v-card class="qc-card qc-stat-card h-100" variant="flat">
    <v-card-text class="pa-5">
      <div class="qc-metric-label">{{ title }}</div>
      <div class="qc-metric-value" :class="{ 'text-error': warn }">{{ value }}</div>
      <div v-if="noteText" class="qc-metric-note">{{ noteText }}</div>
    </v-card-text>

    <span v-if="icon" class="qc-stat-watermark">
      <v-icon :icon="icon" size="64" />
    </span>
  </v-card>
</template>
