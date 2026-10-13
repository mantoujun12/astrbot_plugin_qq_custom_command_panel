/**
 * 插件后端数据访问层: 视图只通过这里取数据, 不直接碰 bridge。
 * endpoint 是插件内相对路径, 不含插件名前缀。
 *
 * bridge 由宿主异步注入, 视图必须等 `useBridge().ready` 后再调用, 否则会退回
 * mock (见 mock.ts), 真实环境会误显示假数据。
 */

import { getBridge } from '../bridge'
import { MOCK_STATUS } from './mock'
import type { StatusResponse } from '../types/dashboard'

/** 与后端 register_web_api 的路由 `/<plugin_name>/status` 对应 */
const STATUS_ENDPOINT = 'status'

/**
 * 拉取状态概览。后端该接口默认查询线上, 属慢请求, 调用方需处理 loading / 错误态;
 * `options.refresh` 为 true 时带 refresh=1 跳过后端短期缓存。
 * 本地 `pnpm dev` 没有 bridge 时退回 mock; 真实环境请求失败直接抛出, 不静默兜底。
 */
export async function fetchStatus(options: { refresh?: boolean } = {}): Promise<StatusResponse> {
  const bridge = getBridge()
  if (!bridge) {
    return MOCK_STATUS
  }
  const params = options.refresh ? { refresh: 1 } : undefined
  return (await bridge.apiGet(STATUS_ENDPOINT, params)) as StatusResponse
}
