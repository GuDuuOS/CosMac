<!--
  CosMac Star 真实客户端驾驶舱（按键布局 + 尺寸 1:1 对齐筱雨演示版 · 暖色皮肤 · 真实后端）
  --------------------------------------------------------------------
  布局/尺寸/按键全部按演示版那套 CSS（topbar/sidebar/channel/composer/plugin-rail/ai-panel）
  的精确数值还原：
    · 顶栏 46 高、品牌按键 36 高、搜索 360 绝对居中、升级会员渐变胶囊、ic-btn 32、头像 28
    · 三块「浮卡」：channels(250) / main(flex) / ai-panel(360) 都 圆角12 + margin8，灰底从缝里透出
    · WorkspaceRail 60 宽、ws-icon 40×40 圆角10、工具图标锚定栏底；PluginRail 40 宽、pr-icon 32 圆形
    · 频道条 active = 白底 + 左侧橙条（非深色填充）；分组头常规 13px
    · 频道头 50 高、★/ic-btn、成员堆叠；消息流为演示版扁平 Slack 风（头像+名+正文，非气泡）
    · Composer 工具条 tb-btn 28、发送键 28 圆形；右侧中枢 AI 面板 head 50、圆形发送
  真实能力（登录/频道/消息/中枢AI/退出/筛选/Markdown 工具）全部接 Synapse；
  纯装饰按钮（升级/提及/收藏/附件等）弹轻量 toast。配色沿用 CosMac 暖色（米白+橙+暖墨），走 tokens.css。
-->
<script setup lang="ts">
import { ref, computed, reactive, onMounted, onBeforeUnmount, nextTick } from 'vue'
import {
  login,
  restoreSession,
  logout,
  onUpdate,
  listRooms,
  listMessages,
  sendText,
  ensureBotDm,
  BOT_ID,
  type LiveRoom,
  type LiveMsg,
} from '@/matrix/client'
import { tenant } from '@/config/tenant'
import logoUrl from '@/assets/cosmac-logo.png'
// 顶栏品牌 logo 用 DEMO 的矢量胶囊（暖色：奶油+橙），22×32 天然比例不变形
import brandLogo from '@/assets/gudu-logo.svg'

const HS = 'https://hs.cosmac.cc'

// ── 登录态 ──────────────────────────────────────────────
const user = ref('admin')
const password = ref('')
const loggedIn = ref(false)
const me = ref('')
const error = ref('')
const loading = ref(false)

// ── 频道 / 消息 ─────────────────────────────────────────
const rooms = ref<LiveRoom[]>([])
const currentRoom = ref('')
const msgs = ref<LiveMsg[]>([])
const draft = ref('')
const taRef = ref<HTMLTextAreaElement>()
const filterText = ref('')

// ── 右侧"中枢 AI"面板（= 与主 AI 的私聊）────────────────
const aiRoom = ref('')
const aiMsgs = ref<LiveMsg[]>([])
const aiDraft = ref('')
const aiOpen = ref(true)

// ── 纯界面态（折叠分组 / 下拉菜单 / 专注模式 / 收藏星）────
const channelsOpen = ref(true)
const dmsOpen = ref(true)
const appMenuOpen = ref(false)
const userMenuOpen = ref(false)
const focused = ref(false)
const fav = ref(false)
const rootEl = ref<HTMLElement | null>(null)

const currentName = computed(
  () => rooms.value.find((r) => r.id === currentRoom.value)?.name || '',
)

// 频道列表按关键词本地筛选（演示版"查找频道"输入框，真实生效）
const filteredRooms = computed(() =>
  rooms.value.filter((r) => !filterText.value || r.name.includes(filterText.value)),
)

function isBot(s: string) {
  return s === BOT_ID
}
function fmtTime(ts: number) {
  const d = new Date(ts)
  const h = String(d.getHours()).padStart(2, '0')
  const m = String(d.getMinutes()).padStart(2, '0')
  return `${h}:${m}`
}

// ── 轻量 toast ──────────────────────────────────────────
interface Toast { id: number; title: string; msg?: string }
const toasts = ref<Toast[]>([])
let toastSeq = 0
function toast(title: string, msg?: string) {
  const id = ++toastSeq
  toasts.value.push({ id, title, msg })
  setTimeout(() => {
    toasts.value = toasts.value.filter((t) => t.id !== id)
  }, 2600)
}

// ── 真实数据刷新 ────────────────────────────────────────
function refresh() {
  rooms.value = listRooms().filter((r) => r.id !== aiRoom.value)
  if (currentRoom.value) msgs.value = listMessages(currentRoom.value)
  if (aiRoom.value) aiMsgs.value = listMessages(aiRoom.value)
}

async function afterLogin(uid: string) {
  me.value = uid
  loggedIn.value = true
  onUpdate(refresh)
  try {
    aiRoom.value = await ensureBotDm()
  } catch (e) {
    /* 没建成私聊也不影响频道功能 */
  }
  refresh()
}

async function doLogin() {
  error.value = ''
  loading.value = true
  try {
    await afterLogin(await login(HS, user.value.trim(), password.value))
  } catch (e: any) {
    error.value = e?.message || String(e)
  } finally {
    loading.value = false
  }
}

function openRoom(id: string) {
  currentRoom.value = id
  msgs.value = listMessages(id)
}

async function send() {
  const t = draft.value.trim()
  if (!t || !currentRoom.value) return
  draft.value = ''
  await sendText(currentRoom.value, t)
  setTimeout(refresh, 400)
}

async function aiSend() {
  const t = aiDraft.value.trim()
  if (!t || !aiRoom.value) return
  aiDraft.value = ''
  await sendText(aiRoom.value, t)
  setTimeout(refresh, 400)
}

function doLogout() {
  logout()
  loggedIn.value = false
  rooms.value = []
  msgs.value = []
  currentRoom.value = ''
  aiRoom.value = ''
  aiMsgs.value = []
  userMenuOpen.value = false
}

function openAiPanel() {
  aiOpen.value = true
}

function initials(name: string) {
  return name.replace(/^@/, '').slice(0, 1).toUpperCase()
}
function isMe(s: string) {
  return s === me.value
}

