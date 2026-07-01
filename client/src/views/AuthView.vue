<script setup lang="ts">
/**
 * 独立登录 / 注册 / 找回密码页（方案A：把认证从 199KB 的 LiveView 巨石里抽出来）。
 *
 * 为什么独立成页：
 *   - 之前认证是 LiveView 里一段 `v-if="!loggedIn"`，登录页必须等整个 app 加载完才显示，
 *     且已登录用户刷新会「闪一下登录框」。抽成独立路由后：登录页秒开、不闪、有自己的地址。
 * 交接机制（关键）：
 *   - 用「只认证不启动客户端」的 loginNoStart/loginWithEmailNoStart：认证成功只写会话到
 *     localStorage，然后 `router.push('/')` 进主应用，由 LiveView 挂载时 restoreSession
 *     做**唯一一次**同步。既不双同步、也无需整页 reload。
 *   - 视觉与原登录块保持一致（同一套 class + 样式），只改架构不改观感。
 */
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import logoUrl from '@/assets/cosmac-logo.png'
import {
  loginNoStart, loginWithEmailNoStart,
  registerRequestCode, registerVerify,
  resetRequestCode, resetVerify,
} from '@/matrix/client'

// homeserver 基址（与 LiveView 保持一致）
const HS = 'https://hs.cosmac.cc'

const route = useRoute()
const router = useRouter()

// —— 认证态（从 LiveView 原样搬来）——
const user = ref('')
const password = ref('')
const password2 = ref('')          // 注册/找回的「确认密码」
const email = ref('')
const emailCode = ref('')
const codeCooldown = ref(0)        // 「发送验证码」倒计时（秒）
const sendingCode = ref(false)
const authMode = ref<'login' | 'register' | 'reset'>('login')
const loginBy = ref<'account' | 'email'>('account')
const error = ref('')
const info = ref('')               // 成功/提示的内联反馈（替代原 toast，保持自包含）
const loading = ref(false)

// 「添加账号」模式：从主应用点「添加账号」跳来时带 ?add=1，给个「返回当前账号」出口。
const isAdd = computed(() => route.query.add === '1')

/** 认证成功后进入主应用：优先回到守卫记下的目标地址，否则首页。 */
function proceed() {
  const to = typeof route.query.redirect === 'string' && route.query.redirect.startsWith('/')
    ? route.query.redirect
    : '/'
  router.push(to)
}

/** 发送邮箱验证码（带 60s 倒计时防连点）。 */
async function sendCode() {
  error.value = ''; info.value = ''
  const e = email.value.trim()
  if (!e) { error.value = '请先填邮箱'; return }
  if (codeCooldown.value > 0 || sendingCode.value) return
  sendingCode.value = true
  try {
    if (authMode.value === 'reset') await resetRequestCode(HS, e)
    else await registerRequestCode(HS, e)
    info.value = `验证码已发送，请查收 ${e}（含垃圾箱）`
    codeCooldown.value = 60
    const t = setInterval(() => {
      codeCooldown.value -= 1
      if (codeCooldown.value <= 0) clearInterval(t)
    }, 1000)
  } catch (err: any) {
    error.value = err?.message || '发送验证码失败'
  } finally {
    sendingCode.value = false
  }
}

/** 登录：账号走 Synapse，邮箱走 cosmac 后端；都用「只认证不启动」，成功后路由进主应用。 */
async function doLogin() {
  error.value = ''; loading.value = true
  try {
    if (loginBy.value === 'email') await loginWithEmailNoStart(HS, email.value.trim(), password.value)
    else await loginNoStart(HS, user.value.trim(), password.value)
    proceed()
  } catch (e: any) {
    error.value = e?.message || String(e)
  } finally {
    loading.value = false
  }
}

/** 注册：校验 → 验码建号 → 用同一套用户名/密码认证 → 进主应用（LiveView 会触发首次引导）。 */
async function doRegister() {
  error.value = ''
  const u = user.value.trim()
  const e = email.value.trim()
  if (!e) { error.value = '请填邮箱'; return }
  if (!emailCode.value.trim()) { error.value = '请填邮箱验证码'; return }
  if (!u || !password.value) { error.value = '请填用户名和密码'; return }
  if (password.value.length < 8) { error.value = '密码至少 8 位'; return }
  if (password.value !== password2.value) { error.value = '两次输入的密码不一致'; return }
  loading.value = true
  try {
    await registerVerify(HS, { email: e, code: emailCode.value.trim(), username: u, password: password.value })
    await loginNoStart(HS, u, password.value)
    proceed()
  } catch (err: any) {
    error.value = err?.message || String(err)
  } finally {
    loading.value = false
  }
}

