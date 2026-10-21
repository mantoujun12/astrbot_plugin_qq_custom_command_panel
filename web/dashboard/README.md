# dashboard

插件 `astrbot_plugin_qq_custom_command_panel` 的 AstrBot WebUI 可视化视图（Vue 3 + TypeScript + Vite）。

## 前置要求

- **Node.js `^22.12.0 || >=24`** —— Vite 8 与 Vitest 5 的硬性要求，版本过低时 `pnpm build` / `pnpm test` 会在运行前直接失败。
  可在 `package.json` 的 `engines` 字段查看。
- **pnpm** —— lockfile 为 `lockfileVersion: 9.0`，pnpm 9+ 均可安装；CI 固定用 **pnpm 12** 构建与测试
  （见 `.github/workflows/ci-dashboard.yml` 与 `.github/workflows/codecov-dashboard.yml`）。

## 构建

```bash
pnpm install
pnpm build
```

`pnpm build` 会先跑 `vue-tsc -b` 做类型检查，再由 Vite 打包。构建产物**直接输出到仓库根目录的 `pages/dashboard/`**（见 `vite.config.ts` 的 `build.outDir`），不需要手动拷贝：

```
pages/dashboard/
├─ index.html          # 视图入口，AstrBot 只扫描该文件
└─ assets/
   ├─ index.js
   ├─ index.css
   └─ <chunk>.js / <chunk>.css   # 懒加载路由与共享 chunk，同样不带哈希
```

要点：

- `base: './'` 必须保留。AstrBot 以受限 iframe 加载视图，静态资源挂在带令牌的前缀
  `/api/v1/plugins/<插件>/views/<视图>/_t/<令牌>/` 下，只有相对路径能沿该前缀解析；绝对路径 `/assets/...` 会 404。
- `outDir` 指向 `../../pages/dashboard`，且需显式 `emptyOutDir: true`（Vite 默认不会清空项目根之外的目录）。
- 产物需要提交进仓库：AstrBot 不会执行 npm 构建，页面文件随插件一起分发。
- 产物文件名**不带内容哈希**（`rollupOptions.output.*FileNames`）。AstrBot 下发视图资源的响应头固定带
  `Cache-Control: no-store`（`astrbot/dashboard/services/plugin_page_service.py` 的 `build_security_headers`），
  浏览器不会缓存，哈希没有 cache busting 的作用；去掉后重新 build 的产物文件名稳定，仓库 diff 不会整体翻新。
- 请使用 hash 路由（如 `createWebHashHistory`）。静态资源按真实文件路径解析，history 路由刷新会 404。

## 开发

```bash
pnpm dev
```

本地 dev server 里**没有** AstrBot 注入的 bridge SDK（`window.AstrBotPluginView`），因此调用后端 API 的部分需要在真实 AstrBot 中调试：build 后在 WebUI 插件页重载插件，再打开视图；改静态资源通常刷新视图即可，新增/删除视图目录才需要重载插件。

视图标题与描述配置在仓库根目录的 `.astrbot-plugin/i18n/<locale>.json` 的 `pages.dashboard` 下，修改后需重载插件生效。**根键必须是 `pages`**：宿主按 `pages.<目录名>.title` 取视图标题，写成 `views` 时标题会回退成目录名 `dashboard`。

本地 dev 没有 bridge 时：状态页、设置页与日志页显示 mock 数据并显式标注；同步入口与保存按钮置灰，绝不伪造同步结果、实时日志或保存成功。

## 后端接口

视图内用相对路径调用（bridge 会补上 `/<plugin_name>/` 前缀），后端实现见 `core/web_api.py`：

| 路径 | 方法 | 用途 |
| --- | --- | --- |
| `status` | GET | 状态概览；`refresh=1` 绕过 5s 缓存 |
| `config` | GET | 读取配置，secret 只回掩码（`secret_masked` / `secret_set`）|
| `config` | POST | 校验并写回配置，保存后立即生效并失效状态缓存 |
| `sync` | POST | 触发一次同步，返回 `{started, busy}` |
| `sync/events` | GET | SSE 进度流，`since` 之后的 seq 会重放 |
| `logs/events` | GET | 插件日志 SSE，回放内存中最近 1000 条并持续推送新日志 |

要点：

- 同步任务跑在插件进程的后台（`core/sync_runner.py`），同一时间只允许一个任务；SSE 断开、刷新页面都不会中断任务。
- 事件是结构化 JSON（`start` / `platform` / `finish`）加本地化文本消息（`message`），页面据此渲染进度条、平台状态与日志。
- 宿主不会通知 SSE 流被关闭，前端收到 `finish` 事件后要自己 `unsubscribeSSE`。
- 日志流独立于同步流运行，只收集带 `[qq-command-panel]` 前缀的插件日志；暂停只冻结页面显示，后端仍继续收集。
- `config` 的 POST 载荷里 secret 留空表示沿用原值（页面只拿到掩码），新增平台则必须填 secret。

## 测试

```bash
pnpm test          # 单次跑完 vitest
pnpm test:coverage # 单次跑完 vitest 并统计 v8 覆盖率
pnpm test:report   # 单次跑完 vitest 并额外产出 test-report.junit.xml
pnpm test:codecov  # 覆盖率与 JUnit 报告一起产出，CI 用的就是它
```

要点：

- 配置在 `vitest.config.ts`，用 `mergeConfig` 复用 `vite.config.ts` 的插件；运行环境是 happy-dom，测试文件与被测代码同目录、命名 `*.test.ts`。
- `pnpm build` 里的 `vue-tsc` 会把 `src/**`、`vite.config.ts`、`vitest.config.ts` 一起做类型检查，所以测试文件里的类型错误会让构建失败。
- 覆盖率只统计 `src/**`，排除 `*.test.ts` 与入口 `src/main.ts`；`coverage/` 与 `test-report.junit.xml` 已在 `.gitignore` 中，不要提交。
- `pnpm test:codecov` 同时产出 `coverage/lcov.info`（覆盖率）与 `test-report.junit.xml`（JUnit），由 CI 的 `.github/workflows/codecov-dashboard.yml` 分两次以 flag `dashboard` 上传到 Codecov（覆盖率 + Test Analytics）；后端 Python 走 `.github/workflows/codecov-core.yml`，flag 为 `unittests`。前后端各自独立统计。
- 视图与 bridge 相关的部分只能靠单元测试兜住（受限 iframe、无 `localStorage`），交互行为仍要在真实 AstrBot 下验证。
