import { version } from '../package.json'

/** 插件版本。package.json 里不带 v，这里补上，与 metadata.yaml / core/paths.py 的写法一致；
    这三处由 scripts/bump_version.py 同步，release.yml 会校验一致性。 */
export const PLUGIN_VERSION = `v${version}`
