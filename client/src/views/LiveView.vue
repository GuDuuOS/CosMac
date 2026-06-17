<!-- CosMac Star 真实客户端驾驶舱：连 Synapse。
     左=真实频道；中=频道消息流(含 cosmac.card 富卡)；右="中枢 AI"面板(与主 AI 的私聊)。 -->
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
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

const HS = 'https://hs.cosmac.cc'

const user = ref('admin')
const password = ref('')
const loggedIn = ref(false)
const me = ref('')
const error = ref('')
const loading = ref(false)

const rooms = ref<LiveRoom[]>([])
const currentRoom = ref('')
const msgs = ref<LiveMsg[]>([])
const draft = ref('')

// 右侧中枢 AI 面板（= 和主 AI 的私聊）
const aiRoom = ref('')
const aiMsgs = ref<LiveMsg[]>([])
const aiDraft = ref('')
const aiOpen = ref(true)

const currentName = computed(
  () => rooms.value.find((r) => r.id === currentRoom.value)?.name || '',
)

function refresh() {
  rooms.value = listRooms()
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
}

function initials(name: string) {
  return name.replace(/^@/, '').slice(0, 1).toUpperCase()
}
function isMe(s: string) {
  return s === me.value
}

onMounted(async () => {
  loading.value = true
  try {
    const uid = await restoreSession()
    if (uid) await afterLogin(uid)
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <!-- 登录 -->
  <div v-if="!loggedIn" class="login">
    <div class="login-card">
      <div class="logo">CosMac<span>Star</span></div>
      <input v-model="user" placeholder="用户名（如 admin）" />
      <input v-model="password" type="password" placeholder="密码" @keyup.enter="doLogin" />
      <button :disabled="loading" @click="doLogin">{{ loading ? '登录中…' : '登录' }}</button>
      <p class="err" v-if="error">登录失败：{{ error }}</p>
      <p class="hint">连接后端 {{ HS }}</p>
    </div>
  </div>

  <!-- 驾驶舱 -->
  <div v-else class="shell">
    <header class="topbar">
      <div class="brand">CosMac<span>Star</span></div>
      <div class="spacer" />
      <button class="ghost" @click="aiOpen = !aiOpen">{{ aiOpen ? '收起 AI' : '中枢 AI' }}</button>
      <div class="user">{{ me }}</div>
      <button class="ghost" @click="doLogout">退出</button>
    </header>

    <div class="body" :class="{ 'no-ai': !aiOpen }">
      <!-- 左：频道 -->
      <aside class="sidebar">
        <div class="side-title">频道</div>
        <div
          v-for="r in rooms"
          :key="r.id"
          class="chan"
          :class="{ active: r.id === currentRoom }"
          @click="openRoom(r.id)"
        >
          <span class="hash">#</span>{{ r.name }}
        </div>
        <p v-if="!rooms.length" class="hint pad">还没有频道</p>
      </aside>

      <!-- 中：频道消息 -->
      <main class="main">
        <div v-if="currentRoom" class="chan-head"># {{ currentName }}</div>
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
        <div v-if="currentRoom" class="composer">
          <input v-model="draft" placeholder="说点什么；叫主 AI 试：CosMac 建专班 测试专班" @keyup.enter="send" />
          <button @click="send">发送</button>
        </div>
      </main>

      <!-- 右：中枢 AI 面板（与主 AI 私聊，私聊里它对每句话都回）-->
      <aside class="ai-panel" v-if="aiOpen">
        <div class="ai-head">
          <div class="ai-dot" /> 中枢 AI · CosMac Star
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
        <div class="composer">
          <input v-model="aiDraft" placeholder="一句话下达目标…" @keyup.enter="aiSend" />
          <button @click="aiSend">发送</button>
        </div>
      </aside>
    </div>
  </div>
</template>

<style scoped>
* { box-sizing: border-box; }
.login { height: 100vh; display: flex; align-items: center; justify-content: center; background: linear-gradient(180deg, #fffdfa, #f4efe8); font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }
.login-card { width: 320px; display: flex; flex-direction: column; gap: 12px; padding: 28px; background: #fff; border: 1px solid #eee; border-radius: 16px; box-shadow: 0 20px 60px rgba(0,0,0,.08); }
.logo, .brand { font-weight: 800; font-size: 22px; color: #15120f; }
.logo span, .brand span { color: #f59e0b; margin-left: 4px; }
.login-card input { padding: 11px 13px; border: 1px solid #ddd; border-radius: 10px; font-size: 14px; }
.login-card button { padding: 11px; border: 0; border-radius: 10px; background: #15120f; color: #fff; font-size: 14px; cursor: pointer; }
.err { color: #d94f5c; font-size: 13px; }
.hint { color: #9b948c; font-size: 12px; }
.hint.pad { padding: 16px; }

.shell { height: 100vh; display: flex; flex-direction: column; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; color: #15120f; }
.topbar { display: flex; align-items: center; gap: 12px; height: 56px; padding: 0 16px; border-bottom: 1px solid #eee; background: #fffdfa; }
.brand { font-size: 18px; }
.spacer { flex: 1; }
.user { font-size: 12px; color: #888; }
.ghost { border: 1px solid #ddd; background: #fff; border-radius: 8px; padding: 6px 12px; cursor: pointer; font-size: 13px; }

.body { flex: 1; display: grid; grid-template-columns: 240px 1fr 360px; min-height: 0; }
.body.no-ai { grid-template-columns: 240px 1fr; }
.sidebar { border-right: 1px solid #eee; overflow: auto; padding: 12px 8px; background: #faf7f2; }
.side-title { font-size: 11px; font-weight: 800; color: #b3aaa0; letter-spacing: .08em; padding: 6px 10px; text-transform: uppercase; }
.chan { display: flex; align-items: center; padding: 8px 10px; border-radius: 8px; cursor: pointer; font-size: 14px; color: #4a443e; }
.chan:hover { background: #f0ebe3; }
.chan.active { background: #15120f; color: #fff; }
.hash { color: #c0b8ad; margin-right: 6px; }
.chan.active .hash { color: #8a8278; }

.main { display: flex; flex-direction: column; min-height: 0; }
.chan-head { height: 52px; display: flex; align-items: center; padding: 0 18px; border-bottom: 1px solid #eee; font-weight: 700; }
.stream { flex: 1; overflow: auto; padding: 18px; display: flex; flex-direction: column; gap: 14px; background: #fff; }
.row { display: flex; gap: 10px; max-width: 760px; }
.row.mine { flex-direction: row-reverse; align-self: flex-end; }
.avatar { width: 34px; height: 34px; border-radius: 50%; background: #15120f; color: #fff; display: flex; align-items: center; justify-content: center; font-size: 13px; font-weight: 700; flex: 0 0 auto; }
.row.mine .avatar { background: #f59e0b; color: #1a1300; }
.bubble-wrap { min-width: 0; }
.who { font-size: 12px; color: #999; margin-bottom: 3px; }
.row.mine .who { text-align: right; }
.bubble { background: #f2eee8; padding: 9px 13px; border-radius: 12px; white-space: pre-wrap; word-break: break-word; }
.row.mine .bubble { background: #fde7c2; }
.card { margin-top: 8px; border: 1px solid #e7e0d6; border-radius: 12px; padding: 14px; background: #fffdf8; max-width: 440px; }
.card-title { font-weight: 700; }
.card-sub { font-size: 12px; color: #888; margin: 2px 0 10px; }
.card-row { display: flex; justify-content: space-between; padding: 6px 0; border-top: 1px dashed #eee; font-size: 14px; }
.card-row .ai { color: #5879ff; font-weight: 600; }
.card-row .human { color: #c2761f; font-weight: 600; }
.composer { display: flex; gap: 8px; padding: 12px 16px; border-top: 1px solid #eee; background: #fffdfa; }
.composer input { flex: 1; padding: 11px 14px; border: 1px solid #ddd; border-radius: 12px; font-size: 14px; }
.composer button { padding: 11px 18px; border: 0; border-radius: 12px; background: #15120f; color: #fff; cursor: pointer; }

/* 右侧中枢 AI 面板 */
.ai-panel { border-left: 1px solid #eee; display: flex; flex-direction: column; min-height: 0; background: #fcfbf8; }
.ai-head { height: 52px; display: flex; align-items: center; gap: 8px; padding: 0 16px; border-bottom: 1px solid #eee; font-weight: 700; font-size: 14px; }
.ai-dot { width: 8px; height: 8px; border-radius: 50%; background: #22c55e; box-shadow: 0 0 0 4px rgba(34,197,94,.16); }
.ai-panel .stream { padding: 14px; }
.ai-panel .row { max-width: 100%; }
.ai-panel .bubble { background: #fff; border: 1px solid #eee; }
.ai-panel .row.mine .bubble { background: #fde7c2; border: 0; }
</style>
