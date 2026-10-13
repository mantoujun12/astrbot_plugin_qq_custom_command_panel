<script setup lang="ts">
import { mdiCogOutline, mdiViewDashboardOutline } from '@mdi/js'
import { useBridge } from '../../composables/useBridge'

const { t } = useBridge()

// 本次只落地这两个入口: 「状态概览」置顶, 「设置」压到抽屉底部
const mainItems = [
  {
    to: '/status',
    icon: mdiViewDashboardOutline,
    key: 'views.dashboard.nav.status',
    fallback: '状态概览',
  },
]

const bottomItems = [
  {
    to: '/settings',
    icon: mdiCogOutline,
    key: 'views.dashboard.nav.settings',
    fallback: '设置',
  },
]
</script>

<template>
  <div class="d-flex flex-column h-100">
    <v-list nav density="comfortable">
      <v-list-item
        v-for="item in mainItems"
        :key="item.to"
        :to="item.to"
        :prepend-icon="item.icon"
        :title="t(item.key, item.fallback)"
      />
    </v-list>

    <v-spacer />

    <v-list nav density="comfortable">
      <v-divider />
      <v-list-item
        v-for="item in bottomItems"
        :key="item.to"
        :to="item.to"
        :prepend-icon="item.icon"
        :title="t(item.key, item.fallback)"
      />
    </v-list>
  </div>
</template>
