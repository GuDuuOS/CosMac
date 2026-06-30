import { reactive, ref } from 'vue'
import { currentUser } from '@/data/channels'
import { getMyProfile, saveMyProfile, type MyAiProfile } from '@/matrix/client'

/** 我的权限（可开关）*/
export interface UserPermission { label: string; desc?: string; enabled: boolean }
/** 可被他人 / AI 调用的我的数据 */
export interface ShareableDatum { label: string; value: string; shared: boolean }

const handle = '@xiaoyu'

/** 个人设置弹窗 */
export type UserSettingsTab = 'profile' | 'ai' | 'perms' | 'share'

// —— AI 偏好画像（About me / Outputs）：真实存取 cosmac DB（经 bot 端点）——
// 模块级单例：弹窗打开时 load 一次、保存时回写。
const aiProfile = reactive<MyAiProfile>({ about: '', style: '', extra: '', enabled: true })
const aiLoading = ref(false)
const aiSaving = ref(false)
const aiSavedTip = ref(false) // 保存成功后短暂显示「已保存」
const settingsVisible = ref(false)
const settingsTab = ref<UserSettingsTab>('profile')
const status = ref<'在线' | '忙碌' | '离开' | '隐身'>('在线')

const permissions = reactive<UserPermission[]>([
  { label: '审核成片 / 商单报价', desc: '对外内容终审', enabled: true },
  { label: '一键定时发布',        desc: '多平台排期发布', enabled: true },
  { label: '全平台数据查看',      desc: '播放 / 涨粉 / 变现汇总', enabled: true },
  { label: '授权 AI 代我起草与复盘', desc: '标题、脚本、周报初稿', enabled: true },
  { label: 'AI 对外动作需我确认',  desc: '发布 / 报价人工把关', enabled: true }
])

const shareableData = reactive<ShareableDatum[]>([
  { label: '我的待办与审核状态', value: '6 项待办', shared: true },
  { label: '我的账号实时 KPI', value: '播放 / 涨粉', shared: true },
  { label: '我的日程 / 在线状态', value: '在线', shared: false },
  { label: '我的选题偏好记录', value: '近 30 天', shared: false }
])

/** 拉取本人 AI 偏好画像填进表单（失败静默，保持空白默认）。 */
async function loadAiProfile() {
  aiLoading.value = true
  try {
    const p = await getMyProfile()
    aiProfile.about = p.about
    aiProfile.style = p.style
    aiProfile.extra = p.extra
    aiProfile.enabled = p.enabled
  } finally {
    aiLoading.value = false
  }
}

/** 保存 AI 偏好画像；成功短暂提示「已保存」。失败抛出（由 UI catch 提示）。 */
async function saveAiProfile() {
  aiSaving.value = true
  try {
    const p = await saveMyProfile({ ...aiProfile })
    aiProfile.about = p.about
    aiProfile.style = p.style
    aiProfile.extra = p.extra
    aiProfile.enabled = p.enabled
    aiSavedTip.value = true
    setTimeout(() => { aiSavedTip.value = false }, 1800)
  } finally {
    aiSaving.value = false
  }
}

export function useUserProfile() {
  return {
    user: currentUser,
    handle,
    status,
    permissions,
    shareableData,
    settingsVisible,
    settingsTab,
    // AI 偏好画像（真实存取）
    aiProfile,
    aiLoading,
    aiSaving,
    aiSavedTip,
    loadAiProfile,
    saveAiProfile,
    openSettings: (tab: UserSettingsTab = 'profile') => {
      settingsTab.value = tab
      settingsVisible.value = true
      // 打开即拉一次最新画像（无论从哪个 tab 进，进 AI tab 时已有数据）
      loadAiProfile()
    },
    closeSettings: () => { settingsVisible.value = false }
  }
}
