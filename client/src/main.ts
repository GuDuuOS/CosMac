import { createApp } from 'vue'
// 当前部署的是"真实可用版"LiveView（真登录/真频道/真消息/真 AI/富卡）。
// 演示稿完整 UI（App.vue + components + styles/tokens）保留在仓库，下一阶段逐块接真后切换回来。
import App from './views/LiveView.vue'
// 真实可用版只挂载 LiveView（演示稿的 App.vue + 各布局组件并未挂载）。
// 因此这里只加载「暖色 tokens + reset」两份全局样式，
// 不再 import 整个 styles/index.css —— 否则演示组件 CSS（.topbar / .composer-toolbar .send 等，
// 含旧蓝色 #154dc4）会与 LiveView 自带的同名 scoped 类名撞车、把暖色皮肤污染掉。
import './styles/tokens.css'
import './styles/reset.css'

createApp(App).mount('#app')
