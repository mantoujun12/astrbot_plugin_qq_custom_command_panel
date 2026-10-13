import { createApp } from 'vue'
import App from './App.vue'
import { router } from './router'
import { vuetify } from './plugins/vuetify'
// 全局重置与页面层样式放在 Vuetify 样式之后导入, 保证优先级符合预期
import './style.css'
import './styles/dashboard.css'

createApp(App).use(router).use(vuetify).mount('#app')
