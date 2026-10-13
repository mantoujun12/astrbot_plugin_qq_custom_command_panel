import 'vuetify/styles'

import { createVuetify } from 'vuetify'
import { aliases, mdi } from 'vuetify/iconsets/mdi-svg'

/**
 * Vuetify 实例。
 * 图标走 MDI 的 SVG 方案 (vuetify/iconsets/mdi-svg): 内置别名已是内联路径,
 * 业务需要额外图标时从 @mdi/js 按名导入路径传给 icon, 只会打包用到的那些,
 * 不像 @mdi/font 那样把整套图标字体 (~3.6MB) 带进产物。
 */
export const vuetify = createVuetify({
  // 宿主 AstrBot dashboard 跑的是 Vuetify 3, 而 4 把默认断点整体调小了
  // (md 840 / lg 1145 / xl 1545 / xxl 2138)。这里恢复 v3 的阈值, 让插件页
  // 在同样的窗口宽度下与宿主表现一致: 只有断点变, 其它 v4 行为不动。
  display: {
    thresholds: { xs: 0, sm: 600, md: 960, lg: 1280, xl: 1920, xxl: 2560 },
  },
  icons: {
    defaultSet: 'mdi',
    aliases,
    sets: { mdi },
  },
})
