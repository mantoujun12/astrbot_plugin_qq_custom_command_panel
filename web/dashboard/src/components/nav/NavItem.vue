<script setup lang="ts">
import { computed } from 'vue'
import { useBridge } from '../../composables/useBridge'

const props = defineProps<{
  to: string
  icon: string
  labelKey: string
  fallback: string
  /** 折叠成 rail 时标题会被 Vuetify 隐藏，用 tooltip 补上 */
  rail?: boolean
}>()

const { t } = useBridge()

const label = computed(() => t(props.labelKey, props.fallback))
</script>

<template>
  <v-tooltip :disabled="!rail" location="right" :open-delay="0" :text="label">
    <template #activator="{ props: tooltipProps }">
      <v-list-item
        v-bind="tooltipProps"
        :to="to"
        rounded
        color="secondary"
        :aria-label="label"
        :style="{ '--indent-padding': '0px' }"
      >
        <template #prepend>
          <v-icon :icon="icon" size="18" />
        </template>
        <v-list-item-title>{{ label }}</v-list-item-title>
      </v-list-item>
    </template>
  </v-tooltip>
</template>
