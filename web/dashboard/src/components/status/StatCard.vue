<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  title: string
  value: number
  /** 上限 (例如 QQ 侧 20 条指令 / 20 个面板), 传了才显示 N/M 和进度条 */
  max?: number
  subtitle?: string
  icon?: string
  /** 到达上限时用 error 色高亮 */
  emphasizeAtLimit?: boolean
}>()

const percent = computed(() =>
  props.max ? Math.min(100, Math.round((props.value / props.max) * 100)) : undefined,
)

const warn = computed(
  () => props.emphasizeAtLimit === true && props.max !== undefined && props.value >= props.max,
)
</script>

<template>
  <v-card variant="tonal" class="h-100">
    <v-card-text>
      <div class="d-flex align-center ga-4 mb-1">
        <v-icon v-if="icon" :icon="icon" size="small" class="text-medium-emphasis" />
        <span class="text-body-medium text-medium-emphasis">{{ title }}</span>
      </div>

      <div class="text-headline-small" :class="{ 'text-error': warn }">
        {{ value }}<template v-if="max !== undefined"
          ><span class="text-body-medium text-medium-emphasis"> / {{ max }}</span></template
        >
      </div>

      <div v-if="subtitle" class="text-body-small text-medium-emphasis">{{ subtitle }}</div>
    </v-card-text>

    <v-progress-linear
      v-if="percent !== undefined"
      :model-value="percent"
      :color="warn ? 'error' : 'primary'"
      height="4"
    />
  </v-card>
</template>
