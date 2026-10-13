<script setup lang="ts">
import { mdiCogOutline } from '@mdi/js'
import { useBridge } from '../composables/useBridge'

const { t } = useBridge()

// 设置页尚未实现: 现有配置项都在插件配置 (schema) 页面, 这里先做占位说明,
// 列出用户需要去那边修改的字段名, 减少来回找。
const configFields = ['language', 'scenes', 'qq_platforms', 'selected_commands']
</script>

<template>
  <v-container fluid>
    <h2 class="text-headline-small mb-4">{{ t('views.dashboard.settings.title', '设置') }}</h2>

    <v-card variant="outlined">
      <v-card-item :prepend-icon="mdiCogOutline">
        <v-card-title class="text-body-large">
          {{ t('views.dashboard.settings.placeholderTitle', '配置仍在插件配置页') }}
        </v-card-title>
        <v-card-subtitle>
          {{
            t(
              'views.dashboard.settings.placeholder',
              '本页尚未实现。目前的配置项请到 AstrBot WebUI 的插件配置页修改, 改完重载插件生效。',
            )
          }}
        </v-card-subtitle>
      </v-card-item>

      <v-card-text>
        <div class="d-flex flex-wrap ga-4">
          <v-chip v-for="field in configFields" :key="field" size="small" variant="tonal">
            {{ field }}
          </v-chip>
        </div>
      </v-card-text>
    </v-card>
  </v-container>
</template>
