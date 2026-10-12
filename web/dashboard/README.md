# dashboard

插件 `astrbot_plugin_qq_custom_command_panel` 的 AstrBot WebUI 可视化视图（Vue 3 + TypeScript + Vite）。

## 前置要求

- **Node.js `^20.19.0 || >=22.12.0`** —— Vite 8 的硬性要求，版本过低时 `pnpm build` 会在打包前直接失败。可在
  `package.json` 的 `engines` 字段查看。
- **pnpm** —— lockfile 为 `lockfileVersion: 9.0`，pnpm 9+ 均可安装；CI 固定用 **pnpm 12** 构建
  （见 `.github/workflows/ci.yml`）。

## 构建

```bash
pnpm install
pnpm build
```

`pnpm build` 会先跑 `vue-tsc -b` 做类型检查，再由 Vite 打包。构建产物**直接输出到仓库根目录的 `pages/dashboard/`**（见 `vite.config.ts` 的 `build.outDir`），不需要手动拷贝：

```
pages/dashboard/
├─ index.html          # 视图入口, AstrBot 只扫描该文件
└─ assets/
   ├─ index-*.js
   └─ index-*.css
```

要点：

- `base: './'` 必须保留。AstrBot 以受限 iframe 加载视图，静态资源挂在带令牌的前缀
  `/api/v1/plugins/<插件>/views/<视图>/_t/<令牌>/` 下，只有相对路径能沿该前缀解析；绝对路径 `/assets/...` 会 404。
- `outDir` 指向 `../../pages/dashboard`，且需显式 `emptyOutDir: true`（Vite 默认不会清空项目根之外的目录）。
- 产物需要提交进仓库：AstrBot 不会执行 npm 构建，页面文件随插件一起分发。
- 请使用 hash 路由（如 `createWebHashHistory`）。静态资源按真实文件路径解析，history 路由刷新会 404。

## 开发

```bash
pnpm dev
```

本地 dev server 里**没有** AstrBot 注入的 bridge SDK（`window.AstrBotPluginView`），因此调用后端 API 的部分需要在真实 AstrBot 中调试：build 后在 WebUI 插件页重载插件，再打开视图；改静态资源通常刷新视图即可，新增/删除视图目录才需要重载插件。

视图标题与描述配置在仓库根目录的 `.astrbot-plugin/i18n/<locale>.json` 的 `views.dashboard` 下，修改后需重载插件生效。
