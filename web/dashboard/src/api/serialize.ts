/**
 * 跨 iframe 传输前的纯数据快照。
 *
 * 视图里的 `ref` / `reactive` 状态是 Vue 的 Proxy，而结构化克隆算法无法克隆 Proxy：
 * 直接把响应式对象交给 bridge（宿主最终走 `window.parent.postMessage`）会抛
 * `DataCloneError`，表现为「保存配置后 failed to execute 'postMessage' ... could
 * not be cloned」。这里在数据层统一还原成纯对象，视图不必各自处理。
 *
 * 注意不能用 `structuredClone`：它同样克隆不了 Proxy。载荷只含 JSON 可表达的值
 * （字符串 / 数字 / 布尔 / 数组 / 对象），与 HTTP JSON 传输一致，`undefined` 字段
 * 会被丢弃，空值原样返回。
 */
export function toPlain<T>(value: T): T {
  if (value === null || value === undefined) {
    return value
  }
  return JSON.parse(JSON.stringify(value)) as T
}
