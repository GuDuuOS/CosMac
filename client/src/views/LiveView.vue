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
import { ref, computed, reactive, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import {
  login,
  restoreSession,
  logout,
  onUpdate,
  listRooms,
  listMessages,
  listReactions,
  react,
  unreact,
  sendReply,
  editMessage,
  sendText,
  ensureBotDm,
  listSpaces,
  roomIdsInSpace,
  createSpace,
  createChannelInSpace,
  updateSpace,
  updateRoom,
  leaveAndForget,
  uploadMedia,
  mxcToHttp,
  inviteToRoom,
  listRoomMembers,
  isFavourite,
  setFavourite,
  normalizeUserId,
  BOT_ID,
  type LiveRoom,
  type LiveMsg,
  type LiveSpace,
} from '@/matrix/client'
import { tenant } from '@/config/tenant'
import logoUrl from '@/assets/cosmac-logo.png'

// ── 复刻 DEMO 的按键功能：直接复用演示版的弹窗/面板组件 + 它们的 composable ──
// 这些组件都是"常驻挂载、内部 v-if(visible)"模式；按键只需调对应 composable 的 open()。
import MarketplaceModal from '@/components/layout/MarketplaceModal.vue'
import PluginStoreModal from '@/components/layout/PluginStoreModal.vue'
import CustomAssetsModal from '@/components/layout/CustomAssetsModal.vue'
import UserSettingsModal from '@/components/layout/UserSettingsModal.vue'
import ProfileHome from '@/components/layout/ProfileHome.vue'
import CliConsole from '@/components/layout/CliConsole.vue'
import { useMarketplace } from '@/composables/useMarketplace'
import { useCli } from '@/composables/useCli'
import { useProfileHome } from '@/composables/useProfileHome'
import { usePluginStore } from '@/composables/usePluginStore'
import { useCustomAssets } from '@/composables/useCustomAssets'
import { useUserProfile, type UserSettingsTab } from '@/composables/useUserProfile'

const { open: openMarket } = useMarketplace()
const { open: openCli } = useCli()
const { open: openProfileHome } = useProfileHome()
const { open: openPluginStore } = usePluginStore()
const { open: openAssets } = useCustomAssets()
const { openSettings } = useUserProfile()

// ── 数据看板（复用 DEMO 的画布组件 + 影视公司主题数据）──
import KpiCard from '@/components/canvas/KpiCard.vue'
import PanelChart from '@/components/canvas/PanelChart.vue'
import UnitGrid from '@/components/canvas/UnitGrid.vue'
import CommandCenter from '@/components/canvas/CommandCenter.vue'
import BizPanels from '@/components/canvas/BizPanels.vue'
import { getDashboard } from '@/data/dashboards'
import { getTodos, type TodoItem } from '@/data/todos'
import { useActiveWorkspace } from '@/composables/useActiveWorkspace'
import '@/styles/canvas.css' // 看板样式，命名空间在 .canvas/.panel 下，不与 LiveView 撞
const { activeId } = useActiveWorkspace()
const dash = computed(() => getDashboard(activeId.value))

// 主区视图：board=数据看板 / tasks=任务看板 / 两者皆 false=频道（登录后默认数据看板）
const board = ref(true)
const tasks = ref(false)
function openBoard() { board.value = true; tasks.value = false; currentRoom.value = '' }
function openTasks() { tasks.value = true; board.value = false; currentRoom.value = '' }

// 任务看板：所有任务按状态分到 3 列（待办/进行中/已完成）
const taskItems = computed<TodoItem[]>(() => getTodos(activeId.value).groups.flatMap((g) => g.items))
const taskCols = computed(() => [
  { key: 'pending', title: '待办', items: taskItems.value.filter((t) => t.status === 'pending') },
  { key: 'in_progress', title: '进行中', items: taskItems.value.filter((t) => t.status === 'in_progress') },
  { key: 'done', title: '已完成', items: taskItems.value.filter((t) => t.status === 'done') },
])
function priLabel(p: string) { return p === 'high' ? '高' : p === 'mid' ? '中' : '低' }

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
const filterInput = ref<HTMLInputElement>()

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
const currentTopic = computed(
  () => rooms.value.find((r) => r.id === currentRoom.value)?.topic || '',
)

// ── 工作区（Matrix Space）──────────────────────────────
const spaces = ref<LiveSpace[]>([])
const activeSpace = ref('')                       // 当前工作区 id
const spaceChildIds = ref<Set<string>>(new Set()) // 当前工作区下的频道 id
const activeSpaceName = computed(
  () => spaces.value.find((s) => s.id === activeSpace.value)?.name || tenant.hqTitle,
)
function wsLabel(name: string) {
  return [...name.replace(/[·\s]/g, '')].slice(0, 2).join('')
}
function selectSpace(id: string) {
  activeSpace.value = id
  spaceChildIds.value = roomIdsInSpace(id)
  // 切了工作区，若当前频道不属于它，回到频道空态
  if (currentRoom.value && !spaceChildIds.value.has(currentRoom.value)) currentRoom.value = ''
}

// ── 工作区设置（点工作区名打开，改名称 / 简称）──
const wsSetOpen = ref(false)
const wsSetName = ref('')
const wsSetLabel = ref('')
const wsSetBusy = ref(false)
const wsDeleteArm = ref(false) // 删除工作区的二次确认
// 工作区头像：avatarChange=undefined 不动 / '' 移除 / mxc 新图；preview 仅用于弹窗内显示
const wsSetAvatarChange = ref<string | undefined>(undefined)
const wsSetAvatarPreview = ref('')
const wsUploading = ref(false)
const wsFileInput = ref<HTMLInputElement>()
function openWsSettings() {
  if (!activeSpace.value) return
  const s = spaces.value.find((x) => x.id === activeSpace.value)
  wsSetName.value = s?.name || ''
  wsSetLabel.value = s?.label || ''
  wsSetAvatarChange.value = undefined
  wsSetAvatarPreview.value = s?.avatarUrl || ''
  wsDeleteArm.value = false
  wsSetOpen.value = true
}
async function onPickWsImage(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  wsUploading.value = true
  try {
    const mxc = await uploadMedia(file)
    wsSetAvatarChange.value = mxc
    wsSetAvatarPreview.value = mxcToHttp(mxc, 64)
  } catch (err: any) {
    toast('上传失败', err?.message || String(err))
  } finally {
    wsUploading.value = false
    if (wsFileInput.value) wsFileInput.value.value = '' // 允许重选同一文件
  }
}
function removeWsImage() {
  wsSetAvatarChange.value = ''
  wsSetAvatarPreview.value = ''
}

// 简称统一限制为「2 个字符」——按码点(visual char)算，中/英/日/韩/emoji 都是 2 个为上限。
function clamp2(s: string): string {
  return [...s].slice(0, 2).join('')
}
watch(wsSetLabel, (v) => { const c = clamp2(v); if (c !== v) wsSetLabel.value = c })
// 当前工作区下的频道数（删除确认提示用）
const wsChildCount = computed(() => (activeSpace.value ? roomIdsInSpace(activeSpace.value).size : 0))
async function deleteWorkspace() {
  const id = activeSpace.value
  if (!id || wsSetBusy.value) return
  wsSetBusy.value = true
  try {
    // 先退出该工作区下的所有频道，再退出工作区本身
    for (const cid of roomIdsInSpace(id)) {
      try { await leaveAndForget(cid) } catch { /* 单个失败不阻断 */ }
    }
    await leaveAndForget(id)
    toast('已删除工作区', wsSetName.value)
    wsSetOpen.value = false
    activeSpace.value = ''
    setTimeout(() => {
      refresh()
      board.value = true; tasks.value = false; currentRoom.value = ''
    }, 900)
  } catch (e: any) {
    toast('删除失败', e?.message || String(e))
  } finally {
    wsSetBusy.value = false
  }
}
async function saveWsSettings() {
  const id = activeSpace.value
  const name = wsSetName.value.trim()
  if (!id || !name || wsSetBusy.value) return
  wsSetBusy.value = true
  try {
    await updateSpace(id, { name, label: wsSetLabel.value.trim(), avatar: wsSetAvatarChange.value })
    toast('已保存', `工作区改为「${name}」`)
    wsSetOpen.value = false
    setTimeout(refresh, 700)
  } catch (e: any) {
    toast('保存失败', e?.message || String(e))
  } finally {
    wsSetBusy.value = false
  }
}

// ── 频道设置（点频道头标题打开，改名称 / 简介）──
const chSetOpen = ref(false)
const chSetName = ref('')
const chSetTopic = ref('')
const chSetBusy = ref(false)
const chDeleteArm = ref(false)
function openChannelSettings() {
  if (!currentRoom.value) return
  chSetName.value = currentName.value
  chSetTopic.value = currentTopic.value
  chDeleteArm.value = false
  chSetOpen.value = true
}
async function deleteChannel() {
  const id = currentRoom.value
  if (!id || chSetBusy.value) return
  chSetBusy.value = true
  try {
    await leaveAndForget(id)
    toast('已删除频道', chSetName.value)
    chSetOpen.value = false
    currentRoom.value = ''
    setTimeout(refresh, 800)
  } catch (e: any) {
    toast('删除失败', e?.message || String(e))
  } finally {
    chSetBusy.value = false
  }
}
async function saveChannelSettings() {
  const id = currentRoom.value
  const name = chSetName.value.trim()
  if (!id || !name || chSetBusy.value) return
  chSetBusy.value = true
  try {
    await updateRoom(id, { name, topic: chSetTopic.value.trim() })
    toast('已保存', `频道改为「${name}」`)
    chSetOpen.value = false
    setTimeout(refresh, 700)
  } catch (e: any) {
    toast('保存失败', e?.message || String(e))
  } finally {
    chSetBusy.value = false
  }
}

// ── 新建工作区（完整表单：类型 / 名称 / 简称 / 可见性 / 按类型建默认频道）──
interface WsType { key: string; title: string; nameLabel: string; namePh: string; spaceName: (n: string) => string; chans: (n: string) => string[] }
const WS_TYPES: WsType[] = [
  { key: '制作', title: '制作', nameLabel: '项目/部门名', namePh: '如：新剧《潮汐》', spaceName: (n) => `制作·${n}`, chans: (n) => [`${n} 制作专班`] },
  { key: '运营', title: '运营营销', nameLabel: '工作区名称', namePh: '如：海外发行', spaceName: (n) => n, chans: (n) => [`${n} · 运营`] },
  { key: '明星', title: '明星·粉丝', nameLabel: '虚拟明星名', namePh: '如：墨白', spaceName: (n) => `明星·${n}`, chans: (n) => [`虚拟明星·${n}`, `${n}后援会`] },
  { key: '外部', title: '外部', nameLabel: '工作区名称', namePh: '如：某品牌合作', spaceName: (n) => n, chans: (n) => [`${n} · 对外洽谈`] },
]
const newWsOpen = ref(false)
const newWsType = ref('制作')
const newWsName = ref('')
const newWsLabel = ref('')
watch(newWsLabel, (v) => { const c = clamp2(v); if (c !== v) newWsLabel.value = c })
const newWsPublic = ref(false)
const newWsCreating = ref(false)
const curWsType = computed(() => WS_TYPES.find((t) => t.key === newWsType.value) || WS_TYPES[0])
const newWsSpaceName = computed(() => (newWsName.value.trim() ? curWsType.value.spaceName(newWsName.value.trim()) : ''))
const newWsChannels = computed(() => (newWsName.value.trim() ? curWsType.value.chans(newWsName.value.trim()) : []))
function openNewWorkspace() {
  newWsType.value = '制作'; newWsName.value = ''; newWsLabel.value = ''; newWsPublic.value = false; newWsOpen.value = true
}
async function createWorkspace() {
  const n = newWsName.value.trim()
  if (!n || newWsCreating.value) return
  const t = curWsType.value
  const spaceName = t.spaceName(n)
  const label = newWsLabel.value.trim() || wsLabel(spaceName)
  const pub = newWsPublic.value
  newWsCreating.value = true
  try {
    const sid = await createSpace(spaceName, { public: pub, label })
    for (const cn of t.chans(n)) await createChannelInSpace(sid, cn, { public: pub })
    toast('已创建工作区', `${spaceName}（${t.chans(n).length} 个频道）`)
    newWsOpen.value = false
    setTimeout(() => {
      refresh()
      activeSpace.value = sid
      spaceChildIds.value = roomIdsInSpace(sid)
      board.value = false; tasks.value = false; currentRoom.value = ''
    }, 900)
  } catch (e: any) {
    toast('创建失败', e?.message || String(e))
  } finally {
    newWsCreating.value = false
  }
}

// ── 新建频道（在当前工作区下真建）──
const newChOpen = ref(false)
const newChName = ref('')
const newChTopic = ref('')
const newChPublic = ref(false)
const newChCreating = ref(false)
function openNewChannel() {
  if (!activeSpace.value) { toast('请先选一个工作区', '频道需要归属到某个工作区'); return }
  newChName.value = ''; newChTopic.value = ''; newChPublic.value = false; newChOpen.value = true
}
async function createChannel() {
  const n = newChName.value.trim()
  if (!n || newChCreating.value || !activeSpace.value) return
  newChCreating.value = true
  try {
    const cid = await createChannelInSpace(activeSpace.value, n, { public: newChPublic.value, topic: newChTopic.value.trim() })
    toast('已创建频道', `# ${n} → ${activeSpaceName.value}`)
    newChOpen.value = false
    setTimeout(() => {
      refresh()
      openRoom(cid)
    }, 900)
  } catch (e: any) {
    toast('创建失败', e?.message || String(e))
  } finally {
    newChCreating.value = false
  }
}

// ── 成员管理（邀请已有用户进当前频道/工作区）──
// 注：「新建账号」需走 Synapse Admin API，而 admin API 不对外代理、也不该把 admin token 暴露到浏览器，
// 所以建账号留给后端（业务后台）做；这里先做能从客户端真跑通的「邀请已有用户」。
const memberOpen = ref(false)
const inviteUserInput = ref('')
const memberBusy = ref(false)
const memberList = ref<{ id: string; name: string; isBot: boolean }[]>([])
// 邀请目标：优先当前打开的频道，否则当前工作区(Space)
const memberTarget = computed(() => {
  if (currentRoom.value) return { id: currentRoom.value, name: `#${currentName.value}` }
  if (activeSpace.value) return { id: activeSpace.value, name: `${activeSpaceName.value} 工作区` }
  return null
})
function openMembers() {
  inviteUserInput.value = ''
  memberList.value = memberTarget.value ? listRoomMembers(memberTarget.value.id) : []
  memberOpen.value = true
}
async function doInvite() {
  const t = memberTarget.value
  const uid = normalizeUserId(inviteUserInput.value)
  if (!t || !uid || memberBusy.value) return
  memberBusy.value = true
  try {
    await inviteToRoom(t.id, uid)
    toast('已邀请', `${uid} → ${t.name}`)
    inviteUserInput.value = ''
    setTimeout(() => { memberList.value = listRoomMembers(t.id) }, 600)
  } catch (e: any) {
    toast('邀请失败', e?.message || String(e))
  } finally { memberBusy.value = false }
}

// 频道列表：按当前工作区过滤 + 关键词筛选
const filteredRooms = computed(() =>
  rooms.value.filter(
    (r) =>
      (!activeSpace.value || spaceChildIds.value.has(r.id)) &&
      (!filterText.value || r.name.includes(filterText.value)),
  ),
)

// ── 频道彩色图标：按名字确定性取色 + 取代表字（无需后端，所有频道立即生效）──
const CHAN_PALETTE = ['#c96442', '#6b8e4e', '#4a7a8c', '#b58932', '#8a6a8a', '#5a7a8a', '#b94a4a', '#7a8a5a']
function colorOf(name: string): string {
  let h = 0
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0
  return CHAN_PALETTE[h % CHAN_PALETTE.length]
}
/** 取频道代表字：优先「·」后一段 / 《》内首字，否则去掉前缀符号取首字 */
function iconChar(name: string): string {
  const s = name.trim()
  const dot = s.lastIndexOf('·')
  if (dot >= 0 && dot < s.length - 1) return [...s.slice(dot + 1)][0]
  const m = s.match(/《(.)/)
  if (m) return m[1]
  return [...s.replace(/^[#\s]+/, '')][0] || '#'
}

function isBot(s: string) {
  return s === BOT_ID
}

// ── 安全的极简 Markdown 渲染（消息显示用）──
// 先 HTML 转义（防 XSS：任何 <script> 都变成纯文本），再做有限的 markdown 替换。
// 代码块/行内代码先抠出占位、避免里面的符号被二次处理。
function escapeHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}
function renderMd(raw: string): string {
  let s = escapeHtml(raw || '')
  const stash: string[] = []
  const keep = (html: string) => ` ${stash.push(html) - 1} `
  // 代码块 ```...```
  s = s.replace(/```([\s\S]*?)```/g, (_m, c) => keep(`<pre class="md-pre">${c.replace(/^\n|\n$/g, '')}</pre>`))
  // 行内代码 `...`
  s = s.replace(/`([^`\n]+)`/g, (_m, c) => keep(`<code class="md-code">${c}</code>`))
  // 加粗 / 斜体 / 删除线
  s = s.replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>')
  s = s.replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>')
  s = s.replace(/~~([^~\n]+)~~/g, '<del>$1</del>')
  // 链接 [文字](url)，仅允许 http/https/mailto
  s = s.replace(/\[([^\]\n]+)\]\((https?:\/\/[^\s)]+|mailto:[^\s)]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>')
  // @提及高亮（@用户 或 @用户:服务器）
  s = s.replace(/(^|[\s(])@([a-zA-Z0-9_.\-]+(?::[a-zA-Z0-9_.\-]+)?)/g, '$1<span class="mention">@$2</span>')
  // 换行
  s = s.replace(/\n/g, '<br>')
  // 还原代码占位
  s = s.replace(/ (\d+) /g, (_m, i) => stash[+i])
  return s
}
function fmtTime(ts: number) {
  const d = new Date(ts)
  const h = String(d.getHours()).padStart(2, '0')
  const m = String(d.getMinutes()).padStart(2, '0')
  return `${h}:${m}`
}
// 日期分隔线标签：今天 / 昨天 / X月X日
function dayKey(ts: number) {
  const d = new Date(ts)
  return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`
}
function dayLabel(ts: number) {
  const d = new Date(ts)
  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
  const that = new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
  const diff = Math.round((today - that) / 86400000)
  if (diff === 0) return '今天'
  if (diff === 1) return '昨天'
  return `${d.getFullYear()} 年 ${d.getMonth() + 1} 月 ${d.getDate()} 日`
}
// 发送者名字配色（沿用频道调色板做确定性取色）
function nameColor(name: string) {
  return colorOf(name)
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
  // 工作区（Space）：加载（listSpaces 已按 order 稳定排序，改名不影响顺序）
  spaces.value = listSpaces()
  // 校正激活项（默认第一个 = order 最小 = 制作中心）
  if (!activeSpace.value || !spaces.value.some((s) => s.id === activeSpace.value)) {
    activeSpace.value = spaces.value[0]?.id || ''
  }
  spaceChildIds.value = activeSpace.value ? roomIdsInSpace(activeSpace.value) : new Set()
  rooms.value = listRooms().filter((r) => r.id !== aiRoom.value)
  if (currentRoom.value) {
    msgs.value = listMessages(currentRoom.value)
    channelMembers.value = listRoomMembers(currentRoom.value)
    reactions.value = listReactions(currentRoom.value)
  }
  if (aiRoom.value) aiMsgs.value = listMessages(aiRoom.value)
}

async function afterLogin(uid: string) {
  me.value = uid
  loggedIn.value = true
  board.value = true // 登录后第一屏 = 数据看板
  tasks.value = false
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

// ── Discord 化：反应 / 回复 / 消息分组 ──
import type { ReactionAgg } from '@/matrix/client'
const reactions = ref<Record<string, ReactionAgg[]>>({})
const replyTo = ref<{ id: string; name: string; body: string } | null>(null)
function loadReactions() {
  if (currentRoom.value) reactions.value = listReactions(currentRoom.value)
}
// 消息分组：同一发送者、5 分钟内、非回复 → 折叠头像/名字
const groupedMsgs = computed(() =>
  msgs.value.map((m, i) => {
    const prev = msgs.value[i - 1]
    const showDay = !prev || dayKey(prev.ts) !== dayKey(m.ts)
    // 跨天必定显头像；否则同人+5分钟内+非回复才折叠
    const showHeader = showDay || !prev || prev.sender !== m.sender || m.ts - prev.ts > 5 * 60 * 1000 || !!m.replyToId
    return { ...m, showHeader, showDay }
  }),
)
// emoji 选择器（点工具条表情/反应＋时弹出）
const EMOJIS = ['👍', '❤️', '😂', '😮', '😢', '😡', '🎉', '🔥', '👏', '🙏', '💯', '✅', '😄', '😍', '🤔', '😎', '😅', '🥳', '😭', '👀', '💪', '🚀', '⭐', '💡', '🎬', '🎵', '📌', '🤝', '😬', '🫡', '🤩', '😇']
const emojiPicker = ref<{ msgId: string; x: number; y: number } | null>(null)
function openEmojiPicker(msgId: string, e: MouseEvent) {
  const r = (e.currentTarget as HTMLElement).getBoundingClientRect()
  emojiPicker.value = { msgId, x: Math.min(r.left, window.innerWidth - 250), y: r.bottom + 4 }
}
function pickEmoji(key: string) {
  if (emojiPicker.value) quickReact(emojiPicker.value.msgId, key)
  emojiPicker.value = null
}
// 编辑自己的消息
const editingId = ref<string | null>(null)
function startEdit(m: { id: string; body: string }) {
  editingId.value = m.id
  replyTo.value = null
  draft.value = m.body
  nextTick(() => taRef.value?.focus())
}
function cancelEdit() { editingId.value = null; draft.value = '' }
async function copyMsg(body: string) {
  try { await navigator.clipboard.writeText(body); toast('已复制') } catch { toast('复制失败') }
}
async function toggleReaction(msgId: string, key: string) {
  if (!currentRoom.value) return
  const mine = reactions.value[msgId]?.find((r) => r.key === key && r.mine)
  try {
    if (mine?.myId) await unreact(currentRoom.value, mine.myId)
    else await react(currentRoom.value, msgId, key)
    setTimeout(loadReactions, 500)
  } catch (e: any) { toast('操作失败', e?.message || String(e)) }
}
async function quickReact(msgId: string, key: string) {
  if (!currentRoom.value) return
  // 已经有我的同款反应 → 取消，否则添加
  const mine = reactions.value[msgId]?.find((r) => r.key === key && r.mine)
  try {
    if (mine?.myId) await unreact(currentRoom.value, mine.myId)
    else await react(currentRoom.value, msgId, key)
    setTimeout(loadReactions, 500)
  } catch (e: any) { toast('操作失败', e?.message || String(e)) }
}
function startReply(m: { id: string; senderName: string; body: string }) {
  replyTo.value = { id: m.id, name: m.senderName, body: m.body }
  nextTick(() => taRef.value?.focus())
}
function cancelReply() { replyTo.value = null }

// 当前频道的真实成员（频道头显示数量+头像）
const channelMembers = ref<{ id: string; name: string; isBot: boolean }[]>([])
function openRoom(id: string) {
  board.value = false
  tasks.value = false
  currentRoom.value = id
  msgs.value = listMessages(id)
  channelMembers.value = listRoomMembers(id)
  fav.value = isFavourite(id)
  reactions.value = listReactions(id)
  replyTo.value = null
  editingId.value = null
}
// 收藏当前频道（真实 Matrix m.favourite 标签，按频道独立、跨设备同步）
async function toggleFav() {
  const id = currentRoom.value
  if (!id) return
  const next = !fav.value
  fav.value = next
  try { await setFavourite(id, next) } catch (e: any) { fav.value = !next; toast('收藏失败', e?.message || String(e)) }
}

async function send() {
  const t = draft.value.trim()
  if (!t || !currentRoom.value) return
  draft.value = ''
  const rep = replyTo.value
  const ed = editingId.value
  replyTo.value = null
  editingId.value = null
  if (ed) await editMessage(currentRoom.value, ed, t)
  else if (rep) await sendReply(currentRoom.value, t, rep.id)
  else await sendText(currentRoom.value, t)
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
// ↓↓↓ 这些按键复刻 DEMO 真实（mock）功能：打开对应弹窗/面板 ↓↓↓
function onSettings(tab?: UserSettingsTab) { openSettings(tab); userMenuOpen.value = false }
function onMarket() { openMarket(); appMenuOpen.value = false }
function onCli() { openCli(); appMenuOpen.value = false }
function onProfile() { openProfileHome(); appMenuOpen.value = false; userMenuOpen.value = false }
function onPluginStore() { openPluginStore() }
function onCustomAssets() { openAssets() }
// ↓↓↓ 这些 DEMO 本身也只是 toast 提示（无独立弹窗），保持一致 ↓↓↓
function onFilter() { filterInput.value?.focus() }
function onAttach() { toast('📎 附件', '支持图片 / 视频 / 文档（演示）') }
function onEmoji() { toast('😊 表情') }

function onDocClick(e: MouseEvent) {
  if (!rootEl.value) return
  if (!(e.target as HTMLElement)?.closest?.('.tas-wrap')) appMenuOpen.value = false
  if (!(e.target as HTMLElement)?.closest?.('.um-wrap')) userMenuOpen.value = false
  if (!(e.target as HTMLElement)?.closest?.('.emoji-pop, .msg-tools, .rxn.add')) emojiPicker.value = null
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
          <img :src="logoUrl" alt="" class="logo" />
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
        <button class="ic-btn" title="设置" @click="onSettings()">
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
            <button class="um-item" @click="onSettings('profile')"><span class="um-ic">👤</span>个人资料</button>
            <button class="um-item" @click="onSettings('perms')"><span class="um-ic">🔒</span>我的权限</button>
            <button class="um-item" @click="onSettings('share')"><span class="um-ic">🔔</span>数据调用授权</button>
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
        <div
          v-for="s in spaces"
          :key="s.id"
          class="ws-icon"
          :class="{ active: s.id === activeSpace, 'has-img': !!s.avatarUrl }"
          :title="s.name"
          @click="selectSpace(s.id)"
        >
          <img v-if="s.avatarUrl" :src="s.avatarUrl" alt="" class="ws-img" />
          <template v-else>{{ s.label || wsLabel(s.name) }}</template>
        </div>
        <div class="ws-icon plus" title="新建工作区" @click="openNewWorkspace">+</div>
        <div class="ws-sep" />
        <div class="ws-icon ws-tool" title="AI Agent 商城" @click="onMarket">
          <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 2 3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4Z" /><path d="M3 6h18" /><path d="M16 10a4 4 0 0 1-8 0" /></svg>
        </div>
        <div class="ws-icon ws-tool" title="CLI" @click="onCli">
          <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="4 17 10 11 4 5" /><line x1="12" x2="20" y1="19" y2="19" /></svg>
        </div>
        <div class="ws-icon ws-tool" title="个人主页" @click="onProfile">
          <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /><polyline points="9 22 9 12 15 12 15 22" /></svg>
        </div>
      </nav>

      <!-- 左：频道侧栏（浮卡）-->
      <aside v-if="!focused" class="channels">
        <div class="cs-ws-head">
          <button class="cs-ws-name" :title="`${activeSpaceName} · 点击设置`" @click="openWsSettings">
            <span class="name">{{ activeSpaceName }}</span>
            <svg class="chev" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6" /></svg>
          </button>
          <button class="cs-add" title="添加" @click="openNewChannel">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M12 5v14" /></svg>
          </button>
        </div>

        <div class="cs-filter">
          <button class="cs-filter-funnel" title="筛选" @click="onFilter">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18l-7 9v6l-4-2v-4z" /></svg>
          </button>
          <input ref="filterInput" class="cs-filter-input" v-model="filterText" placeholder="查找频道" />
        </div>

        <div class="cs-list">
          <!-- 置顶：数据看板（影视公司制作驾驶舱）-->
          <div class="cs-item pinned-item" :class="{ active: board }" @click="openBoard">
            <span class="cs-ic">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="9" rx="1" /><rect x="14" y="3" width="7" height="5" rx="1" /><rect x="14" y="12" width="7" height="9" rx="1" /><rect x="3" y="16" width="7" height="5" rx="1" /></svg>
            </span>
            <span class="cs-label">数据看板</span>
          </div>
          <div class="cs-item pinned-item" :class="{ active: tasks }" @click="openTasks">
            <span class="cs-ic">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 11l3 3L22 4" /><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" /></svg>
            </span>
            <span class="cs-label">任务看板</span>
          </div>

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
                <span class="cs-chan-av" :style="{ background: colorOf(r.name) }">{{ iconChar(r.name) }}</span>
                <span class="cs-label">{{ r.name }}</span>
              </div>
              <p v-if="!filteredRooms.length" class="cs-empty">还没有频道</p>
              <div class="cs-item cs-add-row" @click="openNewChannel">
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
              <div class="cs-item cs-add-row" @click="openMembers">
                <span class="cs-ic-box"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M12 5v14" /></svg></span>
                <span class="cs-label">邀请成员</span>
              </div>
            </template>
          </div>
        </div>
      </aside>

      <!-- 中：数据看板 / 频道（浮卡）-->
      <main class="main">
        <!-- ===== 数据看板（影视公司制作驾驶舱）===== -->
        <template v-if="board">
          <div class="ch-header">
            <div class="title">📊 数据看板</div>
            <div class="ch-actions">
              <button class="ch-ic-btn" :class="{ active: aiOpen }" :title="aiOpen ? '关闭中枢 AI' : '打开中枢 AI'" @click="aiOpen = !aiOpen">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10" /><path d="M12 16v-4M12 8h.01" /></svg>
              </button>
            </div>
          </div>
          <div class="board-scroll">
            <div class="canvas">
              <div class="ctitle">{{ dash.brand }}</div>
              <div class="csub">// 实时运营画布 · 由 CosMac Star 自动维护</div>
              <CommandCenter />
              <div class="kpis">
                <KpiCard v-for="(k, i) in dash.kpis" :key="k.label" :data="k" :delay="200 + i * 80" />
              </div>
              <div class="grid-2">
                <PanelChart :title="dash.prod.title" :config="dash.prod.build" :live="dash.prod.live" />
                <PanelChart :title="dash.save.title" :config="dash.save.build" />
              </div>
              <div class="grid-3">
                <div class="panel" style="grid-column: span 2">
                  <div class="pt">{{ dash.unitsTitle }}</div>
                  <UnitGrid :units="dash.units" />
                </div>
                <PanelChart :title="dash.pie.title" :config="dash.pie.build" :height="dash.pie.height ?? 180" />
              </div>
              <BizPanels />
            </div>
          </div>
        </template>

        <!-- ===== 任务看板（待办/进行中/已完成 三列）===== -->
        <template v-else-if="tasks">
          <div class="ch-header">
            <div class="title">📋 任务看板</div>
            <div class="ch-actions">
              <span class="board-sub">{{ taskItems.length }} 项任务 · AI 制作中</span>
            </div>
          </div>
          <div class="kanban">
            <div v-for="col in taskCols" :key="col.key" class="kb-col">
              <div class="kb-col-head">
                <span class="kb-dot" :class="col.key" />
                <span class="kb-col-title">{{ col.title }}</span>
                <span class="kb-count">{{ col.items.length }}</span>
              </div>
              <div class="kb-cards">
                <div v-for="t in col.items" :key="t.id" class="kb-card" :class="{ done: t.status === 'done' }">
                  <div class="kb-card-title">{{ t.title }}</div>
                  <div class="kb-card-meta">
                    <span class="kb-pri" :class="`pri-${t.priority}`">{{ priLabel(t.priority) }}</span>
                    <span v-if="t.refNo" class="kb-ref">{{ t.refNo }}</span>
                  </div>
                  <div v-if="t.sourceLabel" class="kb-src">📁 {{ t.sourceLabel }}</div>
                  <div class="kb-foot">
                    <span v-if="t.assignee" class="kb-assignee">{{ t.assignee }}</span>
                    <span v-if="t.due" class="kb-due">⏱ {{ t.due }}</span>
                  </div>
                </div>
                <p v-if="!col.items.length" class="kb-empty">暂无</p>
              </div>
            </div>
          </div>
        </template>

        <!-- ===== 频道 ===== -->
        <template v-else>
        <div v-if="currentRoom" class="ch-header">
          <button class="ch-fav" :class="{ active: fav }" :title="fav ? '取消收藏' : '收藏'" @click="toggleFav">
            <svg width="16" height="16" viewBox="0 0 24 24" :fill="fav ? 'currentColor' : 'none'" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" /></svg>
          </button>
          <span class="ch-av" :style="{ background: colorOf(currentName) }">{{ iconChar(currentName) }}</span>
          <button class="title title-btn" :title="'频道设置'" @click="openChannelSettings">{{ currentName }}<svg class="chev" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6" /></svg></button>
          <div v-if="currentTopic" class="ch-topic">{{ currentTopic }}</div>
          <div class="ch-actions">
            <button class="ch-members-btn" title="成员 · 邀请" @click="openMembers">
              <div class="ava-stack">
                <div v-for="m in channelMembers.slice(0, 3)" :key="m.id" class="a" :class="{ bot: m.isBot }">{{ m.isBot ? '智' : initials(m.name) }}</div>
              </div>
              <span class="ch-members-count">{{ channelMembers.length }}</span>
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

        <!-- 消息流（Discord 风：分组 / 日期线 / 回复 / 反应 / 悬停工具条）-->
        <div class="stream">
          <template v-for="m in groupedMsgs" :key="m.id">
          <!-- 日期分隔线 -->
          <div v-if="m.showDay" class="day-sep"><span>{{ dayLabel(m.ts) }}</span></div>
          <div class="msg" :class="{ bot: isBot(m.sender), me: isMe(m.sender), grouped: !m.showHeader }">
            <!-- 回复预览：整行浮在头像上方（Discord 风：弯角连接线 + ↩ + 名字上色 + 正文淡色）-->
            <div v-if="m.replyToId" class="msg-reply">
              <span class="reply-av" :class="{ bot: isBot(m.replyToSender || '') }" :style="isBot(m.replyToSender || '') ? undefined : { background: nameColor(m.replyToName || '') }">{{ isBot(m.replyToSender || '') ? '智' : initials(m.replyToName || '') }}</span>
              <span class="reply-name" :style="{ color: nameColor(m.replyToName || '') }">{{ (m.replyToName || '').replace(/^@/, '') }}</span>
              <span v-if="isBot(m.replyToSender || '')" class="reply-app">APP</span>
              <span class="reply-body">{{ m.replyToBody }}</span>
            </div>
            <div class="msg-main">
            <!-- 左槽：首条显头像，分组内显悬停时间 -->
            <div class="msg-gutter">
              <div v-if="m.showHeader" class="ava">{{ isBot(m.sender) ? '智' : initials(m.senderName) }}</div>
              <span v-else class="gutter-time">{{ fmtTime(m.ts) }}</span>
            </div>
            <div class="msg-body">
              <div v-if="m.showHeader" class="head">
                <span class="name" :style="{ color: nameColor(m.senderName) }">{{ m.senderName }}</span>
                <span v-if="isBot(m.sender)" class="app-tag">APP</span>
                <span class="time">{{ fmtTime(m.ts) }}</span>
              </div>
              <div v-if="!m.card" class="text"><span v-html="renderMd(m.body)"></span><span v-if="m.edited" class="edited">（已编辑）</span></div>
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
              <!-- 反应条 -->
              <div v-if="reactions[m.id]?.length" class="reactions">
                <button v-for="r in reactions[m.id]" :key="r.key" class="rxn" :class="{ mine: r.mine }" @click="toggleReaction(m.id, r.key)">{{ r.key }} <b>{{ r.count }}</b></button>
                <button class="rxn add" title="加表情" @click="openEmojiPicker(m.id, $event)">＋</button>
              </div>
            </div>
            </div>
            <!-- 悬停工具条（表情 / 回复 / 编辑(自己) / 复制）-->
            <div class="msg-tools">
              <button title="表情" @click="openEmojiPicker(m.id, $event)">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10" /><path d="M8 14s1.5 2 4 2 4-2 4-2M9 9h.01M15 9h.01" /></svg>
              </button>
              <button title="回复" @click="startReply(m)">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 17 4 12 9 7" /><path d="M20 18v-2a4 4 0 0 0-4-4H4" /></svg>
              </button>
              <button v-if="isMe(m.sender) && !m.card" title="编辑" @click="startEdit(m)">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" /></svg>
              </button>
              <button title="复制" @click="copyMsg(m.body)">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" /><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" /></svg>
              </button>
            </div>
          </div>
          </template>
          <p v-if="currentRoom && !msgs.length" class="hint pad">这个频道还没有消息</p>
          <p v-if="!currentRoom" class="hint pad">← 选一个频道开始</p>
        </div>

        <!-- emoji 选择器面板 -->
        <div v-if="emojiPicker" class="emoji-pop" :style="{ left: emojiPicker.x + 'px', top: emojiPicker.y + 'px' }" @click.stop>
          <div class="emoji-grid">
            <button v-for="e in EMOJIS" :key="e" class="emoji-cell" @click="pickEmoji(e)">{{ e }}</button>
          </div>
        </div>

        <!-- Composer -->
        <div v-if="currentRoom" class="composer">
          <!-- 回复横幅 -->
          <div v-if="replyTo" class="reply-bar">
            <span class="reply-bar-txt">↩ 回复 <b>{{ replyTo.name }}</b>：{{ replyTo.body.slice(0, 40) }}</span>
            <button class="reply-bar-x" title="取消回复" @click="cancelReply">×</button>
          </div>
          <!-- 编辑横幅 -->
          <div v-if="editingId" class="reply-bar">
            <span class="reply-bar-txt">✏️ 正在<b>编辑</b>消息 · Enter 保存，Esc 取消</span>
            <button class="reply-bar-x" title="取消编辑" @click="cancelEdit">×</button>
          </div>
          <div class="composer-box">
            <textarea
              ref="taRef"
              v-model="draft"
              :placeholder="`发送到 #${currentName}；叫主 AI 试：CosMac 建专班 测试专班`"
              @keydown.enter.exact.prevent="send"
              @keydown.esc="editingId ? cancelEdit() : cancelReply()"
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
        </template>
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
            <div v-if="!m.card" class="ai-bubble" v-html="renderMd(m.body)"></div>
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
          <div class="pr-icon plus" title="添加插件" @click="onPluginStore">+</div>
        </div>
        <div class="pr-divider" />
        <div class="pr-icon assets" title="资产 · 自定义配置" @click="onCustomAssets">◈</div>
        <div class="pr-icon gear" title="插件商城" @click="onPluginStore">⚙</div>
      </nav>
    </div>

    <!-- DEMO 弹窗/面板（常驻挂载，内部按各自 composable 的 visible 控制显隐）-->
    <MarketplaceModal />
    <PluginStoreModal />
    <CustomAssetsModal />
    <UserSettingsModal />
    <ProfileHome />
    <CliConsole />

    <!-- 新建工作区（完整表单 · 真建 Matrix Space + 默认频道）-->
    <div v-if="newWsOpen" class="nw-overlay" @click.self="newWsOpen = false">
      <div class="nw-modal">
        <div class="nw-title">新建工作区</div>
        <div class="nw-sub">工作区 = 一个独立空间（Space），底下挂自己的频道、成员独立</div>

        <!-- 类型 -->
        <div class="nw-field-label">类型</div>
        <div class="nw-types">
          <button
            v-for="t in WS_TYPES"
            :key="t.key"
            class="nw-type"
            :class="{ on: newWsType === t.key }"
            @click="newWsType = t.key"
          >{{ t.title }}</button>
        </div>

        <!-- 名称 -->
        <div class="nw-field-label">{{ curWsType.nameLabel }}</div>
        <input v-model="newWsName" class="nw-input" :placeholder="curWsType.namePh" @keyup.enter="createWorkspace" />

        <!-- 简称（全宽）-->
        <div class="nw-field-label">简称 <span class="nw-hint">左栏图标 · 最多 2 字 · 可留空</span></div>
        <input v-model="newWsLabel" class="nw-input" :placeholder="newWsSpaceName ? wsLabel(newWsSpaceName) : '如 制作'" />

        <!-- 可见性（全宽，两个等宽按钮）-->
        <div class="nw-field-label">可见性</div>
        <div class="nw-vis">
          <button class="nw-vis-btn" :class="{ on: !newWsPublic }" @click="newWsPublic = false">私密 · 邀请制</button>
          <button class="nw-vis-btn" :class="{ on: newWsPublic }" @click="newWsPublic = true">公开 · 可加入</button>
        </div>

        <!-- 预览：将创建什么 -->
        <div v-if="newWsName.trim()" class="nw-preview">
          <div class="nw-prev-h">将创建</div>
          <div class="nw-prev-ws"><span class="nw-prev-ic">{{ newWsLabel.trim() || wsLabel(newWsSpaceName) }}</span>工作区「{{ newWsSpaceName }}」</div>
          <div v-for="c in newWsChannels" :key="c" class="nw-prev-ch"># {{ c }}<span class="nw-prev-tip">含主 AI</span></div>
        </div>

        <div class="nw-foot">
          <button class="nw-btn" :disabled="newWsCreating" @click="newWsOpen = false">取消</button>
          <button class="nw-btn primary" :disabled="!newWsName.trim() || newWsCreating" @click="createWorkspace">{{ newWsCreating ? '创建中…' : '创建' }}</button>
        </div>
      </div>
    </div>

    <!-- 新建频道（在当前工作区下真建）-->
    <div v-if="newChOpen" class="nw-overlay" @click.self="newChOpen = false">
      <div class="nw-modal">
        <div class="nw-title">新建频道</div>
        <div class="nw-sub">将建在「{{ activeSpaceName }}」工作区下，并自动拉主 AI 进群</div>
        <div class="nw-field-label">频道名称</div>
        <input v-model="newChName" class="nw-input" placeholder="如：第二季筹备 / 海报评审" @keyup.enter="createChannel" />
        <div class="nw-field-label">简介（可选，显示在频道头）</div>
        <textarea v-model="newChTopic" class="nw-input nw-textarea" rows="2" placeholder="一句话说明这个频道是干嘛的" />
        <div class="nw-field-label">可见性</div>
        <div class="nw-vis">
          <button class="nw-vis-btn" :class="{ on: !newChPublic }" @click="newChPublic = false">私密 · 邀请制</button>
          <button class="nw-vis-btn" :class="{ on: newChPublic }" @click="newChPublic = true">公开 · 可加入</button>
        </div>
        <div v-if="newChName.trim()" class="nw-preview">
          <div class="nw-prev-h">将创建</div>
          <div class="nw-prev-ch"># {{ newChName.trim() }}<span class="nw-prev-tip">含主 AI · 归属「{{ activeSpaceName }}」</span></div>
        </div>
        <div class="nw-foot">
          <button class="nw-btn" :disabled="newChCreating" @click="newChOpen = false">取消</button>
          <button class="nw-btn primary" :disabled="!newChName.trim() || newChCreating" @click="createChannel">{{ newChCreating ? '创建中…' : '创建' }}</button>
        </div>
      </div>
    </div>

    <!-- 频道设置：改名称 / 简介（真写进 Matrix 房间）-->
    <div v-if="chSetOpen" class="nw-overlay" @click.self="chSetOpen = false">
      <div class="nw-modal">
        <div class="nw-title">频道设置</div>
        <div class="nw-sub">改这个频道的名称和简介（实时写进后端）</div>
        <div class="nw-field-label">频道名称</div>
        <input v-model="chSetName" class="nw-input" placeholder="频道名称" @keyup.enter="saveChannelSettings" />
        <div class="nw-field-label">简介</div>
        <textarea v-model="chSetTopic" class="nw-input nw-textarea" rows="2" placeholder="一句话说明这个频道是干嘛的" />
        <div class="nw-foot nw-foot-split">
          <div class="nw-foot-left">
            <button v-if="!chDeleteArm" class="nw-btn danger-outline" :disabled="chSetBusy" @click="chDeleteArm = true">删除频道</button>
            <template v-else>
              <button class="nw-btn danger" :disabled="chSetBusy" @click="deleteChannel">{{ chSetBusy ? '删除中…' : '确认删除' }}</button>
              <button class="nw-btn" :disabled="chSetBusy" title="取消删除" @click="chDeleteArm = false">×</button>
            </template>
          </div>
          <div class="nw-foot-right">
            <button class="nw-btn" :disabled="chSetBusy" @click="chSetOpen = false">取消</button>
            <button class="nw-btn primary" :disabled="!chSetName.trim() || chSetBusy" @click="saveChannelSettings">{{ chSetBusy ? '保存中…' : '保存' }}</button>
          </div>
        </div>
      </div>
    </div>

    <!-- 工作区设置：改名称 / 简称（真写进 Matrix Space）-->
    <div v-if="wsSetOpen" class="nw-overlay" @click.self="wsSetOpen = false">
      <div class="nw-modal">
        <div class="nw-title">工作区设置</div>
        <div class="nw-sub">改这个工作区的名称和左栏简称（实时写进后端）</div>
        <div class="nw-field-label">名称</div>
        <input v-model="wsSetName" class="nw-input" placeholder="工作区名称" @keyup.enter="saveWsSettings" />
        <div class="nw-field-label">简称（左栏图标，最多 2 字；上传图片后以图片为准）</div>
        <input v-model="wsSetLabel" class="nw-input" :placeholder="wsSetName ? wsLabel(wsSetName) : '如 制作'" />

        <div class="nw-field-label">图标（上传图片，可选）</div>
        <div class="nw-avatar-row">
          <span class="nw-avatar-prev" :style="!wsSetAvatarPreview ? { background: 'var(--action)' } : undefined">
            <img v-if="wsSetAvatarPreview" :src="wsSetAvatarPreview" alt="" />
            <template v-else>{{ wsSetLabel.trim() || wsLabel(wsSetName) || '?' }}</template>
          </span>
          <button class="nw-btn" :disabled="wsUploading" @click="wsFileInput?.click()">{{ wsUploading ? '上传中…' : (wsSetAvatarPreview ? '更换图片' : '上传图片') }}</button>
          <button v-if="wsSetAvatarPreview" class="nw-btn" :disabled="wsUploading" @click="removeWsImage">移除</button>
          <input ref="wsFileInput" type="file" accept="image/*" hidden @change="onPickWsImage" />
        </div>

        <div class="nw-preview" v-if="wsSetName.trim()">
          <div class="nw-prev-ws">
            <span class="nw-prev-ic" :style="wsSetAvatarPreview ? { padding: 0, overflow: 'hidden' } : undefined">
              <img v-if="wsSetAvatarPreview" :src="wsSetAvatarPreview" alt="" style="width:100%;height:100%;object-fit:cover" />
              <template v-else>{{ wsSetLabel.trim() || wsLabel(wsSetName) }}</template>
            </span>{{ wsSetName }}
          </div>
        </div>

        <div class="nw-foot nw-foot-split">
          <!-- 左：删除工作区（红色按钮 → 点一下变二次确认）-->
          <div class="nw-foot-left">
            <button v-if="!wsDeleteArm" class="nw-btn danger-outline" :disabled="wsSetBusy" @click="wsDeleteArm = true">删除工作区</button>
            <template v-else>
              <button class="nw-btn danger" :disabled="wsSetBusy" :title="`删除「${wsSetName}」及其 ${wsChildCount} 个频道，不可撤销`" @click="deleteWorkspace">{{ wsSetBusy ? '删除中…' : `确认删除（含 ${wsChildCount} 频道）` }}</button>
              <button class="nw-btn" :disabled="wsSetBusy" title="取消删除" @click="wsDeleteArm = false">×</button>
            </template>
          </div>
          <!-- 右：取消 / 保存 -->
          <div class="nw-foot-right">
            <button class="nw-btn" :disabled="wsSetBusy" @click="wsSetOpen = false">取消</button>
            <button class="nw-btn primary" :disabled="!wsSetName.trim() || wsSetBusy" @click="saveWsSettings">{{ wsSetBusy ? '保存中…' : '保存' }}</button>
          </div>
        </div>
      </div>
    </div>

    <!-- 成员管理：邀请已有用户进当前频道/工作区（真功能 · Matrix invite）-->
    <div v-if="memberOpen" class="nw-overlay" @click.self="memberOpen = false">
      <div class="nw-modal">
        <div class="nw-title">邀请成员</div>
        <div class="nw-sub">
          邀请进：<b v-if="memberTarget">{{ memberTarget.name }}</b><span v-else class="nw-warn">请先打开一个频道</span>
        </div>

        <div class="nw-field-label">邀请用户名</div>
        <div class="nw-inline">
          <input v-model="inviteUserInput" class="nw-input" placeholder="用户名 或 @用户:cosmac.cc" @keyup.enter="doInvite" />
          <button class="nw-btn primary" :disabled="!inviteUserInput.trim() || !memberTarget || memberBusy" @click="doInvite">{{ memberBusy ? '邀请中…' : '邀请' }}</button>
        </div>

        <!-- 当前真实成员 -->
        <div class="nw-field-label">当前成员 <span class="nw-hint">{{ memberList.length }} 人</span></div>
        <div class="nw-mem-list">
          <div v-for="m in memberList" :key="m.id" class="nw-mem">
            <span class="nw-mem-av" :class="{ bot: m.isBot }">{{ m.isBot ? '智' : initials(m.name) }}</span>
            <span class="nw-mem-name">{{ m.name }}</span>
            <span v-if="m.isBot" class="nw-mem-tag">AI</span>
          </div>
          <p v-if="!memberList.length" class="nw-mem-empty">还没有成员</p>
        </div>

        <div class="nw-note">
          💡 <b>新建账号 / 邀请链接</b> 需要后端支持（Synapse Admin API 不对外开放，不能从浏览器用管理员令牌建号），放到后续「成员管理后台」模块做。现在可邀请<b>已有账号</b>的用户。
        </div>

        <div class="nw-foot">
          <button class="nw-btn" :disabled="memberBusy" @click="memberOpen = false">关闭</button>
        </div>
      </div>
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
.top-brand-btn .logo { width: 26px; height: 26px; object-fit: contain; border-radius: 6px; display: block; flex-shrink: 0; }
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
.ws-icon.has-img { background: var(--bg-panel); overflow: hidden; padding: 0; }
.ws-img { width: 100%; height: 100%; object-fit: cover; display: block; }
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
/* 频道彩色图标（按名字取色 + 代表字）*/
.cs-chan-av { width: 20px; height: 20px; border-radius: 6px; flex-shrink: 0; display: inline-flex; align-items: center; justify-content: center; color: #fff; font-size: 11px; font-weight: 700; line-height: 1; }
.cs-item.active .cs-chan-av { box-shadow: 0 0 0 1.5px rgba(255,255,255,.5); }
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
/* 数据看板滚动容器 */
.board-scroll { flex: 1; overflow-y: auto; min-height: 0; }
.pinned-item { color: var(--text-2); }
.board-sub { font-size: 13px; color: var(--text-3); font-family: var(--mono); }

/* ── 任务看板（kanban 三列）── */
.kanban { flex: 1; min-height: 0; display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; padding: 16px var(--content-pad-x); overflow: hidden; }
.kb-col { display: flex; flex-direction: column; min-height: 0; background: var(--bg-soft); border-radius: 12px; overflow: hidden; }
.kb-col-head { display: flex; align-items: center; gap: 8px; padding: 12px 14px; flex-shrink: 0; }
.kb-dot { width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0; }
.kb-dot.pending { background: var(--text-dim); }
.kb-dot.in_progress { background: var(--accent); }
.kb-dot.done { background: var(--ok); }
.kb-col-title { font-weight: 700; font-size: 14px; color: var(--text); }
.kb-count { margin-left: auto; font-size: 12px; font-family: var(--mono); color: var(--text-3); background: var(--bg-panel); border: 1px solid var(--border); border-radius: 9px; padding: 1px 8px; }
.kb-cards { flex: 1; overflow-y: auto; padding: 0 10px 12px; display: flex; flex-direction: column; gap: 10px; }
.kb-card { background: var(--bg-panel); border: 1px solid var(--border); border-radius: 10px; padding: 12px; box-shadow: 0 1px 2px rgba(0,0,0,.04); }
.kb-card.done { opacity: .7; }
.kb-card.done .kb-card-title { text-decoration: line-through; color: var(--text-3); }
.kb-card-title { font-size: 14px; font-weight: 600; color: var(--text); line-height: 1.4; }
.kb-card-meta { display: flex; align-items: center; gap: 8px; margin-top: 8px; }
.kb-pri { font-family: var(--mono); font-size: 10px; padding: 1px 7px; border-radius: 9px; letter-spacing: .5px; }
.kb-pri.pri-high { background: #fee2e2; color: var(--danger); }
.kb-pri.pri-mid { background: #fef3c7; color: var(--warn); }
.kb-pri.pri-low { background: var(--bg-code); color: var(--text-3); }
.kb-ref { font-family: var(--mono); font-size: 11px; color: var(--accent); }
.kb-src { font-size: 12px; color: var(--text-3); margin-top: 8px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.kb-foot { display: flex; align-items: center; justify-content: space-between; margin-top: 8px; font-size: 12px; }
.kb-assignee { font-weight: 600; color: var(--text-2); }
.kb-due { font-family: var(--mono); color: var(--text-3); }
.kb-empty { font-size: 12px; color: var(--text-dim); padding: 10px; text-align: center; }
.ch-header { height: 50px; flex-shrink: 0; border-bottom: 1px solid var(--border); display: flex; align-items: center; gap: 10px; padding: 0 16px; background: var(--bg-panel); }
.ch-fav { width: 28px; height: 28px; background: transparent; border: none; color: var(--text-3); border-radius: 6px; display: inline-flex; align-items: center; justify-content: center; cursor: pointer; flex-shrink: 0; }
.ch-fav:hover { background: var(--bg-hover); color: var(--text); }
.ch-fav.active { color: var(--warn); }
.title { font-family: var(--font-heading); font-size: var(--fs-200); line-height: var(--lh-200); font-weight: var(--fw-bold); display: flex; align-items: center; gap: 6px; color: var(--text); flex-shrink: 0; }
.title .hash { color: var(--text-3); font-weight: 400; }
.title-btn { display: inline-flex; align-items: center; gap: 4px; background: transparent; border: 0; cursor: pointer; padding: 3px 6px; margin-left: -6px; border-radius: 7px; }
.title-btn:hover { background: var(--bg-hover); }
.title-btn .chev { color: var(--text-3); }
.ch-av { width: 24px; height: 24px; border-radius: 7px; flex-shrink: 0; display: inline-flex; align-items: center; justify-content: center; color: #fff; font-size: 12px; font-weight: 700; line-height: 1; }
.ch-topic { font-size: 13px; color: var(--text-3); border-left: 1px solid var(--border); padding-left: 12px; margin-left: 4px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0; flex: 1; }
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

/* 消息流（Discord 风：分组 / 悬停高亮 / 工具条 / 反应 / 回复）*/
.stream { flex: 1; overflow-y: auto; padding: 8px var(--content-pad-x) 20px; }
.msg { display: flex; flex-direction: column; padding: 4px 10px; margin: 0 -10px; border-radius: 4px; position: relative; }
.msg:not(.grouped) { margin-top: 18px; }
/* 有回复的消息：上方再多留点空，给连接线腾出"空行" */
.msg:not(.grouped):has(.msg-reply) { margin-top: 22px; }
.msg:hover { background: var(--bg-soft); }
.msg.unread { background: var(--accent-soft); box-shadow: inset 3px 0 0 var(--accent); }
.msg-main { display: flex; gap: 12px; }
/* 左槽：固定头像宽度；分组内放悬停才显的时间 */
.msg-gutter { width: 36px; flex-shrink: 0; display: flex; justify-content: center; }
.msg .ava { width: 40px; height: 40px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: 600; font-size: 14px; color: #fff; background: var(--text-3); position: relative; }
.msg-gutter { width: 40px; }
.msg.me .ava { background: var(--accent); color: #1a1300; }
.msg.bot .ava { background: var(--text); }
.msg.bot .ava::after { content: ""; position: absolute; bottom: -1px; right: -1px; width: 10px; height: 10px; border-radius: 50%; background: var(--accent); border: 2px solid var(--bg); }
.gutter-time { font-size: 10px; color: var(--text-dim); font-family: var(--mono); line-height: 22px; opacity: 0; }
.msg.grouped:hover .gutter-time { opacity: 1; }
.msg .msg-body { flex: 1; min-width: 0; }
.msg .head { display: flex; align-items: baseline; gap: 8px; margin-bottom: 2px; }
.msg .name { font-weight: var(--fw-bold); font-size: var(--fs-100); color: var(--text); }
.app-tag { font-size: 9px; font-weight: 700; letter-spacing: .5px; color: #fff; background: var(--accent); border-radius: 3px; padding: 1px 4px; line-height: 1.2; }
.msg .time { font-size: var(--fs-75); color: var(--text-3); }
/* 日期分隔线 */
.day-sep { display: flex; align-items: center; gap: 12px; margin: 14px 6px 6px; }
.day-sep::before, .day-sep::after { content: ""; flex: 1; height: 1px; background: var(--border); }
.day-sep span { font-size: 11px; font-weight: 600; color: var(--text-3); font-family: var(--mono); }
.msg .text { color: var(--text); font-size: var(--fs-100); line-height: var(--lh-200); word-break: break-word; }
.edited { font-size: 11px; color: var(--text-dim); margin-left: 6px; }
/* @提及高亮 */
.text :deep(.mention), .ai-bubble :deep(.mention) { background: var(--accent-soft); color: var(--warn); border-radius: 4px; padding: 0 3px; font-weight: 600; }
/* 回复预览（整行浮在头像上方 · 弯角连接线 + ↩ + 名字上色 + 正文淡色）*/
.msg-reply { position: relative; display: flex; align-items: center; gap: 5px; font-size: 13px; line-height: 1.2; padding-left: 52px; margin-bottom: 7px; min-width: 0; color: var(--text-3); }
/* 连接线：从回复行中部下探到下方头像，顶部弧向右接到回复文字 */
.msg-reply::before { content: ""; position: absolute; left: 20px; top: 11px; bottom: -13px; width: 27px; border-left: 2px solid var(--border); border-top: 2px solid var(--border); border-top-left-radius: 8px; }
.reply-av { width: 16px; height: 16px; border-radius: 50%; flex-shrink: 0; display: inline-flex; align-items: center; justify-content: center; color: #fff; font-size: 9px; font-weight: 700; line-height: 1; background: var(--text-3); }
.reply-av.bot { background: var(--text); }
.reply-name { font-weight: 600; flex-shrink: 0; }
.reply-name:hover { text-decoration: underline; cursor: pointer; }
.reply-app { font-size: 8px; font-weight: 700; letter-spacing: .4px; color: #fff; background: var(--accent); border-radius: 3px; padding: 0 3px; flex-shrink: 0; }
.reply-body { color: var(--text-3); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0; }
/* 反应条 */
.reactions { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 5px; }
.rxn { display: inline-flex; align-items: center; gap: 4px; height: 24px; padding: 0 8px; border: 1px solid var(--border); border-radius: 12px; background: var(--bg-panel); cursor: pointer; font-size: 13px; color: var(--text-2); }
.rxn b { font-size: 12px; }
.rxn:hover { border-color: var(--accent); }
.rxn.mine { background: var(--accent-soft); border-color: var(--accent); color: var(--warn); }
.rxn.add { padding: 0 7px; color: var(--text-3); }
/* 悬停工具条 */
.msg-tools { position: absolute; top: -12px; right: 12px; display: none; gap: 2px; background: var(--bg-panel); border: 1px solid var(--border); border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,.1); padding: 2px; }
.msg:hover .msg-tools { display: flex; }
.msg-tools button { width: 28px; height: 26px; border: 0; background: transparent; border-radius: 6px; cursor: pointer; font-size: 14px; display: inline-flex; align-items: center; justify-content: center; color: var(--text-2); }
.msg-tools button:hover { background: var(--bg-hover); }
/* emoji 选择器 */
.emoji-pop { position: fixed; z-index: 120; width: 248px; background: var(--bg-panel); border: 1px solid var(--border); border-radius: 12px; box-shadow: 0 12px 36px rgba(0,0,0,.16); padding: 8px; }
.emoji-grid { display: grid; grid-template-columns: repeat(8, 1fr); gap: 2px; max-height: 200px; overflow-y: auto; }
.emoji-cell { width: 28px; height: 28px; border: 0; background: transparent; border-radius: 6px; cursor: pointer; font-size: 17px; display: inline-flex; align-items: center; justify-content: center; }
.emoji-cell:hover { background: var(--bg-hover); }
/* 回复横幅 */
.reply-bar { display: flex; align-items: center; gap: 8px; background: var(--bg-soft); border: 1px solid var(--border); border-bottom: 0; border-radius: 10px 10px 0 0; padding: 6px 12px; font-size: 12px; color: var(--text-3); }
.reply-bar-txt { flex: 1; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.reply-bar-txt b { color: var(--accent); }
.reply-bar-x { width: 22px; height: 22px; border: 0; background: transparent; border-radius: 6px; cursor: pointer; color: var(--text-3); font-size: 16px; line-height: 1; }
.reply-bar-x:hover { background: var(--bg-hover); color: var(--text); }
/* 消息里渲染出的 Markdown 元素 */
.text :deep(a), .ai-bubble :deep(a) { color: var(--info); text-decoration: underline; }
.text :deep(code.md-code), .ai-bubble :deep(code.md-code) { background: var(--bg-code); padding: 1px 5px; border-radius: 4px; font-family: var(--mono); font-size: 12.5px; }
.text :deep(pre.md-pre), .ai-bubble :deep(pre.md-pre) { background: var(--bg-code); padding: 10px 12px; border-radius: 8px; font-family: var(--mono); font-size: 12.5px; overflow-x: auto; margin: 6px 0; white-space: pre-wrap; word-break: break-word; }
.text :deep(strong), .ai-bubble :deep(strong) { font-weight: 700; }
.text :deep(del), .ai-bubble :deep(del) { opacity: .7; }
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

/* ──── 新建工作区弹窗 ──── */
.nw-overlay { position: fixed; inset: 0; z-index: 120; background: rgba(20,18,15,.35); display: flex; align-items: center; justify-content: center; animation: toast-in .12s ease; }
.nw-modal { width: 440px; max-width: 92vw; max-height: 88vh; overflow-y: auto; background: var(--bg-panel); border: 1px solid var(--border); border-radius: 14px; padding: 22px; box-shadow: 0 24px 64px rgba(0,0,0,.22); }
.nw-title { font-family: var(--font-heading); font-size: 18px; font-weight: 700; color: var(--text); }
.nw-sub { font-size: 12px; color: var(--text-3); margin: 6px 0 14px; line-height: 1.5; }
.nw-field-label { font-size: 12px; color: var(--text-3); margin: 12px 0 6px; }
.nw-hint { font-size: 11px; color: var(--text-dim); margin-left: 4px; }
.nw-types { display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; }
.nw-type { height: 34px; border: 1px solid var(--border); border-radius: 9px; background: var(--bg); color: var(--text-2); font-size: 13px; cursor: pointer; }
.nw-type:hover { background: var(--bg-hover); }
.nw-type.on { background: var(--accent-soft); border-color: var(--accent); color: var(--accent); font-weight: 700; }
.nw-input { width: 100%; height: 40px; padding: 0 13px; border: 1px solid var(--border); border-radius: 10px; background: var(--bg); font-size: 14px; color: var(--text); outline: none; }
.nw-input:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }
.nw-textarea { height: auto; padding: 10px 13px; resize: vertical; font-family: var(--font-body); line-height: 1.5; }
.nw-row2 { display: grid; grid-template-columns: 1fr 1.4fr; gap: 12px; }
.nw-col { min-width: 0; }
.nw-vis { display: flex; gap: 6px; }
.nw-vis-btn { flex: 1; height: 40px; border: 1px solid var(--border); border-radius: 10px; background: var(--bg); color: var(--text-2); font-size: 12px; cursor: pointer; }
.nw-vis-btn:hover { background: var(--bg-hover); }
.nw-vis-btn.on { background: var(--accent-soft); border-color: var(--accent); color: var(--accent); font-weight: 700; }
.nw-preview { margin-top: 14px; background: var(--bg-soft); border: 1px solid var(--border-soft); border-radius: 10px; padding: 12px 14px; }
.nw-prev-h { font-size: 11px; color: var(--text-3); font-family: var(--mono); letter-spacing: .08em; margin-bottom: 8px; }
.nw-prev-ws { display: flex; align-items: center; gap: 8px; font-size: 14px; font-weight: 600; color: var(--text); margin-bottom: 6px; }
.nw-prev-ic { width: 24px; height: 24px; border-radius: 7px; background: var(--action); color: #fff; display: inline-flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 700; }
.nw-prev-ch { display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--text-2); padding: 3px 0 3px 6px; }
.nw-prev-tip { font-size: 10px; color: var(--text-3); background: var(--bg-panel); border: 1px solid var(--border); border-radius: 8px; padding: 0 6px; }
.nw-inline { display: flex; gap: 8px; }
.nw-inline .nw-input { flex: 1; }
.nw-inline .nw-btn { flex-shrink: 0; }
.nw-divider { height: 1px; background: var(--border-soft); margin: 16px 0 4px; }
.nw-check { display: flex; align-items: center; gap: 8px; margin-top: 12px; font-size: 13px; color: var(--text-2); cursor: pointer; }
.nw-check input { width: 15px; height: 15px; accent-color: var(--accent); }
.nw-warn { color: var(--warn); }
.nw-note { margin-top: 14px; background: var(--accent-soft); border: 1px solid #f4e0bd; border-radius: 10px; padding: 10px 12px; font-size: 12px; line-height: 1.6; color: var(--text-2); }
.nw-mem-list { max-height: 200px; overflow-y: auto; border: 1px solid var(--border); border-radius: 10px; }
.nw-mem { display: flex; align-items: center; gap: 8px; padding: 8px 12px; border-bottom: 1px solid var(--border-soft); }
.nw-mem:last-child { border-bottom: 0; }
.nw-mem-av { width: 24px; height: 24px; border-radius: 7px; background: var(--accent); color: #fff; display: inline-flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 700; flex-shrink: 0; }
.nw-mem-av.bot { background: var(--text); }
.nw-mem-name { flex: 1; font-size: 14px; color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.nw-mem-tag { font-size: 10px; font-family: var(--mono); color: var(--accent); background: var(--accent-soft); border-radius: 8px; padding: 1px 7px; }
.nw-mem-empty { font-size: 13px; color: var(--text-3); padding: 14px; text-align: center; }
.nw-foot { display: flex; justify-content: flex-end; gap: 10px; margin-top: 18px; }
.nw-btn { height: 36px; padding: 0 16px; border: 1px solid var(--border); border-radius: 9px; background: var(--bg-panel); color: var(--text-2); font-size: 14px; cursor: pointer; }
.nw-btn:hover { background: var(--bg-hover); color: var(--text); }
.nw-btn.primary { background: var(--accent); border-color: var(--accent); color: #1a1300; font-weight: 700; }
.nw-btn.primary:hover { filter: brightness(1.05); background: var(--accent); }
.nw-btn.primary:disabled { background: var(--border); border-color: var(--border); color: var(--text-dim); cursor: not-allowed; }
.nw-btn.danger { background: var(--danger); border-color: var(--danger); color: #fff; font-weight: 700; }
.nw-btn.danger:hover { filter: brightness(1.05); }
.nw-btn.danger-outline { background: transparent; border-color: var(--danger); color: var(--danger); }
.nw-btn.danger-outline:hover { background: #fdecec; }
.nw-foot-split { justify-content: space-between; }
.nw-foot-left, .nw-foot-right { display: flex; gap: 10px; }
.nw-avatar-row { display: flex; align-items: center; gap: 10px; }
.nw-avatar-prev { width: 44px; height: 44px; border-radius: 11px; flex-shrink: 0; display: inline-flex; align-items: center; justify-content: center; color: #fff; font-size: 15px; font-weight: 700; overflow: hidden; }
.nw-avatar-prev img { width: 100%; height: 100%; object-fit: cover; }

/* ──── toast ──── */
.toast-host { position: fixed; right: 18px; bottom: 18px; z-index: 200; display: flex; flex-direction: column; gap: 10px; }
.toast { min-width: 220px; max-width: 320px; padding: 12px 14px; background: var(--bg-panel); border: 1px solid var(--border); border-left: 3px solid var(--accent); border-radius: 10px; box-shadow: 0 10px 30px rgba(0,0,0,.12); animation: toast-in .18s ease; }
.toast-title { font-size: 14px; font-weight: 700; color: var(--text); }
.toast-msg { font-size: 12px; color: var(--text-3); margin-top: 3px; }
@keyframes toast-in { from { opacity: 0; transform: translateX(12px); } to { opacity: 1; transform: none; } }
</style>
