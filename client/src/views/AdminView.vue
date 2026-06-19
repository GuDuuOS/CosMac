<template>
  <div class="admin-view channel-view">
    <!-- 关闭管理后台，回到工作台 -->
    <button class="adm-close" title="关闭" @click="emit('close')">✕</button>
    <!-- 左侧管理菜单（用户管理已就绪，其余占位，后续逐块填） -->
    <aside class="adm-nav">
      <div class="adm-brand">
        <span class="adm-logo">⚙</span>
        <div>
          <div class="adm-title">管理后台</div>
          <div class="adm-sub">CosMac Star 运营控制台</div>
        </div>
      </div>
      <nav class="adm-menu">
        <button class="adm-mi" :class="{ active: tab === 'users' }" @click="tab = 'users'">
          <span class="adm-mi-ic">👤</span> 用户管理
        </button>
        <button class="adm-mi" :class="{ active: tab === 'rooms' }" @click="switchToRooms">
          <span class="adm-mi-ic">＃</span> 频道管理
        </button>
        <button class="adm-mi" :class="{ active: tab === 'ai' }" @click="switchToAi">
          <span class="adm-mi-ic">🤖</span> AI 配置
        </button>
        <button class="adm-mi" :class="{ active: tab === 'skills' }" @click="switchToSkills">
          <span class="adm-mi-ic">🛠</span> 技能库
        </button>
        <button class="adm-mi" :class="{ active: tab === 'overview' }" @click="switchToOverview">
          <span class="adm-mi-ic">📊</span> 数据概览
        </button>
      </nav>
    </aside>

    <!-- 右侧内容区 -->
    <section class="adm-main">
      <!-- 1) 权限校验中 -->
      <div v-if="state === 'checking'" class="adm-center">
        <div class="adm-spin" /> 正在校验管理员权限…
      </div>

      <!-- 2) 无权限 -->
      <div v-else-if="state === 'denied'" class="adm-center adm-denied">
        <div class="adm-denied-ic">🔒</div>
        <div class="adm-denied-t">无法进入管理后台</div>
        <div class="adm-denied-d">
          可能原因：① 当前账号不是服务器管理员（请用 <code>@admin</code> 登录）；
          ② 服务器未对管理接口 <code>/_synapse/admin</code> 开放跨域（CORS），
          导致浏览器无法调用。若你确认是管理员，多半是第 ② 种，需在 hs 的 nginx 放开 CORS。
        </div>
        <button class="adm-btn" @click="check">重新校验</button>
      </div>

      <!-- 3) 已是管理员：按 tab 显示用户管理 / 频道管理 -->
      <template v-else-if="tab === 'users'">
        <header class="adm-head">
          <div>
            <h1 class="adm-h1">用户管理</h1>
            <p class="adm-hint">
              共 {{ users.length }} 个账号 ·
              管理员 {{ users.filter(u => u.admin).length }} ·
              已停用 {{ users.filter(u => u.deactivated).length }}
            </p>
          </div>
          <div class="adm-actions">
            <button class="adm-btn ghost" :disabled="loading" @click="loadUsers">
              {{ loading ? '刷新中…' : '刷新' }}
            </button>
            <button class="adm-btn" @click="showCreate = true">＋ 新建用户</button>
          </div>
        </header>

        <div v-if="loading" class="adm-center"><div class="adm-spin" /> 加载用户列表…</div>

        <table v-else class="adm-table">
          <thead>
            <tr>
              <th>用户</th>
              <th>角色</th>
              <th>状态</th>
              <th class="adm-ops-h">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="u in users" :key="u.id" :class="{ off: u.deactivated }">
              <td>
                <div class="adm-user">
                  <span class="adm-ava">{{ avatarOf(u) }}</span>
                  <div class="adm-u-id">
                    <div class="adm-u-name">
                      {{ u.name }}
                      <span v-if="u.isBot" class="adm-tag bot">中枢AI</span>
                    </div>
                    <div class="adm-u-handle">{{ u.id }}</div>
                  </div>
                </div>
              </td>
              <td>
                <span class="adm-tag" :class="u.admin ? 'admin' : 'member'">
                  {{ u.admin ? '管理员' : '成员' }}
                </span>
              </td>
              <td>
                <span class="adm-tag" :class="u.deactivated ? 'off' : 'ok'">
                  {{ u.deactivated ? '已停用' : '正常' }}
                </span>
              </td>
              <td class="adm-ops">
                <button class="adm-op" :disabled="u.isBot || busy === u.id" @click="toggleAdmin(u)">
                  {{ u.admin ? '撤销管理员' : '设为管理员' }}
                </button>
                <button class="adm-op" :disabled="busy === u.id" @click="doResetPassword(u)">
                  重置密码
                </button>
                <button
                  v-if="!u.deactivated"
                  class="adm-op danger"
                  :disabled="u.isBot || busy === u.id"
                  @click="doDeactivate(u)"
                >停用</button>
                <button v-else class="adm-op" :disabled="busy === u.id" @click="doReactivate(u)">
                  恢复
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </template>

      <!-- 频道管理面板 -->
      <template v-else-if="tab === 'rooms'">
        <header class="adm-head">
          <div>
            <h1 class="adm-h1">频道管理</h1>
            <p class="adm-hint">
              全服共 {{ rooms.length }} 个频道 ·
              公开 {{ rooms.filter(r => r.isPublic).length }} ·
              加密 {{ rooms.filter(r => r.encrypted).length }}
            </p>
          </div>
          <div class="adm-actions">
            <button class="adm-btn ghost" :disabled="roomsLoading" @click="loadRooms">
              {{ roomsLoading ? '刷新中…' : '刷新' }}
            </button>
          </div>
        </header>

        <div v-if="roomsLoading" class="adm-center"><div class="adm-spin" /> 加载频道列表…</div>

        <table v-else class="adm-table">
          <thead>
            <tr>
              <th>频道</th>
              <th>成员</th>
              <th>类型</th>
              <th class="adm-ops-h">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in rooms" :key="r.id">
              <td>
                <div class="adm-user">
                  <span class="adm-ava">{{ (r.name || '#').charAt(0).toUpperCase() }}</span>
                  <div class="adm-u-id">
                    <div class="adm-u-name">{{ r.name }}</div>
                    <div class="adm-u-handle">{{ r.alias || r.id }}</div>
                  </div>
                </div>
              </td>
              <td>{{ r.members }}<span class="adm-dim"> / 本服 {{ r.localMembers }}</span></td>
              <td>
                <span class="adm-tag" :class="r.isPublic ? 'admin' : 'member'">
                  {{ r.isPublic ? '公开' : '私有' }}
                </span>
                <span v-if="r.encrypted" class="adm-tag bot" title="端到端加密">🔒 加密</span>
              </td>
              <td class="adm-ops">
                <button class="adm-op" :disabled="roomBusy === r.id" @click="viewMembers(r)">
                  查看成员
                </button>
                <button class="adm-op danger" :disabled="roomBusy === r.id" @click="doDeleteRoom(r)">
                  删除
                </button>
              </td>
            </tr>
            <tr v-if="!rooms.length"><td colspan="4" class="adm-empty">暂无频道</td></tr>
          </tbody>
        </table>
      </template>

      <!-- AI 配置面板 -->
      <template v-else-if="tab === 'ai'">
        <header class="adm-head">
          <div>
            <h1 class="adm-h1">AI 配置</h1>
            <p class="adm-hint">
              改主 AI 的人设/模型/工具开关 · 保存后写入控制室，bot 约 20 秒内热生效（无需重启）
            </p>
          </div>
          <div class="adm-actions">
            <button class="adm-btn ghost" :disabled="aiLoading || aiSaving" @click="loadAi">
              {{ aiLoading ? '加载中…' : '重新加载' }}
            </button>
            <button class="adm-btn" :disabled="aiLoading || aiSaving" @click="saveAi">
              {{ aiSaving ? '保存中…' : '保存' }}
            </button>
          </div>
        </header>

        <div v-if="aiLoading" class="adm-center"><div class="adm-spin" /> 加载配置…</div>

        <div v-else class="adm-form">
          <!-- 模型后端：选 provider + 模型 id。API Key 不在网页配，只在服务端 -->
          <label class="adm-field">
            <span>模型后端</span>
            <select v-model="aiForm.provider">
              <option v-for="p in AI_PROVIDERS" :key="p.value" :value="p.value">{{ p.label }}</option>
            </select>
            <em class="adm-note">选「默认」= 用服务器配置的后端；选某家则切到它（需服务器已配好它的 API Key）。</em>
          </label>

          <template v-if="aiForm.provider">
            <label class="adm-field">
              <span>模型 id</span>
              <input v-model.trim="aiForm.model" :placeholder="providerMeta.modelPlaceholder" />
              <em class="adm-note">⚠️ 填错会让 AI 回话报错；DeepSeek/Gemini 填方舟/Google 的模型 id 或接入点。</em>
            </label>
            <em class="adm-note">🔒 出于安全，<b>API Key 不在网页配置</b>——密钥只在服务器环境变量/Secret&nbsp;Manager 里设（Matrix 事件无法加密，存进去会明文泄露）。切到服务器没配 key 的后端，AI 将无法回话。</em>
          </template>

          <label class="adm-field">
            <span>主 AI 人设（system prompt）</span>
            <textarea v-model="aiForm.system_prompt" rows="5"
              placeholder="留空 = 用服务器默认人设" />
          </label>

          <div class="adm-field">
            <span>工具开关（关掉的工具主 AI 将无法调用）</span>
            <div class="adm-tools">
              <label v-for="t in AI_TOOL_CATALOG" :key="t.name" class="adm-tool">
                <input type="checkbox" :checked="isToolOn(t.name)" @change="toggleTool(t.name, ($event.target as HTMLInputElement).checked)" />
                <span class="adm-tool-l">{{ t.label }}</span>
                <code>{{ t.name }}</code>
              </label>
            </div>
            <em class="adm-note">全部勾选 = 不限制（默认）。</em>
          </div>
        </div>
      </template>

      <!-- 技能库面板：编辑全局技能（写控制室 state event，主 AI 注入到所有群）-->
      <template v-else-if="tab === 'skills'">
        <header class="adm-head">
          <div>
            <h1 class="adm-h1">技能库</h1>
            <p class="adm-hint">
              全局技能 · 主 AI 在所有群回话时按需运用 · 保存后约 20 秒内热生效（无需重启）
            </p>
          </div>
          <div class="adm-actions">
            <button class="adm-btn ghost" :disabled="skLoading || skSaving" @click="loadSkills">
              {{ skLoading ? '加载中…' : '重新加载' }}
            </button>
            <button class="adm-btn" :disabled="skLoading || skSaving" @click="startAddSkill">＋ 新建技能</button>
          </div>
        </header>

        <div v-if="skLoading" class="adm-center"><div class="adm-spin" /> 加载技能…</div>

        <div v-else class="adm-form">
          <!-- 编辑/新建表单 -->
          <div v-if="skEditing" class="adm-skill-edit">
            <label class="adm-field">
              <span>标识 slug（英文/数字/-，全局唯一）</span>
              <input v-model.trim="skForm.slug" :disabled="skForm._isEdit" placeholder="weekly-report" />
            </label>
            <label class="adm-field">
              <span>名称</span>
              <input v-model.trim="skForm.name" placeholder="周报" />
            </label>
            <label class="adm-field">
              <span>一句话说明</span>
              <input v-model.trim="skForm.description" placeholder="生成本周数据周报" />
            </label>
            <label class="adm-field">
              <span>技能正文（喂给主 AI 的提示/步骤）</span>
              <textarea v-model="skForm.instructions" rows="5" placeholder="按…步骤生成…" />
            </label>
            <label class="adm-tool">
              <input type="checkbox" v-model="skForm.enabled" />
              <span class="adm-tool-l">启用</span>
            </label>
            <div class="adm-actions">
              <button class="adm-btn ghost" :disabled="skSaving" @click="skEditing = false">取消</button>
              <button class="adm-btn" :disabled="skSaving || !skForm.slug" @click="saveSkill">
                {{ skSaving ? '保存中…' : '保存' }}
              </button>
            </div>
          </div>

          <!-- 技能列表 -->
          <p v-if="!skills.length" class="adm-hint">还没有全局技能。点右上「新建技能」加一个。</p>
          <table v-else class="adm-table">
            <thead>
              <tr><th>标识</th><th>名称</th><th>说明</th><th>状态</th><th>操作</th></tr>
            </thead>
            <tbody>
              <tr v-for="s in skills" :key="s.slug">
                <td><code>{{ s.slug }}</code></td>
                <td>{{ s.name || '—' }}</td>
                <td class="adm-skill-desc">{{ s.description || '—' }}</td>
                <td>
                  <span class="adm-badge" :class="{ on: s.enabled }">{{ s.enabled ? '启用' : '停用' }}</span>
                </td>
                <td class="adm-row-actions">
                  <button class="adm-btn ghost sm" :disabled="skSaving" @click="startEditSkill(s)">编辑</button>
                  <button class="adm-btn ghost sm" :disabled="skSaving" @click="toggleSkill(s)">{{ s.enabled ? '停用' : '启用' }}</button>
                  <button class="adm-btn ghost sm danger" :disabled="skSaving" @click="removeSkill(s)">删除</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>

      <!-- 数据概览面板 -->
      <template v-else-if="tab === 'overview'">
        <header class="adm-head">
          <div>
            <h1 class="adm-h1">数据概览</h1>
            <p class="adm-hint">
              平台实时概况 · 数据来自 Synapse Admin API
              <span v-if="ov.version"> · 服务端 {{ ov.version }}</span>
            </p>
          </div>
          <div class="adm-actions">
            <button class="adm-btn ghost" :disabled="ovLoading" @click="loadOverview">
              {{ ovLoading ? '刷新中…' : '刷新' }}
            </button>
          </div>
        </header>

        <div v-if="ovLoading" class="adm-center"><div class="adm-spin" /> 统计中…</div>

        <template v-else>
          <!-- KPI 卡片 -->
          <div class="adm-kpis">
            <div class="adm-kpi">
              <div class="adm-kpi-v">{{ ov.userTotal }}</div>
              <div class="adm-kpi-l">账号总数</div>
              <div class="adm-kpi-s">管理员 {{ ov.adminCount }} · 停用 {{ ov.deactivated }}</div>
            </div>
            <div class="adm-kpi">
              <div class="adm-kpi-v">{{ ov.roomTotal }}</div>
              <div class="adm-kpi-l">频道总数</div>
              <div class="adm-kpi-s">公开 {{ ov.publicRooms }} · 加密 {{ ov.encryptedRooms }}</div>
            </div>
            <div class="adm-kpi">
              <div class="adm-kpi-v">{{ ov.memberSum }}</div>
              <div class="adm-kpi-l">成员人次合计</div>
              <div class="adm-kpi-s">平均每频道 {{ ov.avgMembers }}</div>
            </div>
            <div class="adm-kpi">
              <div class="adm-kpi-v">{{ ov.activeRooms }}</div>
              <div class="adm-kpi-l">活跃频道</div>
              <div class="adm-kpi-s">成员 ≥ 2 的频道数</div>
            </div>
          </div>

          <!-- 最活跃频道 Top -->
          <h2 class="adm-h2">最活跃频道 Top {{ ov.topRooms.length }}</h2>
          <table class="adm-table">
            <thead>
              <tr><th>频道</th><th>成员</th><th>类型</th></tr>
            </thead>
            <tbody>
              <tr v-for="r in ov.topRooms" :key="r.id">
                <td>
                  <div class="adm-user">
                    <span class="adm-ava">{{ (r.name || '#').charAt(0).toUpperCase() }}</span>
                    <div class="adm-u-id">
                      <div class="adm-u-name">{{ r.name }}</div>
                      <div class="adm-u-handle">{{ r.alias || r.id }}</div>
                    </div>
                  </div>
                </td>
                <td>{{ r.members }}</td>
                <td>
                  <span class="adm-tag" :class="r.isPublic ? 'admin' : 'member'">
                    {{ r.isPublic ? '公开' : '私有' }}
                  </span>
                </td>
              </tr>
              <tr v-if="!ov.topRooms.length"><td colspan="3" class="adm-empty">暂无数据</td></tr>
            </tbody>
          </table>
        </template>
      </template>
    </section>

    <!-- 新建用户弹窗 -->
    <div v-if="showCreate" class="adm-mask" @click.self="showCreate = false">
      <div class="adm-modal">
        <div class="adm-modal-h">新建用户</div>
        <label class="adm-field">
          <span>用户名</span>
          <input v-model.trim="form.username" placeholder="如 alice（自动补 :{{ domain }}）" />
        </label>
        <label class="adm-field">
          <span>显示名（可选）</span>
          <input v-model.trim="form.displayname" placeholder="如 爱丽丝" />
        </label>
        <label class="adm-field">
          <span>初始密码</span>
          <input v-model="form.password" type="text" placeholder="至少 8 位" />
        </label>
        <div class="adm-modal-f">
          <button class="adm-btn ghost" @click="showCreate = false">取消</button>
          <button class="adm-btn" :disabled="!canCreate || busy === 'create'" @click="doCreate">
            {{ busy === 'create' ? '创建中…' : '创建' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 频道成员弹窗 -->
    <div v-if="membersOf" class="adm-mask" @click.self="membersOf = null">
      <div class="adm-modal">
        <div class="adm-modal-h">{{ membersOf.name }} · 成员</div>
        <div class="adm-mlist">
          <div v-if="membersLoading" class="adm-center"><div class="adm-spin" /> 加载中…</div>
          <template v-else>
            <div v-for="m in memberList" :key="m" class="adm-mrow">
              <span class="adm-ava sm">{{ m.replace(/^@/, '').charAt(0).toUpperCase() }}</span>
              <span class="adm-mid">{{ m }}</span>
            </div>
            <div v-if="!memberList.length" class="adm-empty">没有成员</div>
          </template>
        </div>
        <div class="adm-modal-f">
          <button class="adm-btn ghost" @click="membersOf = null">关闭</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import {
  isServerAdmin,
  listUsers,
  createUser,
  deactivateUser,
  reactivateUser,
  resetPassword,
  setUserAdmin,
  serverName,
  listAdminRooms,
  getRoomMembers,
  deleteRoom,
  getServerVersion,
  getAiConfig,
  setAiConfig,
  getGlobalSkills,
  setGlobalSkills,
  AI_TOOL_CATALOG,
  AI_PROVIDERS,
  type AdminUser,
  type AdminRoom,
  type GlobalSkill,
} from '@/matrix/client'
import { useToast } from '@/composables/useToast'

// 作为覆盖层使用：关闭时通知父组件（LiveView）收起
const emit = defineEmits<{ (e: 'close'): void }>()

const { success, warn } = useToast()

// 当前管理模块：用户管理 / 频道管理 / AI 配置 / 技能库 / 数据概览
const tab = ref<'users' | 'rooms' | 'ai' | 'skills' | 'overview'>('users')

// 页面状态机：checking 校验中 / denied 无权限 / ok 已是管理员
const state = ref<'checking' | 'denied' | 'ok'>('checking')
const loading = ref(false)
const users = ref<AdminUser[]>([])
// busy 存"正在操作的用户 id"或 'create'，用于禁用对应按钮、防重复点击
const busy = ref<string | null>(null)

const domain = computed(() => serverName())

// 新建用户表单
const showCreate = ref(false)
const form = reactive({ username: '', displayname: '', password: '' })
const canCreate = computed(
  () => form.username.length > 0 && form.password.length >= 8,
)

/** 取头像首字（显示名首字，没有就用 id 首字母） */
function avatarOf(u: AdminUser): string {
  const s = u.name || u.id.replace(/^@/, '')
  return s.charAt(0).toUpperCase()
}

/** 进页面先校验管理员；是管理员才拉用户列表 */
async function check() {
  state.value = 'checking'
  const ok = await isServerAdmin()
  if (!ok) { state.value = 'denied'; return }
  state.value = 'ok'
  await loadUsers()
}

async function loadUsers() {
  loading.value = true
  try {
    users.value = await listUsers()
  } catch (e: any) {
    warn('加载失败', e?.message || '无法获取用户列表')
  } finally {
    loading.value = false
  }
}

async function toggleAdmin(u: AdminUser) {
  const next = !u.admin
  if (!confirm(`确认${next ? '把' : '撤销'} ${u.name} ${next ? '设为管理员' : '的管理员权限'}？`)) return
  busy.value = u.id
  try {
    const synced = await setUserAdmin(u.id, next)
    u.admin = next // 服务器管理员身份已改成功（无论控制室是否同步）
    if (next) {
      success('已更新', `${u.name} 现在是管理员`)
    } else if (synced) {
      success('已撤为普通成员', `${u.name} 的控制室写权限将由主 AI 同步移除`)
    } else {
      // 控制室同步没成功 → 不能假装撤干净了，明确提示重试
      warn('已撤管理员，但控制室同步失败', `请重试，否则 ${u.name} 可能仍能写 AI 配置`)
    }
  } catch (e: any) {
    warn('操作失败', e?.message || '权限修改失败')
  } finally {
    busy.value = null
  }
}

async function doResetPassword(u: AdminUser) {
  const pwd = prompt(`给 ${u.name} 设置新密码（至少 8 位，会同时踢下线所有设备）：`)
  if (!pwd) return
  if (pwd.length < 8) { warn('密码太短', '至少 8 位'); return }
  busy.value = u.id
  try {
    await resetPassword(u.id, pwd)
    success('密码已重置', `${u.name} 需用新密码重新登录`)
  } catch (e: any) {
    warn('重置失败', e?.message || '无法重置密码')
  } finally {
    busy.value = null
  }
}

async function doDeactivate(u: AdminUser) {
  if (!confirm(`确认停用 ${u.name}？停用后该账号无法登录（可恢复）。`)) return
  busy.value = u.id
  try {
    await deactivateUser(u.id)
    u.deactivated = true
    success('已停用', `${u.name} 已无法登录`)
  } catch (e: any) {
    warn('停用失败', e?.message || '无法停用账号')
  } finally {
    busy.value = null
  }
}

async function doReactivate(u: AdminUser) {
  const pwd = prompt(`恢复 ${u.name} 需同时设新密码（Synapse 要求，至少 8 位）：`)
  if (!pwd) return
  if (pwd.length < 8) { warn('密码太短', '至少 8 位'); return }
  busy.value = u.id
  try {
    await reactivateUser(u.id, pwd)
    u.deactivated = false
    success('已恢复', `${u.name} 可用新密码登录了`)
  } catch (e: any) {
    warn('恢复失败', e?.message || '无法恢复账号')
  } finally {
    busy.value = null
  }
}

async function doCreate() {
  busy.value = 'create'
  try {
    const uid = await createUser(form.username, form.password, form.displayname || undefined)
    success('已创建', uid)
    showCreate.value = false
    form.username = ''; form.displayname = ''; form.password = ''
    await loadUsers()
  } catch (e: any) {
    warn('创建失败', e?.message || '无法创建账号')
  } finally {
    busy.value = null
  }
}

/* —— 频道管理 —— */
const rooms = ref<AdminRoom[]>([])
const roomsLoading = ref(false)
const roomsLoaded = ref(false)        // 懒加载：首次切到频道 tab 才拉
const roomBusy = ref<string | null>(null)
// 成员弹窗：membersOf 为当前查看的房间，null 表示关闭
const membersOf = ref<AdminRoom | null>(null)
const memberList = ref<string[]>([])
const membersLoading = ref(false)

/** 切到频道 tab；首次进入时懒加载列表 */
function switchToRooms() {
  tab.value = 'rooms'
  if (!roomsLoaded.value) loadRooms()
}

async function loadRooms() {
  roomsLoading.value = true
  try {
    rooms.value = await listAdminRooms()
    roomsLoaded.value = true
  } catch (e: any) {
    warn('加载失败', e?.message || '无法获取频道列表')
  } finally {
    roomsLoading.value = false
  }
}

async function viewMembers(r: AdminRoom) {
  membersOf.value = r
  membersLoading.value = true
  memberList.value = []
  try {
    memberList.value = await getRoomMembers(r.id)
  } catch (e: any) {
    warn('加载失败', e?.message || '无法获取成员')
  } finally {
    membersLoading.value = false
  }
}

async function doDeleteRoom(r: AdminRoom) {
  // 删除不可逆，二次确认；并询问是否一并封禁（禁止重建/重新加入）
  if (!confirm(`确认删除频道「${r.name}」？\n将踢出所有成员并清除历史，不可恢复。`)) return
  const block = confirm('是否同时【封禁】此频道？\n确定 = 封禁（禁止任何人再加入/重建，用于违规群）\n取消 = 仅删除')
  roomBusy.value = r.id
  try {
    await deleteRoom(r.id, block)
    rooms.value = rooms.value.filter(x => x.id !== r.id)
    success('已删除', `频道「${r.name}」已${block ? '删除并封禁' : '删除'}`)
  } catch (e: any) {
    warn('删除失败', e?.message || '无法删除频道')
  } finally {
    roomBusy.value = null
  }
}

/* —— AI 配置 —— */
const aiLoading = ref(false)
const aiSaving = ref(false)
const aiLoaded = ref(false)
// enabled_tools=null 表示全开；UI 里用一个集合表示"当前开启的工具"
const aiForm = reactive<{
  provider: string
  model: string
  system_prompt: string
  tools: Set<string>
}>({
  provider: '',
  model: '',
  system_prompt: '',
  tools: new Set(AI_TOOL_CATALOG.map((t) => t.name)), // 默认全开
})

// 当前选中 provider 的元信息（模型占位符等）
const providerMeta = computed(
  () => AI_PROVIDERS.find((p) => p.value === aiForm.provider) || AI_PROVIDERS[0],
)

function isToolOn(name: string): boolean {
  return aiForm.tools.has(name)
}
function toggleTool(name: string, on: boolean) {
  if (on) aiForm.tools.add(name)
  else aiForm.tools.delete(name)
}

function switchToAi() {
  tab.value = 'ai'
  if (!aiLoaded.value) loadAi()
}

async function loadAi() {
  aiLoading.value = true
  try {
    const cfg = await getAiConfig()
    aiForm.provider = cfg?.provider || ''
    aiForm.model = cfg?.model || ''
    aiForm.system_prompt = cfg?.system_prompt || ''
    const all = AI_TOOL_CATALOG.map((t) => t.name)
    aiForm.tools = new Set(cfg?.enabled_tools ?? all)
    aiLoaded.value = true
  } catch (e: any) {
    warn('加载失败', e?.message || '无法读取 AI 配置')
  } finally {
    aiLoading.value = false
  }
}

async function saveAi() {
  // 选了某家 provider → 提醒「key 在服务器配」（网页不再收 key）
  if (aiForm.provider) {
    if (!confirm(`已选「${providerMeta.value.label}」。请确认服务器已为它配好 API Key（环境变量/Secret Manager），否则 AI 无法回话。仍要保存吗？`)) return
  }
  aiSaving.value = true
  try {
    const all = AI_TOOL_CATALOG.map((t) => t.name)
    // 全开 → 存 null（表示不限制）；否则存当前集合
    const enabled = all.every((n) => aiForm.tools.has(n)) ? null : [...aiForm.tools]
    await setAiConfig({
      provider: aiForm.provider,
      model: aiForm.model,
      system_prompt: aiForm.system_prompt,
      enabled_tools: enabled,
    })
    success('已保存', '主 AI 约 20 秒内热生效')
  } catch (e: any) {
    warn('保存失败', e?.message || '无法写入控制室')
  } finally {
    aiSaving.value = false
  }
}

/* —— 技能库（全局技能，写控制室 state event）—— */
const skills = ref<GlobalSkill[]>([])
const skLoading = ref(false)
const skSaving = ref(false)
const skLoaded = ref(false)
const skEditing = ref(false)
// _isEdit=true 表示编辑已有技能（slug 锁定不可改）
const skForm = reactive<GlobalSkill & { _isEdit: boolean }>({
  slug: '', name: '', description: '', instructions: '', enabled: true, _isEdit: false,
})

function switchToSkills() {
  tab.value = 'skills'
  if (!skLoaded.value) loadSkills()
}

async function loadSkills() {
  skLoading.value = true
  try {
    skills.value = await getGlobalSkills()
    skLoaded.value = true
  } catch (e: any) {
    warn('加载失败', e?.message || '无法读取技能')
  } finally {
    skLoading.value = false
  }
}

function startAddSkill() {
  Object.assign(skForm, {
    slug: '', name: '', description: '', instructions: '', enabled: true, _isEdit: false,
  })
  skEditing.value = true
}

function startEditSkill(s: GlobalSkill) {
  Object.assign(skForm, { ...s, _isEdit: true })
  skEditing.value = true
}

/** 把当前 skills 列表整体写回控制室（全局技能是一个 state event 里的数组）。 */
async function persistSkills(next: GlobalSkill[], okMsg: string) {
  skSaving.value = true
  try {
    await setGlobalSkills(next)
    skills.value = next
    success('已保存', okMsg)
  } catch (e: any) {
    warn('保存失败', e?.message || '无法写入控制室')
    throw e
  } finally {
    skSaving.value = false
  }
}

async function saveSkill() {
  const slug = skForm.slug.trim()
  if (!slug) return
  const item: GlobalSkill = {
    slug,
    name: skForm.name.trim(),
    description: skForm.description.trim(),
    instructions: skForm.instructions,
    enabled: skForm.enabled,
  }
  // 已有同 slug → 覆盖；否则追加
  const next = skills.value.slice()
  const i = next.findIndex((s) => s.slug === slug)
  if (i >= 0) next[i] = item
  else next.push(item)
  try {
    await persistSkills(next, '主 AI 约 20 秒内热生效')
    skEditing.value = false
  } catch { /* persistSkills 已提示 */ }
}

async function toggleSkill(s: GlobalSkill) {
  const next = skills.value.map((x) =>
    x.slug === s.slug ? { ...x, enabled: !x.enabled } : x,
  )
  try { await persistSkills(next, s.enabled ? '已停用' : '已启用') } catch { /* 已提示 */ }
}

async function removeSkill(s: GlobalSkill) {
  if (!confirm(`确认删除技能「${s.name || s.slug}」？`)) return
  const next = skills.value.filter((x) => x.slug !== s.slug)
  try { await persistSkills(next, '已删除') } catch { /* 已提示 */ }
}

/* —— 数据概览 —— */
const ovLoading = ref(false)
const ovLoaded = ref(false)
const ov = reactive({
  version: '',
  userTotal: 0, adminCount: 0, deactivated: 0,
  roomTotal: 0, publicRooms: 0, encryptedRooms: 0,
  memberSum: 0, avgMembers: 0, activeRooms: 0,
  topRooms: [] as AdminRoom[],
})

function switchToOverview() {
  tab.value = 'overview'
  if (!ovLoaded.value) loadOverview()
}

/** 聚合统计：复用 listUsers + listAdminRooms + getServerVersion，前端算汇总 */
async function loadOverview() {
  ovLoading.value = true
  try {
    const [us, rs, ver] = await Promise.all([listUsers(), listAdminRooms(), getServerVersion()])
    ov.version = ver
    ov.userTotal = us.length
    ov.adminCount = us.filter((u) => u.admin).length
    ov.deactivated = us.filter((u) => u.deactivated).length
    ov.roomTotal = rs.length
    ov.publicRooms = rs.filter((r) => r.isPublic).length
    ov.encryptedRooms = rs.filter((r) => r.encrypted).length
    ov.memberSum = rs.reduce((sum, r) => sum + r.members, 0)
    ov.avgMembers = rs.length ? Math.round((ov.memberSum / rs.length) * 10) / 10 : 0
    ov.activeRooms = rs.filter((r) => r.members >= 2).length
    // 客户端按成员数降序取前 8（不依赖接口排序——实测 Admin API 的 dir=b 在本版未降序）
    ov.topRooms = [...rs].sort((a, b) => b.members - a.members).slice(0, 8)
    ovLoaded.value = true
  } catch (e: any) {
    warn('统计失败', e?.message || '无法获取概览数据')
  } finally {
    ovLoading.value = false
  }
}

onMounted(check)
</script>

<style scoped>
/* 全屏覆盖层：盖住整个工作台，自带关闭按钮 */
.admin-view {
  position: fixed;
  inset: 0;
  z-index: 200;
  display: flex;
  min-height: 0;
  background: var(--bg);
  color: var(--text);
  animation: adm-fade 0.15s ease;
}
@keyframes adm-fade { from { opacity: 0; } to { opacity: 1; } }

.adm-close {
  position: absolute;
  top: 14px; right: 18px;
  z-index: 3;
  width: 30px; height: 30px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-panel);
  color: var(--text-3);
  font-size: 15px; cursor: pointer;
  transition: background 0.1s ease, color 0.1s ease;
}
.adm-close:hover { background: var(--bg-soft); color: var(--text); }

/* —— 左侧菜单 —— */
.adm-nav {
  width: 220px;
  flex-shrink: 0;
  border-right: 1px solid var(--border);
  background: var(--bg-panel);
  display: flex;
  flex-direction: column;
  padding: 16px 12px;
  gap: 18px;
}
.adm-brand { display: flex; align-items: center; gap: 10px; padding: 4px; }
.adm-logo {
  width: 34px; height: 34px; border-radius: 9px;
  background: var(--accent); color: #fff;
  display: inline-flex; align-items: center; justify-content: center; font-size: 17px;
}
.adm-title { font-size: var(--fs-200); font-weight: var(--fw-bold); }
.adm-sub { font-size: var(--fs-75); color: var(--text-3); margin-top: 1px; }
.adm-menu { display: flex; flex-direction: column; gap: 2px; }
.adm-mi {
  display: flex; align-items: center; gap: 9px;
  padding: 9px 10px; border: none; border-radius: 8px;
  background: transparent; color: var(--text-2);
  font-size: var(--fs-100); text-align: left; cursor: pointer;
  transition: background 0.1s ease;
}
.adm-mi:hover:not(:disabled) { background: var(--bg-soft); color: var(--text); }
.adm-mi.active { background: var(--accent-soft); color: var(--accent); font-weight: var(--fw-bold); }
.adm-mi:disabled { color: var(--text-3); cursor: default; }
.adm-mi-ic { width: 18px; text-align: center; }
.adm-soon {
  margin-left: auto; font-size: 10px; color: var(--text-3);
  background: var(--bg-soft); padding: 1px 6px; border-radius: 8px;
}

/* —— 右侧内容 —— */
.adm-main { flex: 1; min-width: 0; overflow-y: auto; padding: 22px 26px; }
.adm-head { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 18px; padding-right: 44px; }
.adm-h1 { font-size: 20px; font-weight: var(--fw-bold); }
.adm-hint { font-size: var(--fs-75); color: var(--text-3); margin-top: 4px; }
.adm-actions { display: flex; gap: 8px; }

.adm-btn {
  border: none; border-radius: 8px; cursor: pointer;
  padding: 8px 14px; font-size: var(--fs-100);
  background: var(--accent); color: #fff; font-weight: var(--fw-bold);
  transition: opacity 0.1s ease;
}
.adm-btn:hover:not(:disabled) { opacity: 0.88; }
.adm-btn:disabled { opacity: 0.5; cursor: default; }
.adm-btn.ghost { background: var(--bg-soft); color: var(--text-2); font-weight: 400; }
.adm-btn.sm { padding: 5px 10px; font-size: var(--fs-75); border-radius: 7px; }
.adm-btn.danger { color: var(--danger); }
.adm-btn.danger:hover:not(:disabled) { background: #fee2e2; opacity: 1; }

/* 技能库 */
.adm-row-actions { display: flex; gap: 6px; justify-content: flex-end; }
.adm-skill-desc { color: var(--text-2); max-width: 320px; }
.adm-skill-edit {
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 16px;
  margin-bottom: 16px;
  background: var(--bg-soft);
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.adm-badge {
  font-size: var(--fs-75);
  padding: 2px 9px;
  border-radius: 999px;
  background: var(--bg-soft);
  color: var(--text-3);
  border: 1px solid var(--border);
}
.adm-badge.on {
  color: var(--ok, #2e7d32);
  border-color: color-mix(in srgb, var(--ok, #2e7d32) 40%, var(--border));
  background: color-mix(in srgb, var(--ok, #2e7d32) 10%, transparent);
}

/* 表格 */
.adm-table { width: 100%; border-collapse: collapse; font-size: var(--fs-100); }
.adm-table th {
  text-align: left; font-size: var(--fs-75); color: var(--text-3); font-weight: 400;
  padding: 8px 10px; border-bottom: 1px solid var(--border);
}
.adm-ops-h { text-align: right; }
.adm-table td { padding: 11px 10px; border-bottom: 1px solid var(--border-soft); vertical-align: middle; }
.adm-table tr.off td { opacity: 0.55; }

.adm-user { display: flex; align-items: center; gap: 10px; }
.adm-ava {
  width: 32px; height: 32px; border-radius: 8px; flex-shrink: 0;
  background: var(--accent); color: #fff;
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 14px; font-weight: 600;
}
.adm-u-name { font-weight: var(--fw-bold); display: flex; align-items: center; gap: 6px; }
.adm-u-handle { font-size: var(--fs-75); color: var(--text-3); font-family: var(--mono); margin-top: 1px; }

.adm-tag { font-size: 11px; padding: 2px 8px; border-radius: 8px; }
.adm-tag.admin { color: var(--accent); background: var(--accent-soft); }
.adm-tag.member { color: var(--text-3); background: var(--bg-soft); }
.adm-tag.ok { color: var(--ok); background: color-mix(in srgb, var(--ok) 14%, transparent); }
.adm-tag.off { color: var(--danger); background: #fee2e2; }
.adm-tag.bot { color: #fff; background: var(--accent); }

.adm-ops { text-align: right; white-space: nowrap; }
.adm-op {
  border: 1px solid var(--border); background: var(--bg-panel); color: var(--text-2);
  font-size: var(--fs-75); padding: 5px 9px; border-radius: 7px; margin-left: 6px; cursor: pointer;
  transition: background 0.1s ease;
}
.adm-op:hover:not(:disabled) { background: var(--bg-soft); color: var(--text); }
.adm-op:disabled { opacity: 0.4; cursor: default; }
.adm-op.danger { color: var(--danger); border-color: color-mix(in srgb, var(--danger) 40%, var(--border)); }
.adm-op.danger:hover:not(:disabled) { background: #fee2e2; }

/* 居中态（loading / denied） */
.adm-center {
  display: flex; align-items: center; justify-content: center; gap: 10px;
  padding: 60px 0; color: var(--text-3); font-size: var(--fs-100);
}
.adm-spin {
  width: 18px; height: 18px; border-radius: 50%;
  border: 2px solid var(--border); border-top-color: var(--accent);
  animation: adm-rot 0.7s linear infinite;
}
@keyframes adm-rot { to { transform: rotate(360deg); } }

.adm-denied { flex-direction: column; gap: 8px; text-align: center; padding-top: 80px; }
.adm-denied-ic { font-size: 40px; }
.adm-denied-t { font-size: 17px; font-weight: var(--fw-bold); color: var(--text); }
.adm-denied-d { max-width: 380px; line-height: 1.6; }
.adm-denied-d code { font-family: var(--mono); color: var(--accent); }

/* 新建弹窗 */
.adm-mask {
  position: fixed; inset: 0; z-index: 80;
  background: rgba(0, 0, 0, 0.28);
  display: flex; align-items: center; justify-content: center;
}
.adm-modal {
  width: 380px; background: var(--bg-panel);
  border: 1px solid var(--border); border-radius: 14px; padding: 20px;
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.18);
}
.adm-modal-h { font-size: var(--fs-200); font-weight: var(--fw-bold); margin-bottom: 14px; }
.adm-field { display: flex; flex-direction: column; gap: 5px; margin-bottom: 12px; }
.adm-field span { font-size: var(--fs-75); color: var(--text-3); }
.adm-field input {
  border: 1px solid var(--border); border-radius: 8px; padding: 8px 10px;
  font-size: var(--fs-100); background: var(--bg); color: var(--text);
}
.adm-field input:focus { outline: none; border-color: var(--accent); }
.adm-modal-f { display: flex; justify-content: flex-end; gap: 8px; margin-top: 6px; }

/* 频道管理补充 */
.adm-dim { color: var(--text-3); font-size: var(--fs-75); }
.adm-empty { text-align: center; color: var(--text-3); padding: 24px 0; }
.adm-tag.bot { margin-left: 6px; }

/* AI 配置表单 */
.adm-form { max-width: 640px; display: flex; flex-direction: column; gap: 18px; }
.adm-form .adm-field textarea,
.adm-form .adm-field input,
.adm-form .adm-field select {
  border: 1px solid var(--border); border-radius: 8px; padding: 9px 11px;
  font-size: var(--fs-100); background: var(--bg); color: var(--text);
  font-family: inherit; resize: vertical; line-height: 1.5;
}
.adm-form .adm-field textarea:focus,
.adm-form .adm-field input:focus,
.adm-form .adm-field select:focus { outline: none; border-color: var(--accent); }
.adm-note { font-size: var(--fs-75); color: var(--text-3); font-style: normal; line-height: 1.5; }
.adm-tools { display: flex; flex-direction: column; gap: 8px; margin-top: 4px; }
.adm-tool {
  display: flex; align-items: center; gap: 9px; cursor: pointer;
  padding: 8px 10px; border: 1px solid var(--border); border-radius: 8px; background: var(--bg-panel);
}
.adm-tool input { width: 16px; height: 16px; accent-color: var(--accent); }
.adm-tool-l { font-size: var(--fs-100); color: var(--text); }
.adm-tool code { margin-left: auto; font-family: var(--mono); font-size: var(--fs-75); color: var(--text-3); }

/* 数据概览 KPI 卡片 */
.adm-kpis {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px; margin-bottom: 24px;
}
.adm-kpi {
  border: 1px solid var(--border); border-radius: 12px;
  background: var(--bg-panel); padding: 16px 18px;
}
.adm-kpi-v { font-size: 30px; font-weight: var(--fw-bold); color: var(--accent); line-height: 1.1; }
.adm-kpi-l { font-size: var(--fs-100); color: var(--text); margin-top: 4px; }
.adm-kpi-s { font-size: var(--fs-75); color: var(--text-3); margin-top: 2px; }
.adm-h2 { font-size: var(--fs-200); font-weight: var(--fw-bold); margin: 4px 0 12px; }

/* 成员弹窗列表 */
.adm-mlist { max-height: 320px; overflow-y: auto; margin-bottom: 12px; }
.adm-mrow { display: flex; align-items: center; gap: 9px; padding: 6px 2px; }
.adm-ava.sm { width: 26px; height: 26px; font-size: 12px; border-radius: 7px; }
.adm-mid { font-family: var(--mono); font-size: var(--fs-75); color: var(--text-2); }
</style>
