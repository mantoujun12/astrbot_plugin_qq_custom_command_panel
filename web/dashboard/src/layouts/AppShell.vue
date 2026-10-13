<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
import AppSidebar from '../components/nav/AppSidebar.vue'
import { useBridge } from '../composables/useBridge'

const { mobile } = useDisplay()
const { context, isDark, t } = useBridge()

// 桌面默认展开, 窄屏默认收起 (抽屉在窄屏下自动切到 temporary 模式)
const drawer = ref(!mobile.value)
watch(mobile, (isMobile) => {
  drawer.value = !isMobile
})

const title = computed(
  () => context.value?.displayName ?? t('views.dashboard.title', '指令面板'),
)
</script>

<template>
  <!-- 主题跟随 AstrBot: v-app 的 theme prop 会提供到整棵子树 -->
  <v-app :theme="isDark ? 'dark' : 'light'">
    <v-navigation-drawer v-model="drawer" :permanent="!mobile">
      <AppSidebar />
    </v-navigation-drawer>

    <v-app-bar flat border>
      <v-app-bar-nav-icon v-if="mobile" @click="drawer = !drawer" />
      <v-app-bar-title>{{ title }}</v-app-bar-title>
    </v-app-bar>

    <v-main>
      <router-view />
    </v-main>
  </v-app>
</template>
