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
  icons: {
    defaultSet: 'mdi',
    aliases,
    sets: { mdi },
  },
})
