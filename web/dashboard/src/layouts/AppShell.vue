<script setup lang="ts">
import { watch } from 'vue'
import { mdiMenu } from '@mdi/js'
import { useTheme } from 'vuetify'
import { fetchConfig } from '../api/dashboard'
import AppSidebar from '../components/nav/AppSidebar.vue'
import { useBridge } from '../composables/useBridge'
import { useAppShell } from './useAppShell'
import {
  THEME_DARK,
  THEME_LIGHT,
  applyThemeColors,
  resolveThemeColors,
} from '../theme'

const {
  mobile,
  isDark,
  t,
  drawer,
  railActive,
  toggleSidebar,
  onDrawerUpdate,
  toggleIcon,
  toggleLabel,
  title,
} = useAppShell()

const { ready, hasBackend } = useBridge()
const theme = useTheme()

watch(
  [ready, hasBackend],
  async ([isReady, backendReady]) => {
    if (!isReady || !backendReady) return
    try {
      applyThemeColors(theme, resolveThemeColors(await fetchConfig()))
    } catch (err) {
      console.warn('[qq-command-panel] failed to load theme colors', err)
    }
  },
  { immediate: true },
)
</script>

<template>
  <!-- 主题跟随宿主：v-app 的 theme prop 会提供到整棵子树 -->
  <v-app :theme="isDark ? THEME_DARK : THEME_LIGHT">
    <v-navigation-drawer
      class="qc-sidebar"
      :model-value="drawer"
      :permanent="!mobile"
      :temporary="mobile"
      :mobile-breakpoint="0"
      :rail="railActive"
      rail-width="56"
      width="245"
      location="left"
      floating
      elevation="0"
      @update:model-value="onDrawerUpdate"
    >
      <AppSidebar
        :rail="railActive"
        :title="title"
        :toggle-icon="toggleIcon"
        :toggle-label="toggleLabel"
        @toggle="toggleSidebar"
      />
    </v-navigation-drawer>

    <!-- 窄屏抽屉是临时的，收起后需要一个打开入口 + 标题 -->
    <v-app-bar v-if="mobile" flat border>
      <v-app-bar-nav-icon
        :icon="mdiMenu"
        :aria-label="t('pages.dashboard.nav.openDrawer', '打开侧边栏')"
        @click="drawer = true"
      />
      <v-app-bar-title>{{ title }}</v-app-bar-title>
    </v-app-bar>

    <v-main>
      <router-view />
    </v-main>
  </v-app>
</template>
