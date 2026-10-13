/**
 * 插件后端数据访问层。
 *
 * 所有视图都只通过这里取数据, 不直接碰 bridge, 这样后端接口变动时只需改这一层。
 * endpoint 是插件内相对路径, 不含插件名前缀; bridge 会转发到
 * `/api/v1/plugins/extensions/<plugin_name>/<endpoint>`。
 *
 * 调用时机: bridge 由宿主异步注入, 视图必须等 `useBridge().ready` 之后再调用,
 * 否则这里会因为拿不到 bridge 而退回 mock (见 mock.ts), 真实环境就会误显示假数据。
 */

import { getBridge } from '../bridge'
import { MOCK_STATUS } from './mock'
import type { StatusResponse } from '../types/dashboard'

/** 与后端 register_web_api 的路由 `/<plugin_name>/status` 对应 */
const STATUS_ENDPOINT = 'status'

/**
 * 拉取状态概览。
 *
 * 后端该接口默认查询线上, 属于慢请求, 调用方需要自己处理 loading / 错误态。
 * 本地 `pnpm dev` 没有 bridge, 退回 mock 数据; 真实环境下 bridge 请求失败会
 * 直接抛出, 由视图展示错误, 不静默兜底 (否则用户会误以为线上真的没问题)。
 */
export async function fetchStatus(): Promise<StatusResponse> {
  const bridge = getBridge()
  if (!bridge) {
    return MOCK_STATUS
  }
  return (await bridge.apiGet(STATUS_ENDPOINT)) as StatusResponse
}
