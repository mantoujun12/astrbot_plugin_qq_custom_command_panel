<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { mdiClose, mdiMenu, mdiMenuClose, mdiMenuOpen } from '@mdi/js'
import { useDisplay } from 'vuetify'
import AppSidebar from '../components/nav/AppSidebar.vue'
import { useBridge } from '../composables/useBridge'
import { THEME_DARK, THEME_LIGHT } from '../theme'

const { mobile } = useDisplay()
const { context, isDark, t } = useBridge()

// 窄屏: 抽屉是临时抽屉, 开关的是它; 宽屏: 抽屉常驻, 开关的是折叠 (rail)
const drawer = ref(!mobile.value)
const rail = ref(false)

watch(mobile, (isMobile) => {
  drawer.value = !isMobile
})

const railActive = computed(() => !mobile.value && rail.value)

function toggleSidebar(): void {
  if (mobile.value) {
    drawer.value = !drawer.value
    return
  }
  rail.value = !rail.value
}

function onDrawerUpdate(value: boolean): void {
  // 宽屏时抽屉常驻, 只由我们自己的开关控制
  if (mobile.value) {
    drawer.value = value
  }
}

// 侧边栏 brand 行里的按钮: 宽屏折叠/展开, 窄屏关闭抽屉
const sidebarToggleIcon = computed(() => {
  if (mobile.value) return mdiClose
  return railActive.value ? mdiMenuOpen : mdiMenuClose
})

const sidebarToggleLabel = computed(() => {
  if (mobile.value) {
    return t('views.dashboard.nav.closeDrawer', '关闭侧边栏')
  }
  return railActive.value
    ? t('views.dashboard.nav.expand', '展开侧边栏')
    : t('views.dashboard.nav.collapse', '收起侧边栏')
})

// pageTitle 是视图标题 (views.dashboard.title), displayName 是插件名
const title = computed(
  () =>
    context.value?.pageTitle ??
    context.value?.displayName ??
    t('views.dashboard.title', '指令面板'),
)
</script>

<template>
  <!-- 主题跟随宿主: v-app 的 theme prop 会提供到整棵子树 -->
  <v-app :theme="isDark ? THEME_DARK : THEME_LIGHT">
    <v-navigation-drawer
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
        :toggle-icon="sidebarToggleIcon"
        :toggle-label="sidebarToggleLabel"
        @toggle="toggleSidebar"
      />
    </v-navigation-drawer>

    <!-- 窄屏时抽屉是临时的, 标题随抽屉收起, 所以这里保留一个打开入口和标题 -->
    <v-app-bar v-if="mobile" flat border>
      <v-app-bar-nav-icon
        :icon="mdiMenu"
        :aria-label="t('views.dashboard.nav.openDrawer', '打开侧边栏')"
        @click="drawer = true"
      />
      <v-app-bar-title>{{ title }}</v-app-bar-title>
    </v-app-bar>

    <v-main>
      <router-view />
    </v-main>
  </v-app>
</template>
