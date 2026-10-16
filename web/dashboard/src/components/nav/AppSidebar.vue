<script setup lang="ts">
import { mdiCogOutline, mdiHistory, mdiRobotOutline, mdiViewDashboardOutline } from '@mdi/js'
import NavItem from './NavItem.vue'
import { PLUGIN_VERSION } from '../../version'

defineProps<{
  /** 折叠成 rail 图标栏 */
  rail?: boolean
  /** 显示在 brand 行里的标题（视图标题）*/
  title: string
  toggleIcon: string
  toggleLabel: string
}>()

defineEmits<{ toggle: [] }>()

const mainItems = [
  {
    to: '/status',
    icon: mdiViewDashboardOutline,
    labelKey: 'pages.dashboard.nav.status',
    fallback: '状态概览',
  },
  {
    to: '/robots',
    icon: mdiRobotOutline,
    labelKey: 'pages.dashboard.nav.robots',
    fallback: '机器人',
  }
]

const bottomItems = [
  {
    to: '/compatibility',
    icon: mdiHistory,
    labelKey: 'pages.dashboard.nav.compatibility',
    fallback: '兼容性',
  },
  {
    to: '/settings',
    icon: mdiCogOutline,
    labelKey: 'pages.dashboard.nav.settings',
    fallback: '设置',
  },
]
</script>

<template>
  <div class="d-flex flex-column h-100">
    <div class="qc-sidebar-brand" :class="{ 'qc-sidebar-brand--rail': rail }">
      <div v-if="!rail" class="qc-sidebar-brand-title">{{ title }}</div>

      <v-btn
        class="qc-sidebar-brand-toggle"
        icon
        rounded="sm"
        variant="text"
        :ripple="false"
        :aria-label="toggleLabel"
        @click="$emit('toggle')"
      >
        <v-icon :icon="toggleIcon" size="20" />
      </v-btn>
    </div>

    <v-list nav density="comfortable">
      <NavItem v-for="item in mainItems" :key="item.to" v-bind="item" :rail="rail" />
    </v-list>

    <v-spacer />

    <v-list nav density="comfortable">
      <NavItem v-for="item in bottomItems" :key="item.to" v-bind="item" :rail="rail" />
    </v-list>

    <div v-if="!rail" class="qc-sidebar-version">{{ PLUGIN_VERSION }}</div>
  </div>
</template>
