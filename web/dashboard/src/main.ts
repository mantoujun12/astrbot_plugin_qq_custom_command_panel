import { createApp } from 'vue'
import App from './App.vue'
import { router } from './router'
import { vuetify } from './plugins/vuetify'
// 自带 Outfit 变量字体（只有拉丁子集，中文走系统 CJK 字体）。
// 注册名是 'Outfit Variable' 而不是 'Outfit'，字体栈写在 styles/dashboard.css 的 --v-font-body。
import '@fontsource-variable/outfit'
// 全局重置与页面层样式放在 Vuetify 样式之后导入，保证优先级符合预期
import './style.css'
import './styles/dashboard.css'

createApp(App).use(router).use(vuetify).mount('#app')
