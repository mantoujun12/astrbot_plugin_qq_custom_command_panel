import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'
import vuetify from 'vite-plugin-vuetify'

// https://vite.dev/config/
export default defineConfig({
  // vuetify() 必须排在 vue() 之后，否则按需自动导入 Vuetify 组件/指令会失效。
  plugins: [vue(), vuetify({ autoImport: true })],
  // AstrBot 以受限 iframe 加载插件视图，静态资源挂在
  // /api/v1/plugins/<plugin>/views/<view>/_t/<token>/ 前缀下，
  // 只有相对路径能沿该前缀解析，绝对路径 /assets/... 会 404。
  base: './',
  build: {
    // 产物直接落到插件视图目录（pages 为 views 的兼容别名），
    // AstrBot 只扫描 <view>/index.html，因此 outDir 必须指向该目录本身。
    outDir: '../../pages/dashboard',
    emptyOutDir: true,
    rollupOptions: {
      output: {
        // 去掉文件名里的内容哈希：视图资源由 AstrBot 固定带
        // Cache-Control: no-store 下发，哈希起不到 cache busting 作用；
        // 固定文件名后重新 build 不会让已提交产物整体改名。
        entryFileNames: 'assets/[name].js',
        chunkFileNames: 'assets/[name].js',
        assetFileNames: 'assets/[name][extname]',
      },
    },
  },
})
