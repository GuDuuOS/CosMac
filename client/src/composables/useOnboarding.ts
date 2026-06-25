import { ref, reactive } from 'vue'
import {
  isOnboarded, setOnboarded,
  createSpace, createChannelInSpace, setChannelConfig, onboardIngestKb,
  getOnboardingTemplates, type OnboardingTemplateDef,
} from '@/matrix/client'
import { ONBOARDING_TEMPLATES } from '@/data/onboardingTemplates'

/**
 * 首次引导（注册/登录后的「主 AI 问答」向导）。
 *
 * 机制（负责人定）：**前端脚本化对话向导** + **后台可配模板**——
 *  · 行业模板优先读后台 `cosmac.onboarding_templates`（管理员在「入驻模板」页配）；后台没配则
 *    回退到内置 ONBOARDING_TEMPLATES，保证总能用。
 *  · 选完按模板真建 Space + 频道；**把人设(+RULE)写进每个频道的 `cosmac.channel_config.persona`**，
 *    bot 读它后在该工作区以这个人设回应——**房间级配置普通用户自己有权限写，所以人设真生效**
 *    （旧版写全局控制室 setAiConfig 是管理员级、普通用户静默失败，故弃用）。
 *  · 模型/技能/知识库/默认工作流的绑定要写 DB 或建全局智能体，留 P2b。
 *
 * 步骤：选模板 → 工作区名 → 初始频道(可增删) → 主 AI 人设 → 确认创建。
 * 完成/跳过都写 account data `cosmac.onboarding`，不再重复弹。
 */

export type OnbStep = 'template' | 'name' | 'channels' | 'persona' | 'confirm' | 'creating' | 'done'

/** 聊天气泡 */
export interface OnbMsg { role: 'ai' | 'user'; text: string }

/** 引导里展示/使用的模板（后台模板与内置模板归一成这个形状）。 */
export interface OnbPickTemplate {
  key: string
  label: string
  icon: string
  desc: string
  channels: string[]
  aiName: string
  aiPersona: string
  rules: string
  model: string
  skillSlugs: string[]
  kbDocs: { title: string; content: string }[]
  tier: string
  paid: boolean
}

interface OnbAnswers {
  templateKey: string
  workspace: string
  channels: string[]
  aiName: string
  aiPersona: string
  rules: string
  model: string
  skillSlugs: string[]
  kbDocs: { title: string; content: string }[]
}

/* ===== 模块级单例 ===== */
const visible = ref(false)
const step = ref<OnbStep>('template')
const messages = ref<OnbMsg[]>([])
const busy = ref(false)
const error = ref('')
const createdSpaceId = ref('')
const templates = ref<OnbPickTemplate[]>([])
const answers = reactive<OnbAnswers>({
  templateKey: '', workspace: '', channels: [], aiName: '', aiPersona: '', rules: '',
  model: '', skillSlugs: [], kbDocs: [],
})

function ai(text: string) { messages.value.push({ role: 'ai', text }) }
function user(text: string) { messages.value.push({ role: 'user', text }) }

/** 把后台模板定义归一成引导用的形状。 */
function fromBackend(t: OnboardingTemplateDef): OnbPickTemplate {
  return {
    key: t.key, label: t.label, icon: t.icon || '🧩', desc: t.desc,
    channels: [...t.channels],
    aiName: '中枢 AI',           // 后台模板没单独的 AI 名字段，用默认；用户可在人设步改
    aiPersona: t.persona,
    rules: t.rules,
    model: t.model,
    skillSlugs: [...t.skillSlugs],
    kbDocs: t.kbDocs.map((d) => ({ ...d })),
    tier: t.tier || 'free',
    paid: (t.tier || 'free') !== 'free',
  }
}

/** 内置模板（后台没配时回退）。 */
function builtinTemplates(): OnbPickTemplate[] {
  return ONBOARDING_TEMPLATES.map((t) => ({
    key: t.key, label: t.label, icon: t.icon, desc: t.desc,
    channels: [...t.channels], aiName: t.aiName, aiPersona: t.aiPersona,
    rules: '', model: '', skillSlugs: [], kbDocs: [], tier: 'free', paid: false,
  }))
}

/** 加载模板：优先后台已上架的；没有则回退内置。 */
async function loadTemplates() {
  try {
    const backend = await getOnboardingTemplates()
    const enabled = backend.filter((t) => t.enabled)
    templates.value = enabled.length ? enabled.map(fromBackend) : builtinTemplates()
  } catch {
    templates.value = builtinTemplates()
  }
}

/** 复位到初始问候 */
function reset() {
  step.value = 'template'
  messages.value = []
  busy.value = false
  error.value = ''
  createdSpaceId.value = ''
  answers.templateKey = ''
  answers.workspace = ''
  answers.channels = []
  answers.aiName = ''
  answers.aiPersona = ''
  answers.rules = ''
  answers.model = ''
  answers.skillSlugs = []
  answers.kbDocs = []
  ai('👋 欢迎来到 CosMac Star！我是你的中枢 AI。')
  ai('先花一分钟把你的工作台搭起来——你主要做哪个方向？')
}

