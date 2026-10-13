import 'vuetify/styles'

import { createVuetify } from 'vuetify'
import { aliases, mdi } from 'vuetify/iconsets/mdi-svg'
import { THEME_DARK, THEME_LIGHT, darkTheme, lightTheme } from '../theme'

/**
 * Vuetify 实例。
 *
 * - 图标走 MDI 的 SVG 方案：按名从 @mdi/js 导入，只打包用到的图标，不引入
 *   整套图标字体。
 * - 主题用自带调色板（见 ../theme/index.ts）；卡片 16px 圆角不做 SCSS，
 *   直接在 ../styles/dashboard.css 里写。
 */
export const vuetify = createVuetify({
  display: {
    // 恢复 v3 断点：Vuetify 4 默认值整体偏小，宿主跑的是 Vuetify 3
    thresholds: { xs: 0, sm: 600, md: 960, lg: 1280, xl: 1920, xxl: 2560 },
    // 窄屏切换临时抽屉的界线，与宿主页面层的 959.98px 一致
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
