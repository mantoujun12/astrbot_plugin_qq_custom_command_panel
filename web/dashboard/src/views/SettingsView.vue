<script setup lang="ts">
import { mdiCogOutline } from '@mdi/js'
import { useBridge } from '../composables/useBridge'

const { t } = useBridge()

// 设置页占位：现有配置项都在插件配置 (schema) 页，这里只列出字段名方便定位
const configFields = ['language', 'scenes', 'qq_platforms', 'selected_commands']
</script>

<template>
  <v-container fluid class="qc-page pa-4 pa-md-6">
    <div class="qc-header">
      <div>
        <h1 class="qc-title">{{ t('views.dashboard.settings.title', '设置') }}</h1>
        <p class="qc-subtitle">
          {{
            t(
              'views.dashboard.settings.subtitle',
              '面板内容与平台凭证都在插件配置页维护。',
            )
          }}
        </p>
      </div>
    </div>

    <v-card class="qc-card" variant="outlined">
      <v-card-item class="px-5 pt-5" :prepend-icon="mdiCogOutline">
        <v-card-title class="text-body-large">
          {{ t('views.dashboard.settings.placeholderTitle', '配置仍在插件配置页') }}
        </v-card-title>
        <v-card-subtitle>
          {{
            t(
              'views.dashboard.settings.placeholder',
              '本页尚未实现。目前的配置项请到 AstrBot WebUI 的插件配置页修改，改完重载插件生效。',
            )
          }}
        </v-card-subtitle>
      </v-card-item>

      <v-card-text class="px-5 pb-4 pt-3">
        <div class="d-flex flex-wrap ga-4">
          <v-chip v-for="field in configFields" :key="field" size="small" variant="tonal">
            {{ field }}
          </v-chip>
        </div>
      </v-card-text>
    </v-card>
  </v-container>
</template>
