<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  title: string
  value: number
  /** 上限（例如 QQ 侧 20 条指令 / 20 个面板） */
  max?: number
  /** 数值只是下限（例如部分场景查询失败），展示为 `5+`，具体原因由 note 说明 */
  partial?: boolean
  /** 数值下方的补充说明 */
  note?: string
  icon?: string
  /** 到达上限时用 error 色高亮数值 */
  emphasizeAtLimit?: boolean
}>()

const warn = computed(
  () =>
    props.partial !== true &&
    props.emphasizeAtLimit === true &&
    props.max !== undefined &&
    props.value > 0 &&
    props.value >= props.max,
)

const display = computed(() => (props.partial === true ? `${props.value}+` : `${props.value}`))
</script>

<!-- 指标卡用填充底（机器人卡与同步面板仍是描边），图标做右下角水印 -->
<template>
  <v-card class="qc-card qc-stat-card h-100" variant="flat">
    <v-card-text class="pa-5">
      <div class="qc-metric-label">{{ title }}</div>
      <div class="qc-metric-value" :class="{ 'text-error': warn }">{{ display }}</div>
      <div v-if="note" class="qc-metric-note">{{ note }}</div>
    </v-card-text>

    <span v-if="icon" class="qc-stat-watermark">
      <v-icon :icon="icon" size="64" />
    </span>
  </v-card>
</template>