export function useOnboarding() {
  return {
    visible, step, messages, busy, error, answers, createdSpaceId, templates,

    /** 登录后调用：没引导过才自动弹（已引导/已跳过则什么都不做）。 */
    maybeAutoStart() {
      if (isOnboarded()) return
      reset()
      loadTemplates()
      visible.value = true
    },
    /** 手动打开（如设置里「重新引导」）。 */
    open() { reset(); loadTemplates(); visible.value = true },
    close() { visible.value = false },

    /** ① 选模板 → 预填后进入「工作区名」 */
    pickTemplate(key: string) {
      const t = templates.value.find((x) => x.key === key)
      if (!t) return
      answers.templateKey = key
      answers.channels = [...t.channels]
      answers.aiName = t.aiName
      answers.aiPersona = t.aiPersona
      answers.rules = t.rules
      answers.model = t.model
      answers.skillSlugs = [...t.skillSlugs]
      answers.kbDocs = t.kbDocs.map((d) => ({ ...d }))
      user(`${t.icon} ${t.label}`)
      ai(`好的，按「${t.label}」给你预置了一套频道和助手人设，后面都能改。`)
      ai('给你的工作区起个名字吧？这个名字会显示在左上角。')
      step.value = 'name'
    },

    /** ② 工作区名 → 进入「初始频道」 */
    submitName(v: string) {
      const name = v.trim()
      if (!name) return
      answers.workspace = name
      user(name)
      ai(`「${name}」收到。我先按模板给你建这几个频道，你可以加/删：`)
      step.value = 'channels'
    },

    /** ③ 频道增删 */
    addChannel(v: string) {
      const n = v.trim()
      if (n && !answers.channels.includes(n)) answers.channels.push(n)
    },
    removeChannel(i: number) { answers.channels.splice(i, 1) },

    /** 频道确认 → 进入「主 AI 人设」 */
    confirmChannels() {
      user(answers.channels.length ? answers.channels.join('、') : '（先不建频道）')
      ai('最后，给你的中枢 AI 起个名字、定个人设——它会用这个身份帮你干活：')
      step.value = 'persona'
    },

    /** ④ 主 AI 人设 → 进入「确认」 */
    submitPersona(name: string, persona: string) {
      answers.aiName = name.trim() || answers.aiName
      answers.aiPersona = persona.trim() || answers.aiPersona
      user(`${answers.aiName}：${answers.aiPersona}`)
      ai('都齐了！确认一下，我这就帮你把工作台搭起来：')
      step.value = 'confirm'
    },

    /** 回到上一步重填某项 */
    goStep(s: OnbStep) { step.value = s },

    /**
     * ⑤ 确认创建：真建 Space + 频道 + 给每个频道写人设(+RULE)，完成后标记已引导。
     * 返回新建的 spaceId（失败抛错，由 UI 显示）。
     */
    async runCreate(): Promise<string> {
      busy.value = true
      error.value = ''
      step.value = 'creating'
      try {
        // 1) 建工作区（私有）
        const sid = await createSpace(answers.workspace, { public: false, label: answers.workspace.slice(0, 2) })
        createdSpaceId.value = sid
        // 2) 逐个建频道（单个失败不阻断其余），收集成功的房间 id
        const channelIds: string[] = []
        for (const cn of answers.channels) {
          try { channelIds.push(await createChannelInSpace(sid, cn, { public: false })) } catch { /* 跳过失败的频道 */ }
        }
        // 3) 把人设(+RULE)写进每个频道的 channel_config.persona（房间级，普通用户有权限写）
        //    bot 的 _group_context 读 persona.prompt → 在该群以此人设回应，**真生效**。
        const prompt = answers.rules
          ? `${answers.aiPersona}\n\n[平台规则]\n${answers.rules}`
          : answers.aiPersona
        // 人设 + 模型 + 技能一起写进频道配置；bot 的 _group_context 会读 model/skill_slugs（P2b）
        const personaPatch = {
          persona: {
            aiName: answers.aiName, prompt,
            model: answers.model, skill_slugs: answers.skillSlugs,
          },
        }
        for (const cid of channelIds) {
          try { await setChannelConfig(cid, personaPatch) } catch { /* 单频道写失败不阻断 */ }
        }
        // 4) 把模板预置知识库文档灌进本人个人知识库（best-effort，灌不进不阻断引导）
        if (answers.kbDocs.length) {
          try { await onboardIngestKb(answers.kbDocs) } catch { /* 忽略 */ }
        }
        // 5) 标记已引导
        try { await setOnboarded(true) } catch { /* 标记失败也无妨，下次最多再问一次 */ }
        step.value = 'done'
        ai('🎉 搭好了！正在把你带进新工作区…')
        return sid
      } catch (e: any) {
        error.value = e?.message || '创建失败，请重试'
        step.value = 'confirm' // 退回确认页让用户重试
        throw e
      } finally {
        busy.value = false
      }
    },

    /** 跳过引导（也标记已引导，避免反复弹）。 */
    async skip() {
      try { await setOnboarded(true) } catch { /* 忽略 */ }
      visible.value = false
    },
  }
}