// ── Composer Markdown 工具条（在 draft 文本上真实生效）────
function wrap(before: string, after: string, placeholder: string) {
  const ta = taRef.value
  if (!ta) return
  const start = ta.selectionStart
  const end = ta.selectionEnd
  const value = draft.value
  const inner = value.slice(start, end) || placeholder
  draft.value = value.slice(0, start) + before + inner + after + value.slice(end)
  const innerStart = start + before.length
  const innerEnd = innerStart + inner.length
  nextTick(() => {
    ta.focus()
    ta.setSelectionRange(innerStart, innerEnd)
  })
}
function prefixLine(prefix: string) {
  const ta = taRef.value
  if (!ta) return
  const start = ta.selectionStart
  const value = draft.value
  const lineStart = value.lastIndexOf('\n', start - 1) + 1
  draft.value = value.slice(0, lineStart) + prefix + value.slice(lineStart)
  const caret = start + prefix.length
  nextTick(() => {
    ta.focus()
    ta.setSelectionRange(caret, caret)
  })
}
function insertText(s: string) {
  const ta = taRef.value
  if (!ta) return
  const start = ta.selectionStart
  const value = draft.value
  draft.value = value.slice(0, start) + s + value.slice(ta.selectionEnd)
  const caret = start + s.length
  nextTick(() => {
    ta.focus()
    ta.setSelectionRange(caret, caret)
  })
}
const tb = reactive({
  bold: () => wrap('**', '**', '加粗文字'),
  italic: () => wrap('*', '*', '斜体文字'),
  strike: () => wrap('~~', '~~', '删除线文字'),
  heading: () => prefixLine('## '),
  link: () => wrap('[', '](url)', '链接文字'),
  code: () => wrap('`', '`', '代码'),
  quote: () => prefixLine('> '),
  ul: () => prefixLine('- '),
  at: () => { insertText('@'); toast('@ 提及', '可 @ 成员或 @ 某个 Agent') },
})

// ── 顶栏装饰按钮 / 应用切换 / 工作区工具 ──────────────────
function onSearch() { toast('🔍 全局搜索', '搜索频道 / 消息 / 文件（演示）') }
function onUpgrade() { toast('✦ 升级会员', 'Pro 版解锁全部 Agent 与无限额度（演示）') }
function onMentions() { toast('@ 提及', '这里会列出所有 @ 你的消息（演示）') }
function onBookmarks() { toast('🔖 收藏夹', '你收藏的消息 / 文件（演示）') }
function onSettings() { toast('⚙ 设置', '账号 / 通知 / 外观设置（演示）'); userMenuOpen.value = false }
function onMarket() { toast('🛒 AI Agent 商城', '挑选并安装智能体 / 插件（演示）'); appMenuOpen.value = false }
function onCli() { toast('▸ CLI', '命令行控制台（演示）'); appMenuOpen.value = false }
function onProfile() { toast('🏠 个人主页', '你的主页 / 名片（演示）'); appMenuOpen.value = false }
function onAddWorkspace() { toast('＋ 新建工作区', '创建一个新的部门 / 工作区（演示）') }
function onAddChannel() { toast('＋ 新建频道', '在当前工作区创建频道（演示）') }
function onInvite() { toast('＋ 邀请成员', '通过链接或 @ 邀请成员加入（演示）') }
function onFilter() { toast('筛选频道', '按未读 / 私密过滤（演示，可直接在右侧输入框查找）') }
function onMembers() { toast('👥 成员 · 技能 · 知识库 · 规则', '管理当前频道（演示）') }
function onAttach() { toast('📎 附件', '支持图片 / 视频 / 文档（演示）') }
function onEmoji() { toast('😊 表情') }

function onDocClick(e: MouseEvent) {
  if (!rootEl.value) return
  if (!(e.target as HTMLElement)?.closest?.('.tas-wrap')) appMenuOpen.value = false
  if (!(e.target as HTMLElement)?.closest?.('.um-wrap')) userMenuOpen.value = false
}

onMounted(async () => {
  document.addEventListener('click', onDocClick)
  loading.value = true
  try {
    const uid = await restoreSession()
    if (uid) await afterLogin(uid)
  } finally {
    loading.value = false
  }
})
onBeforeUnmount(() => document.removeEventListener('click', onDocClick))
</script>

