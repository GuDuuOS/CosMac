import { reactive, ref, watch } from 'vue'
import { getSocialSources, setSocialSources } from '@/matrix/client'

/**
 * 社媒数据源（数据看板真实取数的配置）。
 *
 * 设计（与模块3 工作流连接器同构，见 client.ts SOCIAL_SOURCES_EVENT 注释）：
 *  · 一个工作区(Space)一份配置，存 Matrix state event `cosmac.social_sources`，多端同步、刷新不丢。
 *  · 定义里只放「凭据名」(credName)，真正的 API key/token/cookie 在**服务端 env**，前端永不触碰。
 *  · 取数模式两种：'api'(官方开放平台 API) / 'crawl'(AI Agent 走工作流爬公开主页)。
 *  · 运行态(lastSync/lastStatus/lastError)由后端采集器回写，前端只读展示。
 *
 * 本文件只管「配置的读写」。真实采集（调 API / 跑工作流 / 写 DB / 回看板）是后端 P2~P4。
 */

/** 取数模式 */
export type SocialMode = 'api' | 'crawl'

/** 单个社媒数据源 */
export interface SocialSource {
  platform: string        // 平台 key（见 SOCIAL_PLATFORMS）
  account: string         // 账号名 / 主页 URL / UID（用于定位要抓哪个号）
  mode: SocialMode        // 取数模式：官方 API / AI 爬取
  credName?: string       // 'api' 模式：服务端 env 里的凭据名（如 YOUTUBE_API），只放名不放值
  workflow?: string       // 'crawl' 模式：用哪个工作流连接器去抓（对应 cosmac.workflows 里的 name）
  intervalH?: number      // 轮询间隔（小时），后端采集器按此定时
  enabled: boolean        // 是否启用采集
  // ↓ 运行态：后端回写，前端只读（P2 起才有值）
  lastSync?: number       // 最近同步时间戳(ms)
  lastStatus?: 'ok' | 'error' | 'never'
  lastError?: string
}

/** 支持的平台目录（前端展示用；后端适配器按 key 实现）。新增平台前后端各加一条。 */
export const SOCIAL_PLATFORMS: { key: string; label: string; icon: string }[] = [
  { key: 'douyin', label: '抖音', icon: '🎵' },
  { key: 'bilibili', label: 'B站', icon: '📺' },
  { key: 'youtube', label: 'YouTube', icon: '▶️' },
  { key: 'xiaohongshu', label: '小红书', icon: '📕' },
  { key: 'weibo', label: '微博', icon: '🔶' },
  { key: 'x', label: 'X / Twitter', icon: '✖️' },
]
export function platformLabel(key: string): string {
  return SOCIAL_PLATFORMS.find((p) => p.key === key)?.label || key
}
export function platformIcon(key: string): string {
  return SOCIAL_PLATFORMS.find((p) => p.key === key)?.icon || '🌐'
}

/* ===== 模块级单例状态（跨组件共享）===== */
const spaceId = ref('')
const sources = ref<SocialSource[]>([])
const saveState = ref<'idle' | 'saving' | 'saved' | 'error'>('idle')
const modalOpen = ref(false)
let suppress = false // 加载期抑制回写（避免"加载即保存"的回声）

/** 从当前 Space 的 state event 读配置 */
function load() {
  const saved = spaceId.value ? getSocialSources(spaceId.value) : {}
  suppress = true
  sources.value = Array.isArray(saved.sources) ? saved.sources : []
  setTimeout(() => { suppress = false }, 0)
}

/** 防抖整体写回 Space 的 state event */
let timer: ReturnType<typeof setTimeout> | null = null
function persist() {
  if (!spaceId.value) return
  if (timer) clearTimeout(timer)
  saveState.value = 'saving'
  timer = setTimeout(async () => {
    try {
      await setSocialSources(spaceId.value, { sources: sources.value.map((s) => ({ ...s })) })
      saveState.value = 'saved'
    } catch {
      saveState.value = 'error' // 多半是当前用户在该工作区没改配置的权限
    }
  }, 600)
}

watch(sources, () => { if (!suppress && spaceId.value) persist() }, { deep: true })

export function useSocialSources() {
  return {
    sources,
    saveState,
    modalOpen,
    /** 切换当前工作区（LiveView 在 activeSpace 变化时调用）*/
    setSpace(id?: string) {
      spaceId.value = id || ''
      load()
    },
    /** 打开配置弹窗（打开前刷新一遍，防 Space 状态还没 sync）*/
    openModal() {
      load()
      saveState.value = 'idle'
      modalOpen.value = true
    },
    closeModal() { modalOpen.value = false },
    /** 新增一个数据源（带默认值）*/
    addSource(s: Partial<SocialSource>) {
      sources.value.push({
        platform: s.platform || SOCIAL_PLATFORMS[0].key,
        account: (s.account || '').trim(),
        mode: s.mode || 'api',
        credName: s.credName?.trim() || undefined,
        workflow: s.workflow?.trim() || undefined,
        intervalH: s.intervalH ?? 6,
        enabled: s.enabled ?? true,
        lastStatus: 'never',
      })
    },
    /** 移除一个数据源 */
    removeSource(i: number) { sources.value.splice(i, 1) },
  }
}
