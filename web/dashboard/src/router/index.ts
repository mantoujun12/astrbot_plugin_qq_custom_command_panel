import { createRouter, createWebHashHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  { path: '/', redirect: { name: 'status' } },
  {
    path: '/status',
    name: 'status',
    component: () => import('../views/StatusOverviewView.vue'),
  },
  {
    path: '/settings',
    name: 'settings',
    component: () => import('../views/SettingsView.vue'),
  },
  { path: '/:pathMatch(.*)*', redirect: { name: 'status' } },
]

/**
 * 固定使用 hash 路由：AstrBot 按真实文件路径解析视图资源，history 路由刷新会
 * 404；官方文档也建议 SPA 用 hash routing。
 */
export const router = createRouter({
  history: createWebHashHistory(),
  routes,
})
