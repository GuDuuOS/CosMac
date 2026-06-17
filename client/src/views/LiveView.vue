<!--
  CosMac Star 真实客户端驾驶舱（演示版按键布局 · 暖色皮肤 · 真实后端）
  --------------------------------------------------------------------
  这一版把界面"按键布局"对齐筱雨工作室演示版（顶栏九宫格应用切换 / 升级·提及·收藏·设置 /
  用户菜单、左侧 WorkspaceRail 工作区竖栏、ChannelSidebar 频道+私信分组与筛选、频道头
  ★收藏·成员·专注·关于、Composer 完整 Markdown 工具条、右侧 PluginRail 插件竖栏），
  但所有"会真正干活"的按钮仍然连真实 Synapse：
    · 登录 / 退出 / 会话记忆       → matrix/client.ts
    · 左侧真实频道列表 + 筛选       → listRooms / 本地 filter
    · 频道消息流（含 cosmac.card 富卡）→ listMessages
    · 发送消息（含 Markdown 工具条）→ sendText
    · 右侧"中枢 AI"面板（与主 AI 私聊，AI 对每句话都回）→ ensureBotDm / sendText
  纯装饰/演示用的按钮（升级会员、提及、收藏、附件等）只弹一个轻量 toast，不影响主流程。
  配色：沿用现已做好的 CosMac 暖色（米白 + 品牌橙 + 暖墨），全部走 tokens.css 变量。
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
  type LiveRoom,
  type LiveMsg,
} from '@/matrix/client'
import { tenant } from '@/config/tenant'
import logoUrl from '@/assets/cosmac-logo.png'

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

// ── 轻量 toast（给装饰按钮一个反馈，不引外部依赖）─────────
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
  // 左侧频道列表排除"中枢 AI"私聊（它在右侧面板 / 私信组里单独显示）
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

// 点击左侧"中枢 AI"私信 → 直接展开右侧面板
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
/** 在选区前后包裹 before/after；无选区时插入占位文字并选中 */
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
/** 在当前行行首插入 prefix（如 "## "、"> "、"- "）*/
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
  ol: () => prefixLine('1. '),
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