<template>
  <!-- ════════════════ 登录页 ════════════════ -->
  <div v-if="!loggedIn" class="login">
    <div class="login-card">
      <div class="brand login-brand"><img :src="logoUrl" class="brand-logo" alt="" />CosMac<span>Star</span></div>
      <input v-model="user" placeholder="用户名（如 admin）" />
      <input v-model="password" type="password" placeholder="密码" @keyup.enter="doLogin" />
      <button class="login-btn" :disabled="loading" @click="doLogin">{{ loading ? '登录中…' : '登录' }}</button>
      <p class="err" v-if="error">登录失败：{{ error }}</p>
      <p class="hint">连接后端 {{ HS }}</p>
    </div>
  </div>

  <!-- ════════════════ 驾驶舱 ════════════════ -->
  <div v-else ref="rootEl" class="shell">
    <!-- ───────── 顶栏 ───────── -->
    <header class="topbar">
      <!-- 左：品牌 / 九宫格应用切换器 -->
      <div class="tas-wrap">
        <button class="top-brand-btn" :class="{ open: appMenuOpen }" @click.stop="appMenuOpen = !appMenuOpen">
          <svg class="apps-ic" width="18" height="18" viewBox="0 0 18 18" fill="currentColor">
            <circle cx="3" cy="3" r="1.6" /><circle cx="9" cy="3" r="1.6" /><circle cx="15" cy="3" r="1.6" />
            <circle cx="3" cy="9" r="1.6" /><circle cx="9" cy="9" r="1.6" /><circle cx="15" cy="9" r="1.6" />
            <circle cx="3" cy="15" r="1.6" /><circle cx="9" cy="15" r="1.6" /><circle cx="15" cy="15" r="1.6" />
          </svg>
          <img :src="brandLogo" alt="" class="logo" />
          <span class="product-name">CosMac Star<span class="product-x">X</span>{{ tenant.topbarSuffix }}</span>
        </button>
        <div v-if="appMenuOpen" class="tas-pop" @click.stop>
          <button class="tas-item active"><span class="tas-ic accent">▣</span><span class="tas-label">Channels</span><span class="tas-check">✓</span></button>
          <div class="tas-sep" />
          <button class="tas-item" @click="onMarket"><span class="tas-ic">🛒</span><span class="tas-label">AI Agent 商城</span></button>
          <button class="tas-item" @click="onCli"><span class="tas-ic">▸</span><span class="tas-label">CLI</span></button>
          <button class="tas-item" @click="appMenuOpen = false"><span class="tas-ic">▭</span><span class="tas-label">系统控制台</span></button>
          <button class="tas-item" @click="appMenuOpen = false"><span class="tas-ic">🧩</span><span class="tas-label">集成</span></button>
          <div class="tas-sep" />
          <button class="tas-item" @click="onProfile"><span class="tas-ic">🏠</span><span class="tas-label">个人主页</span></button>
        </div>
      </div>

      <!-- 中：搜索（绝对居中）-->
      <div class="top-mid"></div>
      <div class="search" role="button" tabindex="0" @click="onSearch">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8" /><path d="m21 21-4.3-4.3" /></svg>
        <span>搜索</span>
      </div>

      <!-- 右：升级 / 提及 / 收藏 / 设置 / 中枢AI开关 / 用户菜单 -->
      <div class="top-right">
        <button class="top-upgrade" @click="onUpgrade">✦ 升级会员 ✦</button>
        <button class="ic-btn" title="提及" @click="onMentions">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4" /><path d="M16 8v5a3 3 0 0 0 6 0v-1a10 10 0 1 0-4 8" /></svg>
        </button>
        <button class="ic-btn" title="收藏" @click="onBookmarks">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m19 21-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2Z" /></svg>
        </button>
        <button class="ic-btn" title="设置" @click="onSettings">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></svg>
        </button>
        <button class="ic-btn ai-toggle" :class="{ active: aiOpen }" :title="aiOpen ? '收起中枢 AI' : '展开中枢 AI'" @click="aiOpen = !aiOpen">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l1.9 5.6L19.5 9.5 13.9 11.4 12 17l-1.9-5.6L4.5 9.5l5.6-1.9L12 2z" /></svg>
        </button>
        <div class="um-wrap">
          <button class="user-chip" :class="{ open: userMenuOpen }" @click.stop="userMenuOpen = !userMenuOpen">
            <span class="avatar">{{ initials(me) }}</span>
            <span class="online-dot" />
          </button>
          <div v-if="userMenuOpen" class="um-pop" @click.stop>
            <div class="um-head">
              <span class="um-ava">{{ initials(me) }}</span>
              <div class="um-id">
                <div class="um-name">{{ me }}</div>
                <div class="um-handle">已连接 {{ HS }} · <span class="um-online">在线</span></div>
              </div>
            </div>
            <div class="um-sep" />
            <button class="um-item" @click="onProfile"><span class="um-ic">👤</span>个人资料</button>
            <button class="um-item" @click="onSettings"><span class="um-ic">🔒</span>我的权限</button>
            <button class="um-item" @click="onSettings"><span class="um-ic">🔔</span>通知偏好</button>
            <div class="um-sep" />
            <button class="um-item danger" @click="doLogout"><span class="um-ic">⎋</span>退出登录</button>
          </div>
        </div>
      </div>
    </header>

    <!-- ───────── 主体（浮卡式三栏 + 两侧竖栏）───────── -->
    <div class="body" :class="{ focused }">
      <!-- 最左：工作区竖栏 -->
      <nav v-if="!focused" class="ws-rail">
        <div class="ws-icon active" :title="tenant.hqTitle">{{ tenant.hqLabel }}</div>
        <div class="ws-icon plus" title="新建工作区" @click="onAddWorkspace">+</div>
        <div class="ws-sep" />
        <div class="ws-icon ws-tool" title="AI Agent 商城" @click="onMarket">🛒</div>
        <div class="ws-icon ws-tool" title="CLI" @click="onCli">▸</div>
        <div class="ws-icon ws-tool" title="个人主页" @click="onProfile">🏠</div>
      </nav>

      <!-- 左：频道侧栏（浮卡）-->
      <aside v-if="!focused" class="channels">
        <div class="cs-ws-head">
          <button class="cs-ws-name" :title="tenant.hqTitle">
            <span class="name">{{ tenant.hqTitle }}</span>
            <svg class="chev" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6" /></svg>
          </button>
          <button class="cs-add" title="添加" @click="onAddChannel">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M12 5v14" /></svg>
          </button>
        </div>

        <div class="cs-filter">
          <button class="cs-filter-funnel" title="筛选" @click="onFilter">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18l-7 9v6l-4-2v-4z" /></svg>
          </button>
          <input class="cs-filter-input" v-model="filterText" placeholder="查找频道" />
        </div>

        <div class="cs-list">
          <!-- 频道 group（真实房间）-->
          <div class="cs-group">
            <button class="cs-group-head" @click="channelsOpen = !channelsOpen">
              <svg class="caret" :class="{ open: channelsOpen }" width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><path d="M9 6 15 12 9 18z" /></svg>
              <span>频道</span>
            </button>
            <template v-if="channelsOpen">
              <div
                v-for="r in filteredRooms"
                :key="r.id"
                class="cs-item ch-row"
                :class="{ active: r.id === currentRoom }"
                @click="openRoom(r.id)"
              >
                <span class="cs-ic">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10" /><path d="M2 12h20" /><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10" /></svg>
                </span>
                <span class="cs-label">{{ r.name }}</span>
              </div>
              <p v-if="!filteredRooms.length" class="cs-empty">还没有频道</p>
              <div class="cs-item cs-add-row" @click="onAddChannel">
                <span class="cs-ic-box"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M12 5v14" /></svg></span>
                <span class="cs-label">添加频道</span>
              </div>
            </template>
          </div>

          <!-- 私信 group（中枢 AI）-->
          <div class="cs-group">
            <button class="cs-group-head" @click="dmsOpen = !dmsOpen">
              <svg class="caret" :class="{ open: dmsOpen }" width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><path d="M9 6 15 12 9 18z" /></svg>
              <span>私信</span>
            </button>
            <template v-if="dmsOpen">
              <div class="cs-item dm-row" :class="{ active: aiOpen }" @click="openAiPanel">
                <span class="cs-dm-av bot">智<span class="dot-online" /></span>
                <span class="cs-label">中枢 AI</span>
              </div>
              <div class="cs-item cs-add-row" @click="onInvite">
                <span class="cs-ic-box"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M12 5v14" /></svg></span>
                <span class="cs-label">邀请成员</span>
              </div>
            </template>
          </div>
        </div>
      </aside>

      <!-- 中：频道（浮卡）-->
      <main class="main">
        <div v-if="currentRoom" class="ch-header">
          <button class="ch-fav" :class="{ active: fav }" :title="fav ? '取消收藏' : '收藏'" @click="fav = !fav">
            <svg width="16" height="16" viewBox="0 0 24 24" :fill="fav ? 'currentColor' : 'none'" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" /></svg>
          </button>
          <div class="title"><span class="hash">#</span>{{ currentName }}</div>
          <div class="ch-actions">
            <button class="ch-members-btn" title="管理成员 · 技能 · 知识库 · 规则" @click="onMembers">
              <div class="ava-stack"><div class="a">{{ initials(me) }}</div><div class="a bot">智</div></div>
              <span class="ch-members-count">2</span>
            </button>
            <button class="ch-ic-btn" :class="{ active: focused }" :title="focused ? '退出专注' : '专注模式'" @click="focused = !focused">
              <svg v-if="focused" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7V3h4M21 7V3h-4M3 17v4h4M21 17v4h-4" /></svg>
              <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="18" x="3" y="3" rx="2" /><path d="M12 3v18M3 12h18" /></svg>
            </button>
            <button class="ch-ic-btn" :class="{ active: aiOpen }" :title="aiOpen ? '关闭中枢 AI' : '打开中枢 AI'" @click="aiOpen = !aiOpen">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10" /><path d="M12 16v-4M12 8h.01" /></svg>
            </button>
          </div>
        </div>

        <!-- 消息流（演示版扁平 Slack 风）-->
        <div class="stream">
          <div v-for="m in msgs" :key="m.id" class="msg" :class="{ bot: isBot(m.sender), me: isMe(m.sender) }">
            <div class="ava">{{ isBot(m.sender) ? '智' : initials(m.senderName) }}</div>
            <div class="msg-body">
              <div class="head">
                <span class="name">{{ m.senderName }}</span>
                <span class="role" :class="isBot(m.sender) ? 'bot' : 'human'">{{ isBot(m.sender) ? 'AI' : '成员' }}</span>
                <span class="time">{{ fmtTime(m.ts) }}</span>
              </div>
              <div v-if="!m.card" class="text">{{ m.body }}</div>
              <div v-else class="rich info">
                <div class="r-head"><span class="t">🗂 {{ m.card.title }}</span></div>
                <p v-if="m.card.subtitle">{{ m.card.subtitle }}</p>
                <div class="kv">
                  <template v-for="(rw, i) in (m.card.rows || [])" :key="i">
                    <span class="k">{{ rw.task }}</span>
                    <span class="v" :class="rw.type">{{ rw.owner }}</span>
                  </template>
                </div>
              </div>
            </div>
          </div>
          <p v-if="currentRoom && !msgs.length" class="hint pad">这个频道还没有消息</p>
          <p v-if="!currentRoom" class="hint pad">← 选一个频道开始</p>
        </div>

        <!-- Composer -->
        <div v-if="currentRoom" class="composer">
          <div class="composer-box">
            <textarea
              ref="taRef"
              v-model="draft"
              :placeholder="`发送到 #${currentName}；叫主 AI 试：CosMac 建专班 测试专班`"
              @keydown.enter.exact.prevent="send"
            />
            <div class="composer-toolbar">
              <div class="tb-left">
                <button class="tb-btn tb-ai" title="AI 辅助" @click="aiOpen = true"><svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l1.9 5.6L19.5 9.5 13.9 11.4 12 17l-1.9-5.6L4.5 9.5l5.6-1.9L12 2z" /></svg><span>AI</span></button>
                <span class="tb-sep" />
                <button class="tb-btn" title="加粗" @click="tb.bold"><b>B</b></button>
                <button class="tb-btn" title="斜体" @click="tb.italic"><i>I</i></button>
                <button class="tb-btn" title="删除线" @click="tb.strike"><s>S</s></button>
                <button class="tb-btn tb-heading" title="标题" @click="tb.heading">H</button>
                <span class="tb-sep" />
                <button class="tb-btn" title="链接" @click="tb.link"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" /><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" /></svg></button>
                <button class="tb-btn" title="代码" @click="tb.code"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6" /><polyline points="8 6 2 12 8 18" /></svg></button>
                <button class="tb-btn" title="引用" @click="tb.quote"><svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M7 7v6H4V9c0-1.1.9-2 2-2h1Zm10 0v6h-3V9c0-1.1.9-2 2-2h1Z" /></svg></button>
                <button class="tb-btn" title="无序列表" @click="tb.ul"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="8" y1="6" x2="21" y2="6" /><line x1="8" y1="12" x2="21" y2="12" /><line x1="8" y1="18" x2="21" y2="18" /><line x1="3" y1="6" x2="3.01" y2="6" /><line x1="3" y1="12" x2="3.01" y2="12" /><line x1="3" y1="18" x2="3.01" y2="18" /></svg></button>
                <button class="tb-btn" title="@提及" @click="tb.at"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4" /><path d="M16 8v5a3 3 0 0 0 6 0v-1a10 10 0 1 0-4 8" /></svg></button>
              </div>
              <div class="tb-right">
                <button class="tb-btn" title="附件" @click="onAttach"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l8.57-8.57A4 4 0 1 1 17.93 8.8L9.41 17.32a2 2 0 0 1-2.83-2.83l8.49-8.48" /></svg></button>
                <button class="tb-btn" title="表情" @click="onEmoji"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10" /><path d="M8 14s1.5 2 4 2 4-2 4-2M9 9h.01M15 9h.01" /></svg></button>
                <button class="send" :disabled="!draft.trim()" title="发送 (Enter)" @click="send"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M22 2 11 13" /><path d="M22 2 15 22l-4-9-9-4Z" /></svg></button>
              </div>
            </div>
          </div>
        </div>
      </main>

      <!-- 右：中枢 AI 面板（浮卡）-->
      <aside class="ai-panel" v-if="aiOpen && !focused">
        <div class="ai-head">
          <span class="ai-dot" />
          <span class="ai-title">中枢 AI · CosMac Star</span>
          <div class="ai-head-actions">
            <button class="ai-ic-btn" title="收起" @click="aiOpen = false">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M18 6 6 18M6 6l12 12" /></svg>
            </button>
          </div>
        </div>
        <div class="ai-body">
          <div v-for="m in aiMsgs" :key="m.id" class="ai-msg" :class="{ mine: isMe(m.sender) }">
            <div v-if="!m.card" class="ai-bubble">{{ m.body }}</div>
            <div v-else class="rich info">
              <div class="r-head"><span class="t">🗂 {{ m.card.title }}</span></div>
              <p v-if="m.card.subtitle">{{ m.card.subtitle }}</p>
              <div class="kv">
                <template v-for="(rw, i) in (m.card.rows || [])" :key="i">
                  <span class="k">{{ rw.task }}</span>
                  <span class="v" :class="rw.type">{{ rw.owner }}</span>
                </template>
              </div>
            </div>
          </div>
          <p v-if="!aiMsgs.length" class="hint pad">跟中枢 AI 说句话，比如"帮我建个爆款专班"</p>
        </div>
        <div class="ai-composer">
          <div class="ai-input-box">
            <input v-model="aiDraft" placeholder="一句话下达目标…" @keyup.enter="aiSend" />
            <div class="ai-toolbar">
              <div class="ai-tb-left">
                <button class="ai-tb-btn" title="附件" @click="onAttach"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l8.57-8.57A4 4 0 1 1 17.93 8.8L9.41 17.32a2 2 0 0 1-2.83-2.83l8.49-8.48" /></svg></button>
              </div>
              <button class="ai-send-ic" :disabled="!aiDraft.trim()" @click="aiSend"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M22 2 11 13" /><path d="M22 2 15 22l-4-9-9-4Z" /></svg></button>
            </div>
          </div>
        </div>
      </aside>

      <!-- 最右：插件竖栏 -->
      <nav v-if="!focused" class="plugin-rail">
        <div class="pr-list">
          <div class="pr-icon active" title="中枢 AI" @click="aiOpen = !aiOpen">智</div>
          <div class="pr-icon plus" title="添加插件" @click="onMarket">+</div>
        </div>
        <div class="pr-divider" />
        <div class="pr-icon assets" title="资产 · 自定义配置" @click="onMarket">◈</div>
        <div class="pr-icon gear" title="插件商城" @click="onMarket">⚙</div>
      </nav>
    </div>

    <!-- toast -->
    <div class="toast-host">
      <div v-for="t in toasts" :key="t.id" class="toast">
        <div class="toast-title">{{ t.title }}</div>
        <div v-if="t.msg" class="toast-msg">{{ t.msg }}</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
