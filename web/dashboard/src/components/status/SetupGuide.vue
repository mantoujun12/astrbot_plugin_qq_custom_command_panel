<script setup lang="ts">
defineProps<{
  title: string
  description: string
  icon?: string
}>()
</script>

<template>
  <v-empty-state :icon="icon" :title="title" :text="description" />
</template>