/** 找回密码：验码 → 重置 → 回登录页用新密码登录（停在本页，不跳转）。 */
async function doResetPassword() {
  error.value = ''; info.value = ''
  const e = email.value.trim()
  if (!e) { error.value = '请填邮箱'; return }
  if (!emailCode.value.trim()) { error.value = '请填邮箱验证码'; return }
  if (password.value.length < 8) { error.value = '新密码至少 8 位'; return }
  if (password.value !== password2.value) { error.value = '两次输入的密码不一致'; return }
  loading.value = true
  try {
    await resetVerify(HS, { email: e, code: emailCode.value.trim(), password: password.value })
    switchAuthMode('login')
    password.value = ''
    info.value = '密码已重置，请用新密码登录'
  } catch (err: any) {
    error.value = err?.message || String(err)
  } finally {
    loading.value = false
  }
}

/** 切换登录/注册/找回密码，清掉上次的错误和相关字段。 */
function switchAuthMode(m: 'login' | 'register' | 'reset') {
  authMode.value = m
  error.value = ''
  info.value = ''
  password2.value = ''
  emailCode.value = ''
}
</script>

<template>
  <div class="login">
    <div class="login-card">
      <!-- 添加账号：给个「返回当前账号」（当前会话仍在，直接回主应用）-->
      <button v-if="isAdd" class="add-acct-back" @click="router.push('/')">← 返回当前账号</button>
      <!-- 顶部：品牌 + tab/标题 -->
      <div class="auth-top">
        <div class="brand login-brand"><img :src="logoUrl" class="brand-logo" alt="" />CosMac<span>Star</span></div>
        <div class="auth-tabs" v-if="authMode !== 'reset'">
          <button class="auth-tab" :class="{ active: authMode === 'login' }" @click="switchAuthMode('login')">登录</button>
          <button class="auth-tab" :class="{ active: authMode === 'register' }" @click="switchAuthMode('register')">注册</button>
        </div>
        <div v-else class="auth-reset-title">重置密码</div>
      </div>

      <!-- 中部：表单字段 -->
      <div class="auth-fields">
        <!-- ===== 登录：账号 / 邮箱 二选一 ===== -->
        <template v-if="authMode === 'login'">
          <div class="auth-subtabs">
            <button class="auth-subtab" :class="{ active: loginBy === 'account' }" @click="loginBy = 'account'">账号登录</button>
            <button class="auth-subtab" :class="{ active: loginBy === 'email' }" @click="loginBy = 'email'">邮箱登录</button>
          </div>
          <input v-if="loginBy === 'account'" v-model="user" name="login-username" autocomplete="username" placeholder="用户名" @keyup.enter="doLogin" />
          <input v-else v-model="email" type="email" name="login-email" autocomplete="email" placeholder="邮箱" @keyup.enter="doLogin" />
          <input v-model="password" type="password" autocomplete="current-password" placeholder="密码" @keyup.enter="doLogin" />
        </template>

        <!-- ===== 注册 / 找回密码 ===== -->
        <template v-else>
          <div class="auth-code-row">
            <input v-model="email" type="email" name="reg-email" autocomplete="email" placeholder="邮箱" />
            <button class="auth-code-btn" :disabled="codeCooldown > 0 || sendingCode || !email.trim()" @click="sendCode">
              {{ codeCooldown > 0 ? `${codeCooldown}s` : (sendingCode ? '发送中…' : '发送验证码') }}
            </button>
          </div>
          <input v-model="emailCode" name="reg-otp" autocomplete="one-time-code" inputmode="numeric" maxlength="6"
                 placeholder="6 位验证码（填邮件里的数字）"
                 @keyup.enter="authMode === 'reset' ? doResetPassword() : doRegister()" />
          <input v-if="authMode === 'register'" v-model="user" name="reg-username" autocomplete="username" placeholder="用户名" />
          <input v-model="password" type="password" autocomplete="new-password"
                 :placeholder="authMode === 'reset' ? '新密码（至少 8 位）' : '密码（至少 8 位）'"
                 @keyup.enter="authMode === 'reset' ? doResetPassword() : doRegister()" />
          <input v-model="password2" type="password" autocomplete="new-password"
                 :placeholder="authMode === 'reset' ? '确认新密码' : '确认密码'"
                 @keyup.enter="authMode === 'reset' ? doResetPassword() : doRegister()" />
        </template>
      </div>

      <!-- 底部：提交按钮 + 提示/错误 + 切换链接 -->
      <div class="auth-bottom">
        <button v-if="authMode === 'login'" class="login-btn" :disabled="loading" @click="doLogin">{{ loading ? '登录中…' : '登录' }}</button>
        <button v-else-if="authMode === 'register'" class="login-btn" :disabled="loading" @click="doRegister">{{ loading ? '注册中…' : '注册并进入' }}</button>
        <button v-else class="login-btn" :disabled="loading" @click="doResetPassword">{{ loading ? '重置中…' : '重置密码' }}</button>
        <p class="ok" v-if="info">{{ info }}</p>
        <p class="err" v-if="error">{{ authMode === 'login' ? '登录失败' : (authMode === 'reset' ? '重置失败' : '注册失败') }}：{{ error }}</p>
        <p class="auth-switch" v-if="authMode === 'login'">还没有账号？<a @click="switchAuthMode('register')">注册一个</a> · <a @click="switchAuthMode('reset')">忘记密码？</a></p>
        <p class="auth-switch" v-else-if="authMode === 'register'">已有账号？<a @click="switchAuthMode('login')">去登录</a></p>
        <p class="auth-switch" v-else>想起来了？<a @click="switchAuthMode('login')">返回登录</a></p>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 与原 LiveView 登录块完全一致的样式（搬迁，不改观感）。CSS 变量来自全局 tokens.css。 */