// 点击空白处关闭顶栏下拉
function onDocClick(e: MouseEvent) {
  if (!rootEl.value) return
  const t = e.target as Node
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
    <!-- ───────── 顶栏（演示版布局）───────── -->
    <header class="topbar">
      <!-- 左：品牌 / 九宫格应用切换器 -->
      <div class="tas-wrap">
        <button class="top-brand-btn" :class="{ open: appMenuOpen }" @click.stop="appMenuOpen = !appMenuOpen">
          <svg class="apps-ic" width="18" height="18" viewBox="0 0 18 18" fill="currentColor">
            <circle cx="3" cy="3" r="1.6" /><circle cx="9" cy="3" r="1.6" /><circle cx="15" cy="3" r="1.6" />
            <circle cx="3" cy="9" r="1.6" /><circle cx="9" cy="9" r="1.6" /><circle cx="15" cy="9" r="1.6" />
            <circle cx="3" cy="15" r="1.6" /><circle cx="9" cy="15" r="1.6" /><circle cx="15" cy="15" r="1.6" />
          </svg>
          <img :src="logoUrl" alt="" class="logo" />
          <span class="product-name">CosMac<span class="product-x">×</span>{{ tenant.topbarSuffix }}</span>
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

      <!-- 中：搜索 -->
      <div class="top-mid">
        <div class="search" role="button" tabindex="0" @click="onSearch">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8" /><path d="m21 21-4.3-4.3" /></svg>
          <span>搜索</span>
        </div>
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
        <!-- 用户菜单 -->
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

    <!-- ───────── 主体三栏 + 两侧竖栏 ───────── -->
    <div class="body" :class="{ focused }">
      <!-- 最左：工作区竖栏（WorkspaceRail）-->
      <nav v-if="!focused" class="ws-rail">
        <div class="ws-icon active" :title="tenant.hqTitle">{{ tenant.hqLabel }}</div>
        <div class="ws-icon plus" title="新建工作区" @click="onAddWorkspace">+</div>
        <div class="ws-sep" />
        <div class="ws-icon ws-tool" title="AI Agent 商城" @click="onMarket">🛒</div>
        <div class="ws-icon ws-tool" title="CLI" @click="onCli">▸</div>
        <div class="ws-icon ws-tool" title="个人主页" @click="onProfile">🏠</div>
      </nav>

      <!-- 左：频道侧栏（ChannelSidebar）-->
      <aside v-if="!focused" class="channels">
        <!-- workspace 名 + 添加 -->
        <div class="cs-ws-head">
          <button class="cs-ws-name" :title="tenant.hqTitle">
            <span class="name">{{ tenant.hqTitle }}</span>
            <svg class="chev" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6" /></svg>
          </button>
          <button class="cs-add" title="添加" @click="onAddChannel">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M12 5v14" /></svg>
          </button>
        </div>

        <!-- 筛选 -->
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

          <!-- 私信 group（中枢 AI 私聊）-->
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

      <!-- 中：频道消息 -->
      <main class="main">
        <!-- 频道头（ChannelHeader）-->
        <div v-if="currentRoom" class="ch-header">
          <button class="ch-fav" :class="{ active: fav }" :title="fav ? '取消收藏' : '收藏'" @click="fav = !fav">
            <svg width="16" height="16" viewBox="0 0 24 24" :fill="fav ? 'currentColor' : 'none'" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" /></svg>
          </button>
          <div class="ch-title"><span class="hash">#</span>{{ currentName }}</div>
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

        <!-- 消息流 -->
        <div class="stream">
          <div v-for="m in msgs" :key="m.id" class="row" :class="{ mine: isMe(m.sender) }">
            <div class="avatar">{{ initials(m.senderName) }}</div>
            <div class="bubble-wrap">
              <div class="who">{{ m.senderName }}</div>
              <div v-if="!m.card" class="bubble">{{ m.body }}</div>
              <div v-if="m.card" class="card">
                <div class="card-title">🗂 {{ m.card.title }}</div>
                <div class="card-sub" v-if="m.card.subtitle">{{ m.card.subtitle }}</div>
                <div v-for="(rw, i) in (m.card.rows || [])" :key="i" class="card-row">
                  <span>{{ rw.task }}</span>
                  <span :class="rw.type">{{ rw.owner }}</span>
                </div>
              </div>
            </div>
          </div>
          <p v-if="currentRoom && !msgs.length" class="hint pad">这个频道还没有消息</p>
          <p v-if="!currentRoom" class="hint pad">← 选一个频道开始</p>
        </div>

        <!-- Composer（演示版完整工具条 · Markdown 真实生效）-->
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
                <button class="tb-btn" title="标题" @click="tb.heading">H</button>
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

      <!-- 右：中枢 AI 面板（与主 AI 私聊，私聊里它对每句话都回）-->
      <aside class="ai-panel" v-if="aiOpen && !focused">
        <div class="ai-head">
          <span class="ai-dot" /> 中枢 AI · CosMac Star
          <button class="ai-close" title="收起" @click="aiOpen = false">×</button>
        </div>
        <div class="stream">
          <div v-for="m in aiMsgs" :key="m.id" class="row" :class="{ mine: isMe(m.sender) }">
            <div class="bubble-wrap">
              <div v-if="!m.card" class="bubble">{{ m.body }}</div>
              <div v-if="m.card" class="card">
                <div class="card-title">🗂 {{ m.card.title }}</div>
                <div class="card-sub" v-if="m.card.subtitle">{{ m.card.subtitle }}</div>
                <div v-for="(rw, i) in (m.card.rows || [])" :key="i" class="card-row">
                  <span>{{ rw.task }}</span>
                  <span :class="rw.type">{{ rw.owner }}</span>
                </div>
              </div>
            </div>
          </div>
          <p v-if="!aiMsgs.length" class="hint pad">跟中枢 AI 说句话，比如"帮我建个爆款专班"</p>
        </div>
        <div class="composer mini">
          <div class="composer-box">
            <input v-model="aiDraft" placeholder="一句话下达目标…" @keyup.enter="aiSend" />
            <button class="send inline" :disabled="!aiDraft.trim()" @click="aiSend"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M22 2 11 13" /><path d="M22 2 15 22l-4-9-9-4Z" /></svg></button>
          </div>
        </div>
      </aside>

      <!-- 最右：插件竖栏（PluginRail）-->
      <nav v-if="!focused" class="plugin-rail">
        <div class="pr-list">
          <div class="pr-icon active" title="中枢 AI" @click="aiOpen = !aiOpen">智</div>
          <div class="pr-icon plus" title="添加插件" @click="onMarket">+</div>
        </div>
        <div class="pr-divider" />
        <div class="pr-icon" title="资产 · 自定义配置" @click="onMarket">◈</div>
        <div class="pr-icon" title="插件商城" @click="onMarket">⚙</div>
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
.shell { height: 100vh; display: flex; flex-direction: column; font-family: var(--font-body); color: var(--text); }

/* ──── 顶栏 ──── */
.topbar { display: flex; align-items: center; gap: 10px; height: var(--topbar-h); padding: 0 10px 0 6px; border-bottom: 1px solid var(--border); background: var(--bg-soft); flex-shrink: 0; }
.tas-wrap { position: relative; display: inline-flex; }
.top-brand-btn { display: inline-flex; align-items: center; gap: 8px; height: 34px; padding: 0 10px; background: transparent; border: 1px solid transparent; border-radius: 9px; cursor: pointer; color: var(--text); }
.top-brand-btn:hover, .top-brand-btn.open { background: var(--bg-hover); }
.apps-ic { color: var(--text-3); }
.top-brand-btn .logo { width: 20px; height: 20px; object-fit: contain; border-radius: 5px; }
.product-name { font-weight: 700; font-size: 14px; }
.product-x { color: var(--accent); margin: 0 3px; }
.tas-pop { position: absolute; top: calc(100% + 6px); left: 6px; z-index: 60; min-width: 220px; padding: 8px; background: var(--bg-panel); border: 1px solid var(--border); border-radius: 12px; box-shadow: 0 12px 36px rgba(0,0,0,.14); }
.tas-item { width: 100%; display: flex; align-items: center; gap: 12px; padding: 9px 10px; background: transparent; border: 0; border-radius: 8px; cursor: pointer; text-align: left; font-size: 14px; color: var(--text); }
.tas-item:hover { background: var(--bg-soft); }
.tas-ic { width: 18px; text-align: center; color: var(--text-3); }
.tas-ic.accent { color: var(--accent); }
.tas-label { flex: 1; }
.tas-item.active .tas-label { font-weight: 700; }
.tas-check { color: var(--accent); }
.tas-sep { height: 1px; background: var(--border-soft); margin: 6px 4px; }

.top-mid { flex: 1; display: flex; justify-content: center; }
.search { display: inline-flex; align-items: center; gap: 8px; height: 30px; min-width: 220px; max-width: 420px; width: 40%; padding: 0 12px; background: var(--bg-panel); border: 1px solid var(--border); border-radius: 8px; color: var(--text-3); font-size: 13px; cursor: pointer; }
.search:hover { border-color: var(--accent); }

.top-right { display: inline-flex; align-items: center; gap: 6px; }
.top-upgrade { height: 30px; padding: 0 12px; border: 0; border-radius: 8px; background: var(--accent-soft); color: var(--warn); font-size: 12px; font-weight: 700; cursor: pointer; white-space: nowrap; }
.top-upgrade:hover { background: #ffe9c2; }
.ic-btn { width: 32px; height: 32px; display: inline-flex; align-items: center; justify-content: center; border: 0; border-radius: 8px; background: transparent; color: var(--text-2); cursor: pointer; }
.ic-btn:hover { background: var(--bg-hover); color: var(--text); }
.ic-btn.active { background: var(--accent-soft); color: var(--accent); }

.um-wrap { position: relative; display: inline-flex; }
.user-chip { position: relative; width: 34px; height: 34px; border: 0; background: transparent; cursor: pointer; padding: 0; }
.user-chip .avatar { width: 30px; height: 30px; border-radius: 8px; background: var(--action); color: #fff; display: flex; align-items: center; justify-content: center; font-size: 13px; font-weight: 700; }
.user-chip.open .avatar { box-shadow: 0 0 0 2px var(--accent); }
.online-dot { position: absolute; right: 1px; bottom: 1px; width: 9px; height: 9px; border-radius: 50%; background: var(--ok); border: 2px solid var(--bg-soft); }
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

/* ──── 主体 ──── */
.body { flex: 1; display: grid; grid-template-columns: var(--ws-rail-w) var(--channels-w) 1fr; min-height: 0; }
.body:has(.ai-panel) { grid-template-columns: var(--ws-rail-w) var(--channels-w) 1fr var(--right-w) var(--plugin-rail-w); }
.body:not(:has(.ai-panel)) { grid-template-columns: var(--ws-rail-w) var(--channels-w) 1fr var(--plugin-rail-w); }
.body.focused { grid-template-columns: 1fr; }

/* WorkspaceRail */
.ws-rail { background: var(--bg-soft); border-right: 1px solid var(--border); display: flex; flex-direction: column; align-items: center; gap: 8px; padding: 10px 0; overflow: auto; }
.ws-icon { width: 40px; height: 40px; border-radius: 12px; background: var(--bg-panel); border: 1px solid var(--border); display: flex; align-items: center; justify-content: center; font-size: 14px; font-weight: 700; color: var(--text-2); cursor: pointer; }
.ws-icon:hover { border-radius: 12px; background: var(--bg-hover); }
.ws-icon.active { background: var(--action); color: #fff; border-color: var(--action); box-shadow: 0 0 0 2px var(--accent); }
.ws-icon.plus { font-size: 20px; color: var(--text-3); font-weight: 400; }
.ws-icon.ws-tool { font-size: 16px; }
.ws-sep { width: 24px; height: 1px; background: var(--border); margin: 4px 0; }

/* ChannelSidebar */
.channels { background: var(--bg-side); border-right: 1px solid var(--border); display: flex; flex-direction: column; min-height: 0; }
.cs-ws-head { display: flex; align-items: center; height: 46px; padding: 0 8px 0 14px; border-bottom: 1px solid var(--border-soft); }
.cs-ws-name { flex: 1; display: flex; align-items: center; gap: 6px; background: transparent; border: 0; cursor: pointer; font-size: 15px; font-weight: 700; color: var(--text); padding: 4px; border-radius: 6px; }
.cs-ws-name:hover { background: var(--bg-hover); }
.cs-ws-name .name { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cs-ws-name .chev { color: var(--text-3); }
.cs-add { width: 28px; height: 28px; display: flex; align-items: center; justify-content: center; border: 0; border-radius: 7px; background: transparent; color: var(--text-2); cursor: pointer; }
.cs-add:hover { background: var(--bg-hover); color: var(--text); }
.cs-filter { display: flex; align-items: center; gap: 6px; padding: 8px 10px; }
.cs-filter-funnel { width: 28px; height: 28px; display: flex; align-items: center; justify-content: center; border: 0; border-radius: 7px; background: transparent; color: var(--text-3); cursor: pointer; }
.cs-filter-funnel:hover { background: var(--bg-hover); color: var(--text); }
.cs-filter-input { flex: 1; height: 30px; padding: 0 10px; border: 1px solid var(--border); border-radius: 8px; background: var(--bg-panel); font-size: 13px; color: var(--text); }
.cs-list { flex: 1; overflow: auto; padding: 4px 8px 16px; }
.cs-group { margin-top: 6px; }
.cs-group-head { width: 100%; display: flex; align-items: center; gap: 6px; padding: 6px 6px; background: transparent; border: 0; cursor: pointer; font-size: 11px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; color: var(--text-3); }
.cs-group-head .caret { transition: transform .12s ease; }
.cs-group-head .caret.open { transform: rotate(90deg); }
.cs-item { display: flex; align-items: center; gap: 8px; padding: 7px 8px; border-radius: 8px; cursor: pointer; font-size: 14px; color: var(--text-2); }
.cs-item:hover { background: var(--bg-hover); }
.cs-item.active { background: var(--action); color: #fff; }
.cs-ic { width: 16px; display: inline-flex; justify-content: center; color: var(--text-3); flex-shrink: 0; }
.cs-item.active .cs-ic { color: rgba(255,255,255,.7); }
.cs-label { flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cs-empty { font-size: 12px; color: var(--text-3); padding: 6px 10px; }
.cs-add-row { color: var(--text-3); }
.cs-ic-box { width: 16px; display: inline-flex; justify-content: center; color: var(--text-3); }
.cs-dm-av { position: relative; width: 22px; height: 22px; border-radius: 6px; background: var(--text-3); color: #fff; display: inline-flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 700; flex-shrink: 0; }
.cs-dm-av.bot { background: var(--accent); color: #1a1300; }
.cs-item.active .cs-dm-av.bot { box-shadow: 0 0 0 2px rgba(255,255,255,.5); }
.dot-online { position: absolute; right: -2px; bottom: -2px; width: 8px; height: 8px; border-radius: 50%; background: var(--ok); border: 2px solid var(--bg-side); }

/* main */
.main { display: flex; flex-direction: column; min-height: 0; background: var(--bg); }
.ch-header { display: flex; align-items: center; gap: 10px; height: 52px; padding: 0 16px; border-bottom: 1px solid var(--border); flex-shrink: 0; }
.ch-fav { width: 30px; height: 30px; display: flex; align-items: center; justify-content: center; border: 0; border-radius: 7px; background: transparent; color: var(--text-3); cursor: pointer; }
.ch-fav:hover { background: var(--bg-hover); }
.ch-fav.active { color: var(--accent); }
.ch-title { font-weight: 700; font-size: 16px; display: flex; align-items: center; }
.ch-title .hash { color: var(--text-dim); margin-right: 3px; }
.ch-actions { margin-left: auto; display: inline-flex; align-items: center; gap: 6px; }
.ch-members-btn { display: inline-flex; align-items: center; gap: 6px; height: 30px; padding: 0 8px; border: 1px solid var(--border); border-radius: 8px; background: var(--bg-panel); cursor: pointer; color: var(--text-2); }
.ch-members-btn:hover { background: var(--bg-hover); }
.ava-stack { display: inline-flex; }
.ava-stack .a { width: 20px; height: 20px; border-radius: 50%; background: var(--action); color: #fff; display: flex; align-items: center; justify-content: center; font-size: 10px; font-weight: 700; margin-left: -6px; border: 2px solid var(--bg-panel); }
.ava-stack .a:first-child { margin-left: 0; }
.ava-stack .a.bot { background: var(--accent); color: #1a1300; }
.ch-members-count { font-size: 13px; font-weight: 600; }
.ch-ic-btn { width: 32px; height: 32px; display: inline-flex; align-items: center; justify-content: center; border: 0; border-radius: 8px; background: transparent; color: var(--text-2); cursor: pointer; }
.ch-ic-btn:hover { background: var(--bg-hover); color: var(--text); }
.ch-ic-btn.active { background: var(--accent-soft); color: var(--accent); }

.stream { flex: 1; overflow: auto; padding: 18px; display: flex; flex-direction: column; gap: 14px; }
.row { display: flex; gap: 10px; max-width: 760px; }
.row.mine { flex-direction: row-reverse; align-self: flex-end; }
.avatar { width: 34px; height: 34px; border-radius: 50%; background: var(--action); color: #fff; display: flex; align-items: center; justify-content: center; font-size: 13px; font-weight: 700; flex: 0 0 auto; }
.row.mine .avatar { background: var(--accent); color: #1a1300; }
.bubble-wrap { min-width: 0; }
.who { font-size: 12px; color: var(--text-3); margin-bottom: 3px; }
.row.mine .who { text-align: right; }
.bubble { background: var(--bg-code); padding: 9px 13px; border-radius: 12px; white-space: pre-wrap; word-break: break-word; }
.row.mine .bubble { background: #fde7c2; }
.card { margin-top: 8px; border: 1px solid var(--border); border-radius: 12px; padding: 14px; background: var(--bg-panel); max-width: 440px; }
.card-title { font-weight: 700; }
.card-sub { font-size: 12px; color: var(--text-3); margin: 2px 0 10px; }
.card-row { display: flex; justify-content: space-between; padding: 6px 0; border-top: 1px dashed var(--border-soft); font-size: 14px; }
.card-row .ai { color: var(--info); font-weight: 600; }
.card-row .human { color: var(--warn); font-weight: 600; }

/* Composer */
.composer { padding: 10px 16px 14px; flex-shrink: 0; }
.composer-box { border: 1px solid var(--border); border-radius: 12px; background: var(--bg-panel); overflow: hidden; }
.composer-box textarea { width: 100%; min-height: 46px; max-height: 180px; resize: none; border: 0; outline: 0; padding: 12px 14px; background: transparent; font-family: var(--font-body); font-size: 14px; color: var(--text); }
.composer-toolbar { display: flex; align-items: center; justify-content: space-between; padding: 4px 6px; border-top: 1px solid var(--border-soft); }
.tb-left, .tb-right { display: inline-flex; align-items: center; gap: 1px; }
.tb-btn { min-width: 28px; height: 28px; padding: 0 6px; display: inline-flex; align-items: center; justify-content: center; gap: 3px; border: 0; border-radius: 6px; background: transparent; color: var(--text-2); cursor: pointer; font-size: 13px; }
.tb-btn:hover { background: var(--bg-hover); color: var(--text); }
.tb-ai { color: var(--accent); font-weight: 700; }
.tb-ai:hover { background: var(--accent-soft); }
.tb-sep { width: 1px; height: 16px; background: var(--border); margin: 0 4px; }
.send { width: 30px; height: 28px; display: inline-flex; align-items: center; justify-content: center; border: 0; border-radius: 7px; background: var(--accent); color: #1a1300; cursor: pointer; margin-left: 4px; }
.send:disabled { background: var(--border); color: var(--text-dim); cursor: not-allowed; }

/* ──── 右侧中枢 AI 面板 ──── */
.ai-panel { border-left: 1px solid var(--border); display: flex; flex-direction: column; min-height: 0; background: var(--bg-panel); }
.ai-head { height: 52px; display: flex; align-items: center; gap: 8px; padding: 0 14px; border-bottom: 1px solid var(--border); font-weight: 700; font-size: 14px; }
.ai-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--ok); box-shadow: 0 0 0 4px rgba(22,163,74,.16); }
.ai-close { margin-left: auto; width: 26px; height: 26px; border: 0; border-radius: 6px; background: transparent; color: var(--text-3); font-size: 18px; cursor: pointer; line-height: 1; }
.ai-close:hover { background: var(--bg-hover); color: var(--text); }
.ai-panel .stream { padding: 14px; }
.ai-panel .row { max-width: 100%; }
.ai-panel .bubble { background: #fff; border: 1px solid var(--border-soft); }
.ai-panel .row.mine .bubble { background: #fde7c2; border: 0; }
.composer.mini { padding: 10px 12px 12px; }
.composer.mini .composer-box { display: flex; align-items: center; padding: 4px 4px 4px 6px; }
.composer.mini input { flex: 1; border: 0; outline: 0; background: transparent; font-size: 14px; padding: 8px; color: var(--text); }
.send.inline { margin: 0; }

/* ──── 右侧插件竖栏 ──── */
.plugin-rail { background: var(--bg-soft); border-left: 1px solid var(--border); display: flex; flex-direction: column; align-items: center; gap: 8px; padding: 10px 0; }
.pr-list { display: flex; flex-direction: column; gap: 8px; align-items: center; }
.pr-icon { width: 30px; height: 30px; border-radius: 9px; background: var(--bg-panel); border: 1px solid var(--border); display: flex; align-items: center; justify-content: center; font-size: 13px; font-weight: 700; color: var(--text-2); cursor: pointer; }
.pr-icon:hover { background: var(--bg-hover); }
.pr-icon.active { background: var(--accent); color: #1a1300; border-color: var(--accent); }
.pr-icon.plus { color: var(--text-3); font-weight: 400; font-size: 18px; }
.pr-divider { width: 18px; height: 1px; background: var(--border); margin: 2px 0; }

/* ──── toast ──── */
.toast-host { position: fixed; right: 18px; bottom: 18px; z-index: 200; display: flex; flex-direction: column; gap: 10px; }
.toast { min-width: 220px; max-width: 320px; padding: 12px 14px; background: var(--bg-panel); border: 1px solid var(--border); border-left: 3px solid var(--accent); border-radius: 10px; box-shadow: 0 10px 30px rgba(0,0,0,.12); animation: toast-in .18s ease; }
.toast-title { font-size: 14px; font-weight: 700; color: var(--text); }
.toast-msg { font-size: 12px; color: var(--text-3); margin-top: 3px; }
@keyframes toast-in { from { opacity: 0; transform: translateX(12px); } to { opacity: 1; transform: none; } }
</style>
