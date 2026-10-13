import 'vuetify/styles'

import { createVuetify } from 'vuetify'
import { aliases, mdi } from 'vuetify/iconsets/mdi-svg'
import { THEME_DARK, THEME_LIGHT, darkTheme, lightTheme } from '../theme'

/**
 * Vuetify 实例。
 *
 * - 图标走 MDI 的 SVG 方案 (vuetify/iconsets/mdi-svg): 内置别名已是内联路径,
 *   业务需要额外图标时从 @mdi/js 按名导入路径传给 icon, 只会打包用到的那些,
 *   不像 @mdi/font 那样把整套图标字体 (~3.6MB) 带进产物。
 * - 主题用自带的两个调色板, 色值对齐宿主 (见 ../theme/index.ts)。
 *   这里不设 VCard 的 rounded 默认值: Vuetify 的 lg 是 8px, 而宿主的卡片是
 *   16px (它靠 SCSS 的 $border-radius-root), 我们不做 SCSS, 所以在
 *   ../styles/dashboard.css 里直接给 16px。
 */
export const vuetify = createVuetify({
  display: {
    // 恢复 v3 断点: Vuetify 4 把默认值整体调小了 (md 840 / lg 1145 / xl 1545),
    // 宿主跑的是 Vuetify 3, 不还原的话两边在 840-960 这段表现不一致。
    thresholds: { xs: 0, sm: 600, md: 960, lg: 1280, xl: 1920, xxl: 2560 },
    // 窄屏切换临时抽屉的界线, 与宿主页面层的 959.98px 一致
    mobileBreakpoint: 'md',
  },
  theme: {
    defaultTheme: THEME_LIGHT,
    themes: {
      [THEME_LIGHT]: lightTheme,
      [THEME_DARK]: darkTheme,
    },
  },
  icons: {
    defaultSet: 'mdi',
    aliases,
    sets: { mdi },
  },
})
