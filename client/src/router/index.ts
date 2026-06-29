import { createRouter, createWebHashHistory, type RouteRecordRaw } from 'vue-router'
import LiveView from '@/views/LiveView.vue'
import AdminView from '@/views/AdminView.vue'

// 工作台内部导航用的占位组件：
// LiveView 是根组件、整页由它渲染，不走 <router-view>。这些路由仅用于让
// 工作台内部地址（/s/... 等）成为「合法路由」，否则 router.push 会命中下面的
// catch-all 被重定向回 /。组件本身永不渲染，给个空 render 即可。
// （早期演示稿的整页视图 DashboardView/TodoView/... 已删除——它们走 <router-view>、
//  而本应用根是 LiveView、router-view 从不渲染，故是死代码。）
const Blank = { render: () => null }

const routes: RouteRecordRaw[] = [
  { path: '/admin',     name: 'admin',     component: AdminView },
  // —— 工作台内部视图（地址同步用；component 不会被渲染）——
  { path: '/me',                component: Blank }, // 个人主页覆盖层
  { path: '/s/:space',          component: Blank },
  { path: '/s/:space/board',    component: Blank },
  { path: '/s/:space/tasks',    component: Blank },
  { path: '/s/:space/docs',     component: Blank },
  { path: '/s/:space/c/:room',  component: Blank },
  { path: '/live',      name: 'live',      component: LiveView },
  { path: '/',          name: 'dashboard', component: Blank },
  { path: '/:pathMatch(.*)*', redirect: { name: 'dashboard' } }
]

export const router = createRouter({
  history: createWebHashHistory(),
  routes
})
