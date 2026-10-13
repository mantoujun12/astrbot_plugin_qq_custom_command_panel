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
 * 固定使用 hash 路由。
 *
 * AstrBot 按真实文件路径解析视图静态资源, history 路由刷新时后端没有对应
 * 文件会 404; 官方文档也建议 SPA 使用 hash routing (README 里同样有这条约定)。
 */
export const router = createRouter({
  history: createWebHashHistory(),
  routes,
})
