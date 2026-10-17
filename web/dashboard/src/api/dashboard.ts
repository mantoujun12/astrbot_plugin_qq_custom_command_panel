/**
 * 视图的数据访问层：视图只通过这里取数据，不直接碰 bridge。
 * endpoint 是插件内相对路径，bridge 会补上宿主的插件名前缀。
 *
 * bridge 由宿主异步注入，视图必须等 `useBridge().ready` 后再调用，否则本地会
 * 退回 mock（见 mock.ts）。真实请求失败会直接抛出，由调用方处理错误态。
 */

import { getBridge } from '../bridge'
import { MOCK_CONFIG, MOCK_STATUS } from './mock'
import { toPlain } from './serialize'
import type { PluginConfigResponse, PluginConfigSubmit, StatusResponse } from '../types/dashboard'

/** 对应后端 register_web_api 的路径 `/<plugin_name>/status` */
const STATUS_ENDPOINT = 'status'

/** 对应后端 `/<plugin_name>/config`（GET 读 / POST 写）*/
const CONFIG_ENDPOINT = 'config'

/**
 * 获取状态概览。后端该接口默认查询线上，属慢请求，调用方需处理 loading / 错误态。
 * `options.refresh` 为 true 时带 refresh=1，让后端跳过短期缓存。
 * 本地 `pnpm dev` 没有 bridge 时退回 mock；真实环境请求失败直接抛出，不静默兜底。
 */
export async function fetchStatus(options: { refresh?: boolean } = {}): Promise<StatusResponse> {
  const bridge = getBridge()
  if (!bridge) {
    return MOCK_STATUS
  }
  const params = options.refresh ? { refresh: 1 } : undefined
  return (await bridge.apiGet(STATUS_ENDPOINT, toPlain(params))) as StatusResponse
}

/** 读取插件配置（secret 只返回掩码）；本地无 bridge 时退回 mock */
export async function fetchConfig(): Promise<PluginConfigResponse> {
  const bridge = getBridge()
  if (!bridge) {
    return MOCK_CONFIG
  }
  return (await bridge.apiGet(CONFIG_ENDPOINT)) as PluginConfigResponse
}

/**
 * 写回插件配置，返回落库后的配置（同样只含掩码）。
 *
 * 载荷允许只带部分字段：后端按字段合并，缺省字段沿用已保存的值（见 core/config.py），
 * 所以「设置」页只提交通用设置，「兼容性」页只提交平台与指令条目。
 * 校验失败时后端返回错误响应，bridge 会把它转成 Error，调用方直接展示 message 即可。
 * 本地无 bridge 时抛错：不允许在没有后端的开发环境里伪造"保存成功"。
 * payload 允许是视图里的响应式对象，这里会先快照成纯数据（见 toPlain）。
 */
export async function saveConfig(payload: PluginConfigSubmit): Promise<PluginConfigResponse> {
  const bridge = getBridge()
  if (!bridge) {
    throw new Error('no backend: config saving is unavailable in local dev')
  }
  return (await bridge.apiPost(CONFIG_ENDPOINT, toPlain(payload))) as PluginConfigResponse
}