* { box-sizing: border-box; }

/* 填充式控件的暖色（替代演示版的中性灰 rgb(202,204,207)）*/
.shell { --chip: #e7ddcd; --chip-hover: #ddd0bb; }

/* ════════ 登录页 ════════ */
.login { height: 100vh; display: flex; align-items: center; justify-content: center; background: linear-gradient(180deg, var(--bg-panel), var(--bg-soft)); font-family: var(--font-body); }
.login-card { width: 320px; display: flex; flex-direction: column; gap: 12px; padding: 28px; background: #fff; border: 1px solid var(--border); border-radius: 16px; box-shadow: 0 20px 60px rgba(0,0,0,.08); }
.login-brand { font-weight: 800; font-size: 22px; color: var(--text); display: inline-flex; align-items: center; gap: 8px; }
.login-brand span { color: var(--accent); margin-left: 4px; }
.brand-logo { width: 26px; height: 26px; object-fit: contain; border-radius: 6px; }
.login-card input { padding: 11px 13px; border: 1px solid var(--border); border-radius: 10px; font-size: 14px; }
.login-btn { padding: 11px; border: 0; border-radius: 10px; background: var(--action); color: #fff; font-size: 14px; cursor: pointer; }
.err { color: var(--danger); font-size: 13px; }
.hint { color: var(--text-3); font-size: 12px; }
.hint.pad { padding: 16px; }

/* ════════ 外壳 ════════ */
.shell { height: 100vh; display: flex; flex-direction: column; font-family: var(--font-body); color: var(--text); background: var(--bg-soft); }

/* ──── 顶栏（46 高，无下边框）──── */
.topbar { height: var(--topbar-h); display: flex; align-items: center; padding: 0 12px; gap: 10px; background: var(--bg-soft); position: relative; z-index: 20; flex-shrink: 0; }
.tas-wrap { position: relative; display: inline-flex; flex-shrink: 0; }
.top-brand-btn { display: inline-flex; align-items: center; gap: 10px; height: 36px; padding: 0 12px; background: transparent; border: none; border-radius: 8px; cursor: pointer; color: var(--text); transition: background .12s ease; }
.top-brand-btn:hover { background: var(--bg-hover); }
.top-brand-btn:active, .top-brand-btn.open { background: var(--bg-active); }
.apps-ic { color: var(--text-3); flex-shrink: 0; }
.top-brand-btn .logo { width: 22px; height: 32px; object-fit: contain; display: block; flex-shrink: 0; }
.product-name { font-family: var(--font-heading); font-size: var(--fs-200); line-height: var(--lh-200); font-weight: var(--fw-bold); color: var(--text); letter-spacing: -.2px; display: inline-flex; align-items: center; white-space: nowrap; }
.product-x { color: var(--accent); font-weight: 800; margin: 0 8px; font-family: var(--font-heading); font-size: var(--fs-200); font-style: italic; letter-spacing: 0; }
.tas-pop { position: absolute; top: calc(100% + 6px); left: 6px; z-index: 60; min-width: 220px; padding: 8px; background: var(--bg-panel); border: 1px solid var(--border); border-radius: 12px; box-shadow: 0 12px 36px rgba(0,0,0,.14); }
.tas-item { width: 100%; display: flex; align-items: center; gap: 12px; padding: 9px 10px; background: transparent; border: 0; border-radius: 8px; cursor: pointer; text-align: left; font-size: 14px; color: var(--text); }
.tas-item:hover { background: var(--bg-soft); }
.tas-ic { width: 18px; text-align: center; color: var(--text-3); }
.tas-ic.accent { color: var(--accent); }
.tas-label { flex: 1; }
.tas-item.active .tas-label { font-weight: 700; }
.tas-check { color: var(--accent); }
.tas-sep { height: 1px; background: var(--border-soft); margin: 6px 4px; }

.top-mid { flex: 1; min-width: 0; }
.search { position: absolute; left: 50%; top: 50%; transform: translate(-50%, -50%); width: 360px; height: 32px; background: var(--chip); border: 1px solid transparent; border-radius: 6px; display: flex; align-items: center; padding: 0 14px; gap: 10px; color: var(--text-2); font-size: 13px; cursor: pointer; transition: background .12s ease; }
.search:hover { background: var(--chip-hover); }

.top-right { display: flex; align-items: center; gap: 4px; flex-shrink: 0; }
.top-upgrade { border: none; background: linear-gradient(90deg, var(--accent), var(--warn)); color: #fff; font-size: 12px; font-weight: var(--fw-bold); padding: 7px 14px; border-radius: 999px; cursor: pointer; white-space: nowrap; flex-shrink: 0; margin-right: 4px; transition: filter .12s ease; }
.top-upgrade:hover { filter: brightness(1.06); }
.ic-btn { width: 32px; height: 32px; border: none; background: transparent; color: var(--text-3); border-radius: 6px; display: inline-flex; align-items: center; justify-content: center; cursor: pointer; transition: background .12s ease, color .12s ease; }
.ic-btn:hover { background: var(--bg-hover); color: var(--text); }
.ic-btn.active { background: var(--accent-soft); color: var(--accent); }

.um-wrap { position: relative; display: inline-flex; }
.user-chip { position: relative; width: 32px; height: 32px; border: none; background: transparent; cursor: pointer; padding: 0; margin-left: 4px; }
.user-chip .avatar { width: 28px; height: 28px; border-radius: 50%; background: var(--accent); color: #fff; display: inline-flex; align-items: center; justify-content: center; font-weight: 600; font-size: 13px; line-height: 1; }
.user-chip.open .avatar { box-shadow: 0 0 0 2px var(--accent); }
.user-chip:hover .avatar { filter: brightness(1.05); }
.online-dot { position: absolute; right: 0; bottom: 0; width: 10px; height: 10px; border-radius: 50%; background: var(--ok); border: 2px solid var(--bg-soft); }
.um-pop { position: absolute; top: calc(100% + 8px); right: 0; z-index: 60; width: 280px; padding: 8px; background: var(--bg-panel); border: 1px solid var(--border); border-radius: 12px; box-shadow: 0 12px 36px rgba(0,0,0,.14); }
.um-head { display: flex; align-items: center; gap: 10px; padding: 8px; }
.um-ava { width: 38px; height: 38px; border-radius: 9px; background: var(--accent); color: #fff; display: inline-flex; align-items: center; justify-content: center; font-size: 15px; font-weight: 600; }
.um-name { font-size: 14px; font-weight: 700; word-break: break-all; }
.um-handle { font-size: 11px; color: var(--text-3); margin-top: 2px; word-break: break-all; }
.um-online { color: var(--ok); }
.um-sep { height: 1px; background: var(--border-soft); margin: 6px 4px; }
.um-item { width: 100%; display: flex; align-items: center; gap: 10px; padding: 8px; background: transparent; border: 0; border-radius: 8px; cursor: pointer; text-align: left; font-size: 14px; color: var(--text-2); }
.um-item:hover { background: var(--bg-soft); color: var(--text); }
.um-ic { width: 18px; text-align: center; }
.um-item.danger { color: var(--danger); }
.um-item.danger:hover { background: #fdecec; }

/* ──── 主体（flex，浮卡靠 margin + 缝隙露灰底）──── */
.body { flex: 1; display: flex; min-height: 0; background: var(--bg-soft); }
.body.focused .main { margin: 8px; }

/* WorkspaceRail */
.ws-rail { width: var(--ws-rail-w); background: var(--bg-soft); display: flex; flex-direction: column; align-items: center; padding: 12px 0; gap: 8px; flex-shrink: 0; }
.ws-icon { width: 40px; height: 40px; border-radius: 10px; background: var(--chip); border: 2px solid transparent; display: flex; align-items: center; justify-content: center; font-family: var(--font-heading); font-weight: var(--fw-bold); color: var(--text); cursor: pointer; font-size: 13px; line-height: 1; letter-spacing: -.5px; user-select: none; transition: background .12s ease, border-color .12s ease, box-shadow .12s ease, color .12s ease; }
.ws-icon:hover { background: var(--chip-hover); }
.ws-icon.active { background: var(--bg-panel); color: var(--text); border-color: var(--ws-active); box-shadow: 0 0 0 2px var(--ws-active-soft); }
.ws-icon.plus { color: var(--text-3); font-size: 18px; border-style: dashed; border-color: var(--border); background: transparent; }
.ws-icon.plus:hover { border-color: var(--text-3); background: var(--bg-hover); }
.ws-sep { width: 24px; height: 1px; background: var(--border); margin-top: auto; flex-shrink: 0; }
.ws-icon.ws-tool { background: transparent; color: var(--text-3); font-size: 16px; }
.ws-icon.ws-tool:hover { background: var(--bg-hover); color: var(--text); }

/* ChannelSidebar（浮卡）*/
.channels { width: var(--channels-w); background: var(--bg-side); border: none; border-radius: 12px; margin: 8px 0 8px 8px; overflow: hidden; display: flex; flex-direction: column; flex-shrink: 0; }
.cs-ws-head { display: flex; align-items: center; padding: 8px 8px 8px 14px; gap: 6px; height: 48px; flex-shrink: 0; }
.cs-ws-name { flex: 1; display: inline-flex; align-items: center; gap: 6px; background: transparent; border: none; padding: 4px 6px; border-radius: 6px; cursor: pointer; text-align: left; min-width: 0; }
.cs-ws-name:hover { background: var(--bg-hover); }
.cs-ws-name .name { font-family: var(--font-heading); font-size: var(--fs-200); line-height: var(--lh-200); font-weight: var(--fw-bold); color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cs-ws-name .chev { color: var(--text-3); flex-shrink: 0; }
.cs-add { width: 28px; height: 28px; background: transparent; border: none; color: var(--text-3); border-radius: 6px; display: inline-flex; align-items: center; justify-content: center; cursor: pointer; flex-shrink: 0; }
.cs-add:hover { background: var(--bg-hover); color: var(--text); }
.cs-filter { display: flex; align-items: center; padding: 4px 8px 10px; gap: 6px; flex-shrink: 0; }
.cs-filter-funnel { width: 28px; height: 28px; background: transparent; border: none; color: var(--text-3); border-radius: 6px; display: inline-flex; align-items: center; justify-content: center; cursor: pointer; flex-shrink: 0; }
.cs-filter-funnel:hover { background: var(--bg-hover); color: var(--text); }
.cs-filter-input { flex: 1; height: 28px; border: 1px solid var(--border); background: var(--bg-panel); border-radius: 6px; padding: 0 12px; font-size: 13px; font-family: var(--font-body); color: var(--text); outline: none; min-width: 0; }
.cs-filter-input:focus { border-color: var(--text-3); }
.cs-filter-input::placeholder { color: var(--text-dim); }
.cs-list { flex: 1; overflow-y: auto; padding: 0 8px 14px; }
.cs-group { margin-top: 8px; }
.cs-group-head { display: flex; align-items: center; gap: 6px; padding: 6px 8px; background: transparent; border: none; color: var(--text-3); font-size: 13px; font-weight: 500; cursor: pointer; width: 100%; text-align: left; border-radius: 6px; }
.cs-group-head:hover { background: var(--bg-hover); color: var(--text); }
.cs-group-head .caret { transition: transform .12s ease; flex-shrink: 0; }
.cs-group-head .caret.open { transform: rotate(90deg); }
.cs-item { display: flex; align-items: center; gap: 8px; padding: 6px 8px; margin: 1px 0; border-radius: 6px; cursor: pointer; color: var(--text-2); font-size: 14px; min-width: 0; position: relative; }
.cs-item:hover { background: var(--bg-hover); color: var(--text); }
.cs-item.active { background: var(--bg-panel); color: var(--text); font-weight: 600; box-shadow: 0 1px 2px rgba(0,0,0,.04); }
.cs-item.active::before { content: ""; position: absolute; left: -4px; top: 6px; bottom: 6px; width: 3px; border-radius: 2px; background: var(--accent); }
.cs-ic { width: 18px; height: 18px; display: inline-flex; align-items: center; justify-content: center; color: var(--text-3); flex-shrink: 0; }
.cs-item.active .cs-ic { color: var(--text); }
.cs-label { flex: 1; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cs-empty { font-size: 12px; color: var(--text-3); padding: 6px 10px; }
.cs-add-row { color: var(--text-3); }
.cs-ic-box { width: 18px; height: 18px; border: 1px dashed var(--border); border-radius: 4px; display: inline-flex; align-items: center; justify-content: center; color: var(--text-3); flex-shrink: 0; }
.cs-dm-av { width: 22px; height: 22px; border-radius: 50%; background: var(--accent); color: #fff; display: inline-flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 600; flex-shrink: 0; position: relative; }
.cs-dm-av.bot { background: var(--text); border-radius: 6px; }
.dot-online { position: absolute; right: -2px; bottom: -2px; width: 8px; height: 8px; border-radius: 50%; background: var(--ok); border: 1.5px solid var(--bg-side); }

/* main（浮卡）*/
.main { flex: 1; display: flex; flex-direction: column; min-width: 0; background: var(--bg); border-radius: 12px; margin: 8px; overflow: hidden; }
.ch-header { height: 50px; flex-shrink: 0; border-bottom: 1px solid var(--border); display: flex; align-items: center; gap: 10px; padding: 0 16px; background: var(--bg-panel); }
.ch-fav { width: 28px; height: 28px; background: transparent; border: none; color: var(--text-3); border-radius: 6px; display: inline-flex; align-items: center; justify-content: center; cursor: pointer; flex-shrink: 0; }
.ch-fav:hover { background: var(--bg-hover); color: var(--text); }
.ch-fav.active { color: var(--warn); }
.title { font-family: var(--font-heading); font-size: var(--fs-200); line-height: var(--lh-200); font-weight: var(--fw-bold); display: flex; align-items: center; gap: 6px; color: var(--text); flex-shrink: 0; }
.title .hash { color: var(--text-3); font-weight: 400; }
.ch-actions { margin-left: auto; display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
.ch-members-btn { display: inline-flex; align-items: center; background: transparent; border: none; cursor: pointer; padding: 3px 6px; border-radius: 6px; transition: background .12s ease; }
.ch-members-btn:hover { background: var(--bg-hover); }
.ava-stack { display: flex; align-items: center; }
.ava-stack .a { width: 22px; height: 22px; border-radius: 50%; background: var(--accent); color: #fff; display: flex; align-items: center; justify-content: center; font-size: 10px; font-weight: 600; border: 2px solid var(--bg-panel); margin-left: -6px; }
.ava-stack .a:first-child { margin-left: 0; }
.ava-stack .a.bot { background: var(--text); border-radius: 5px; }
.ch-members-count { font-size: 13px; color: var(--text-3); font-family: var(--mono); margin: 0 0 0 6px; }
.ch-ic-btn { width: 30px; height: 30px; background: transparent; border: none; color: var(--text-3); border-radius: 6px; display: inline-flex; align-items: center; justify-content: center; cursor: pointer; transition: background .12s ease, color .12s ease; }
.ch-ic-btn:hover { background: var(--bg-hover); color: var(--text); }
.ch-ic-btn.active { background: var(--accent-soft); color: var(--accent); }

/* 消息流（扁平 Slack 风）*/
.stream { flex: 1; overflow-y: auto; padding: 16px var(--content-pad-x) 20px; }
.msg { display: flex; gap: 12px; padding: 8px 0; border-radius: 6px; }
/* 平时不铺底色（保持干净白底）；只有未读 / 选中时才出现底色 */
.msg.unread { background: var(--accent-soft); margin: 0 -10px; padding: 8px 10px; box-shadow: inset 3px 0 0 var(--accent); }
.msg.selected { background: var(--bg-soft); margin: 0 -10px; padding: 8px 10px; }
.msg .ava { width: 36px; height: 36px; border-radius: 6px; flex-shrink: 0; display: flex; align-items: center; justify-content: center; font-weight: 600; font-size: 13px; color: #fff; background: var(--text-3); position: relative; }
.msg.me .ava { background: var(--accent); color: #1a1300; }
.msg.bot .ava { background: var(--text); }
.msg.bot .ava::after { content: ""; position: absolute; bottom: -1px; right: -1px; width: 10px; height: 10px; border-radius: 50%; background: var(--accent); border: 2px solid var(--bg); }
.msg .msg-body { flex: 1; min-width: 0; }
.msg .head { display: flex; align-items: baseline; gap: 8px; margin-bottom: 2px; }
.msg .name { font-weight: var(--fw-bold); font-size: var(--fs-100); color: var(--text); }
.msg .role { font-size: var(--fs-50); padding: 1px 6px; border-radius: 3px; background: var(--bg-code); color: var(--text-3); letter-spacing: .3px; }
.msg .role.bot { color: var(--text-2); }
.msg .role.human { background: var(--accent-soft); color: var(--accent); }
.msg .time { font-size: var(--fs-75); color: var(--text-3); }
.msg .text { color: var(--text); font-size: var(--fs-100); line-height: var(--lh-200); white-space: pre-wrap; word-break: break-word; }
.rich { margin-top: 8px; border: 1px solid var(--border); background: var(--bg-panel); border-radius: 6px; padding: 14px 16px; }
.rich.info { border-left: 3px solid var(--info); }
.rich .r-head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.rich .r-head .t { font-weight: 600; font-size: 14px; }
.rich p { font-size: 13px; color: var(--text-3); margin: 4px 0 0; }
.rich .kv { display: grid; grid-template-columns: auto 1fr; gap: 4px 14px; font-size: 13px; margin-top: 8px; }
.rich .kv .k { color: var(--text-3); }
.rich .kv .v { color: var(--text); font-weight: 500; text-align: right; }
.rich .kv .v.ai { color: var(--info); }
.rich .kv .v.human { color: var(--warn); }

/* Composer */
.composer { flex-shrink: 0; padding: 8px var(--content-pad-x) 14px; background: var(--bg); }
.composer-box { border: 1px solid var(--border); border-radius: 12px; background: var(--bg-panel); overflow: hidden; transition: border-color .12s ease, box-shadow .12s ease; }
.composer-box:focus-within { border-color: var(--ws-active); box-shadow: 0 0 0 3px var(--ws-active-soft); }
.composer textarea { width: 100%; border: none; background: transparent; outline: none; resize: none; font-family: var(--font-body); font-size: 14px; color: var(--text); min-height: 38px; line-height: 1.55; padding: 10px 14px 4px; display: block; }
.composer textarea::placeholder { color: var(--text-dim); }
.composer-toolbar { display: flex; align-items: center; padding: 4px 6px; gap: 2px; }
.tb-left, .tb-right { display: flex; align-items: center; gap: 1px; }
.tb-right { margin-left: auto; }
.tb-btn { background: transparent; border: none; color: var(--text-3); width: 28px; height: 28px; border-radius: 5px; display: inline-flex; align-items: center; justify-content: center; cursor: pointer; font-size: 13px; }
.tb-btn:hover { background: var(--bg-hover); color: var(--text); }
.tb-heading { font-weight: 700; font-family: var(--font-heading); font-size: 14px; }
.tb-sep { width: 1px; height: 16px; background: var(--border); margin: 0 4px; }
.tb-btn.tb-ai { width: auto; padding: 0 8px; gap: 4px; color: var(--accent); font-weight: var(--fw-bold); font-size: 12px; }
.tb-btn.tb-ai:hover { background: var(--accent-soft); color: var(--accent); }
.send { background: var(--accent); color: #fff; border: none; width: 28px; height: 28px; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; cursor: pointer; margin-left: 4px; transition: background .12s ease, opacity .12s ease; }
.send:hover { background: var(--warn); }
.send:disabled { background: var(--border); color: var(--text-dim); cursor: not-allowed; opacity: .7; }

/* ──── 右侧中枢 AI 面板（浮卡）──── */
.ai-panel { width: var(--right-w-ai, 360px); flex-shrink: 0; background: var(--bg-panel); display: flex; flex-direction: column; border-radius: 12px; margin: 8px 0; overflow: hidden; }
.ai-head { height: 50px; flex-shrink: 0; padding: 0 14px; display: flex; align-items: center; gap: 8px; border-bottom: 1px solid var(--border-soft); }
.ai-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--ok); box-shadow: 0 0 0 4px rgba(22,163,74,.16); flex-shrink: 0; }
.ai-title { font-family: var(--font-heading); font-size: var(--fs-200); line-height: var(--lh-200); font-weight: var(--fw-bold); color: var(--text); }
.ai-head-actions { margin-left: auto; display: flex; align-items: center; gap: 2px; }
.ai-ic-btn { width: 30px; height: 30px; background: transparent; border: none; color: var(--text-3); border-radius: 6px; display: inline-flex; align-items: center; justify-content: center; cursor: pointer; }
.ai-ic-btn:hover { background: var(--bg-hover); color: var(--text); }
.ai-body { flex: 1; overflow-y: auto; padding: 12px 14px 16px; display: flex; flex-direction: column; gap: 10px; }
.ai-msg { display: flex; }
.ai-msg.mine { justify-content: flex-end; }
.ai-bubble { max-width: 86%; background: #fff; border: 1px solid var(--border-soft); padding: 9px 12px; border-radius: 12px; font-size: 14px; line-height: 1.5; white-space: pre-wrap; word-break: break-word; color: var(--text); }
.ai-msg.mine .ai-bubble { background: #fde7c2; border: 0; }
.ai-composer { flex-shrink: 0; padding: 10px 14px 14px; }
.ai-input-box { border: 1px solid var(--border); border-radius: 12px; background: var(--bg); padding: 8px 8px 4px 12px; transition: border-color .12s ease, box-shadow .12s ease; }
.ai-input-box:focus-within { border-color: var(--ws-active); box-shadow: 0 0 0 3px var(--ws-active-soft); }
.ai-input-box input { width: 100%; border: none; outline: none; background: transparent; font-family: var(--font-body); font-size: 14px; color: var(--text); padding: 2px 4px; }
.ai-input-box input::placeholder { color: var(--text-dim); }
.ai-toolbar { display: flex; align-items: center; margin-top: 4px; padding-top: 4px; }
.ai-tb-left { display: flex; align-items: center; gap: 1px; }
.ai-tb-btn { width: 28px; height: 28px; background: transparent; border: none; color: var(--text-3); border-radius: 6px; display: inline-flex; align-items: center; justify-content: center; cursor: pointer; }
.ai-tb-btn:hover { background: var(--bg-hover); color: var(--text); }
.ai-send-ic { margin-left: auto; background: var(--accent); color: #fff; border: none; width: 28px; height: 28px; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; cursor: pointer; transition: background .12s ease, opacity .12s ease; }
.ai-send-ic:hover { background: var(--warn); }
.ai-send-ic:disabled { background: var(--border); color: var(--text-dim); cursor: not-allowed; opacity: .7; }

/* ──── 右侧插件竖栏（40 宽，pr-icon 32 圆形）──── */
.plugin-rail { width: var(--plugin-rail-w); background: var(--bg-soft); display: flex; flex-direction: column; align-items: center; padding: 10px 0; gap: 8px; flex-shrink: 0; }
.pr-list { display: flex; flex-direction: column; align-items: center; gap: 8px; flex: 1; overflow-y: auto; width: 100%; }
.pr-icon { width: 32px; height: 32px; border-radius: 50%; background: var(--chip); border: none; display: flex; align-items: center; justify-content: center; font-weight: var(--fw-bold); color: var(--text); cursor: pointer; position: relative; font-size: 11px; line-height: 1; flex-shrink: 0; user-select: none; transition: transform .12s ease, background .12s ease, color .12s ease, box-shadow .12s ease; }
.pr-icon:hover { background: var(--chip-hover); }
.pr-icon.active { background: var(--ws-active); color: #fff; }
.pr-icon.active::after { content: ""; position: absolute; left: -9px; top: 4px; bottom: 4px; width: 2px; border-radius: 2px; background: var(--text); }
.pr-icon.plus { background: transparent; border: 2px dashed var(--border); color: var(--text-3); font-size: 16px; }
.pr-icon.plus:hover { background: var(--bg-hover); border-color: var(--text-3); color: var(--text); }
.pr-icon.assets, .pr-icon.gear { color: var(--text-3); font-size: 16px; background: transparent; }
.pr-icon.assets:hover { background: var(--accent-soft); color: var(--accent); }
.pr-icon.gear:hover { background: var(--bg-hover); color: var(--text); }
.pr-divider { width: 18px; height: 1px; background: var(--border); margin: 4px 0; }

/* ──── toast ──── */
.toast-host { position: fixed; right: 18px; bottom: 18px; z-index: 200; display: flex; flex-direction: column; gap: 10px; }
.toast { min-width: 220px; max-width: 320px; padding: 12px 14px; background: var(--bg-panel); border: 1px solid var(--border); border-left: 3px solid var(--accent); border-radius: 10px; box-shadow: 0 10px 30px rgba(0,0,0,.12); animation: toast-in .18s ease; }
.toast-title { font-size: 14px; font-weight: 700; color: var(--text); }
.toast-msg { font-size: 12px; color: var(--text-3); margin-top: 3px; }
@keyframes toast-in { from { opacity: 0; transform: translateX(12px); } to { opacity: 1; transform: none; } }
</style>
