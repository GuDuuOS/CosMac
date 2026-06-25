import { ref, reactive } from 'vue'
import {
  isOnboarded, setOnboarded,
  createSpace, createChannelInSpace, setAiConfig, getAiConfig,
} from '@/matrix/client'
import { templateOf, type OnboardingTemplate } from '@/data/onboardingTemplates'

/**
 * 首次引导（注册/登录后的「主 AI 问答」向导）。
 *
 * 机制（负责人定）：**前端脚本化对话向导**——前端用聊天 UI 按固定步骤问，
 * 像在跟中枢 AI 对话；答完直接调现有 Matrix 接口真建工作区/频道/写 AI 人设。
 * 零后端、可部署、完全可控；以后可升级为接真 LLM 的自然问答。
 *
 * 步骤：选行业模板 → 工作区名 → 初始频道(模板预填可增删) → 主 AI 人设 → 确认创建。
 * 完成/跳过都写 account data `cosmac.onboarding`，不再重复弹（见 client.ts isOnboarded/setOnboarded）。
 */

export type OnbStep = 'template' | 'name' | 'channels' | 'persona' | 'confirm' | 'creating' | 'done'

/** 聊天气泡 */
export interface OnbMsg { role: 'ai' | 'user'; text: string }

interface OnbAnswers {
  templateKey: string
  workspace: string
  channels: string[]
  aiName: string
  aiPersona: string
}

/* ===== 模块级单例 ===== */
const visible = ref(false)
const step = ref<OnbStep>('template')
const messages = ref<OnbMsg[]>([])
const busy = ref(false)
const error = ref('')
const createdSpaceId = ref('')
const answers = reactive<OnbAnswers>({
  templateKey: '', workspace: '', channels: [], aiName: '', aiPersona: '',
})

function ai(text: string) { messages.value.push({ role: 'ai', text }) }
function user(text: string) { messages.value.push({ role: 'user', text }) }

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
  ai('👋 欢迎来到 CosMac Star！我是你的中枢 AI。')
  ai('先花一分钟把你的工作台搭起来——你主要做哪个方向？')
}

export function useOnboarding() {
  return {
    visible, step, messages, busy, error, answers, createdSpaceId,

    /** 登录后调用：没引导过才自动弹（已引导/已跳过则什么都不做）。 */
    maybeAutoStart() {
      if (isOnboarded()) return
      reset()
      visible.value = true
    },
    /** 手动打开（如设置里「重新引导」）。 */
    open() { reset(); visible.value = true },
    close() { visible.value = false },

    /** ① 选行业模板 → 预填后进入「工作区名」 */
    pickTemplate(key: string) {
      const t: OnboardingTemplate = templateOf(key)
      answers.templateKey = key
      answers.channels = [...t.channels]
      answers.aiName = t.aiName
      answers.aiPersona = t.aiPersona
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

    /** 回到上一步重填某项（简单返回到对应 step）*/
    goStep(s: OnbStep) { step.value = s },

    /**
     * ⑤ 确认创建：真建 Space + 频道 + 写 AI 人设（best-effort），完成后标记已引导。
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
        // 2) 逐个建频道（单个失败不阻断其余）
        for (const cn of answers.channels) {
          try { await createChannelInSpace(sid, cn, { public: false }) } catch { /* 跳过失败的频道 */ }
        }
        // 3) 写主 AI 人设（控制室是管理员级，非管理员会失败——静默跳过，不阻断引导）
        try {
          const cur = await getAiConfig()
          await setAiConfig({
            provider: cur?.provider || '',
            model: cur?.model || '',
            // 把昵称 + 人设拼成 system_prompt 基底；保留已有配置里的其它设定
            system_prompt: `你叫「${answers.aiName}」。${answers.aiPersona}`,
            enabled_tools: cur?.enabled_tools ?? null,
          })
        } catch { /* 非管理员/无控制室权限：跳过 AI 人设写入 */ }
        // 4) 标记已引导
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