.login { height: 100vh; display: flex; align-items: center; justify-content: center; background: linear-gradient(180deg, var(--bg-panel), var(--bg-soft)); font-family: var(--font-body); }
.login-card { width: 640px; max-width: 92vw; min-height: 502px; box-sizing: border-box; display: flex; flex-direction: column; justify-content: space-between; gap: 20px; padding: 40px; background: #fff; border: 1px solid var(--border); border-radius: 16px; box-shadow: 0 20px 60px rgba(0,0,0,.08); }
.auth-top { display: flex; flex-direction: column; gap: 16px; }
.auth-fields { display: flex; flex-direction: column; gap: 14px; }
.auth-bottom { display: flex; flex-direction: column; gap: 12px; }
.login-brand { font-weight: 800; font-size: 22px; color: var(--text); display: inline-flex; align-items: center; gap: 8px; }
.login-brand span { color: var(--accent); margin-left: 4px; }
.brand-logo { width: 26px; height: 26px; object-fit: contain; border-radius: 6px; }
.login-card input { padding: 13px 15px; border: 1px solid var(--border); border-radius: 10px; font-size: 15px; }
.login-btn { padding: 14px; border: 0; border-radius: 10px; background: var(--action); color: #fff; font-size: 15px; font-weight: 600; cursor: pointer; }
.login-btn:disabled { opacity: .6; cursor: default; }
.auth-tabs { display: flex; gap: 4px; padding: 4px; background: var(--bg, #f1efe9); border: 1px solid var(--border); border-radius: 10px; }
.auth-tab { flex: 1; padding: 10px; border: 0; background: transparent; color: var(--text-3); font-size: 15px; font-weight: 600; border-radius: 8px; cursor: pointer; }
.auth-tab.active { background: #fff; color: var(--text); box-shadow: 0 1px 3px rgba(0,0,0,.08); }
.auth-subtabs { display: flex; gap: 18px; padding: 0 2px; }
.auth-subtab { border: 0; background: transparent; color: var(--text-3); font-size: 14px; font-weight: 600; padding: 2px 0 6px; cursor: pointer; border-bottom: 2px solid transparent; }
.auth-subtab.active { color: var(--accent); border-bottom-color: var(--accent); }
.auth-code-row { display: flex; gap: 8px; }
.auth-code-row input { flex: 1; min-width: 0; }
.auth-code-btn { flex-shrink: 0; padding: 0 12px; border: 1px solid var(--border); background: var(--bg-panel, #fff); color: var(--accent); font-size: 13px; font-weight: 600; border-radius: 10px; cursor: pointer; white-space: nowrap; }
.auth-code-btn:disabled { opacity: .5; cursor: default; color: var(--text-3); }
.auth-reset-title { font-size: 16px; font-weight: 700; color: var(--text); text-align: center; padding: 2px 0; }
.auth-switch { color: var(--text-3); font-size: 13px; text-align: center; margin: 0; }
.auth-switch a { color: var(--accent); cursor: pointer; font-weight: 600; }
.auth-switch a:hover { text-decoration: underline; }
.err { color: var(--danger); font-size: 13px; }
.ok { color: var(--accent); font-size: 13px; margin: 0; }
.add-acct-back { align-self: flex-start; border: none; background: transparent; color: var(--text-3); font-size: 13px; cursor: pointer; padding: 0; }
</style>
