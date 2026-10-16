<script setup lang="ts">
import { mdiProgressWrench } from '@mdi/js'
import { useBridge } from '../composables/useBridge'

const { t } = useBridge()
</script>

<template>
  <v-container fluid class="qc-page pa-4 pa-md-6">
    <div class="qc-header">
      <div>
        <h1 class="qc-title">{{ t('pages.dashboard.settings.title', '设置') }}</h1>
        <p class="qc-subtitle">
          {{ t('pages.dashboard.settings.subtitle', '插件级通用设置会集中在这里。') }}
        </p>
      </div>
    </div>

    <v-alert
      type="info"
      variant="tonal"
      class="qc-wip"
      :title="t('pages.dashboard.settings.wipTitle', '功能施工中')"
      :prepend-icon="mdiProgressWrench"
    >
      {{
        t(
          'pages.dashboard.settings.wipText',
          '这个页面还在建设中，后续会提供插件级通用设置。',
        )
      }}
    </v-alert>
  </v-container>
</template>
