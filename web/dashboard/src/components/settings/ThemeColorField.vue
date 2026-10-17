<script setup lang="ts">
import { isHexColor } from '../../theme'

const COLOR_SWATCHES: string[][] = [
  ['#3c96ca', '#2f86bd', '#00a6a6', '#00c853'],
  ['#ff9800', '#f44336', '#9c27b0', '#607d8b'],
]

const props = withDefaults(
  defineProps<{
    modelValue: string
    label: string
    hint: string
    invalidMessage: string
    disabled?: boolean
  }>(),
  {
    disabled: false,
  },
)

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

function colorRule(value: string): true | string {
  return isHexColor(value.trim()) ? true : props.invalidMessage
}

function updateFromPicker(value: unknown): void {
  if (typeof value === 'string' && isHexColor(value.trim())) {
    emit('update:modelValue', value.trim().toLowerCase())
  }
}
</script>

<template>
  <v-text-field
    :model-value="modelValue"
    :disabled="disabled"
    :label="label"
    :hint="hint"
    :rules="[colorRule]"
    variant="outlined"
    density="compact"
    persistent-hint
    @update:model-value="emit('update:modelValue', $event)"
  >
    <template #append-inner>
      <v-menu
        :close-on-content-click="false"
        :disabled="disabled"
        location="bottom end"
        :offset="[0, 8]"
      >
        <template #activator="{ props: activatorProps }">
          <button
            v-bind="activatorProps"
            class="qc-color-trigger"
            type="button"
            :disabled="disabled"
            :aria-label="label"
            :style="{ backgroundColor: modelValue }"
          />
        </template>

        <v-color-picker
          class="qc-color-picker-popover"
          :model-value="modelValue"
          mode="hex"
          :modes="['hex']"
          :canvas-height="150"
          :swatches="COLOR_SWATCHES"
          :swatches-max-height="120"
          show-swatches
          elevation="8"
          @update:model-value="updateFromPicker"
        />
      </v-menu>
    </template>
  </v-text-field>
</template>

<style scoped>
.qc-color-trigger {
  width: 28px;
  height: 28px;
  padding: 0;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.2);
  border-radius: 8px;
  background-clip: padding-box;
}

.qc-color-trigger:disabled {
  opacity: 0.45;
}
</style>
