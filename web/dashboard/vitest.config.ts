import { mergeConfig } from 'vite'
import { defineConfig } from 'vitest/config'
import viteConfig from './vite.config.ts'

export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: 'happy-dom',
      include: ['src/**/*.test.ts'],
      setupFiles: ['./src/test/setup.ts'],
      server: {
        deps: {
          inline: [/vuetify/],
        },
      },
      coverage: {
        provider: 'v8',
        reporter: ['text', 'lcov'],
        include: ['src/**/*.{ts,vue}'],
        exclude: ['src/**/*.test.ts', 'src/main.ts', 'src/test/**'],
        // 阈值取实测值往下 5 个百分点（实测：行 99.2 / 语句 98.2 / 函数 99.0 / 分支 92.0），
        // 留出跨环境正常浮动，同时给覆盖率回落下硬门。
        thresholds: {
          lines: 94,
          statements: 93,
          functions: 94,
          branches: 87,
        },
      },
    },
  }),
)
