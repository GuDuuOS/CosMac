import { ref } from 'vue'
import { useRightPanel } from '@/composables/useRightPanel'

/** AI 助手侧栏的可见状态 */
const visible = ref(false)
/** dock 模式下：是否展开（720px 浮层） */
const expanded = ref(false)
/** 放大模式：全屏弹窗，布局对齐 Cowork（左导航栏 + 中对话 + 右进度/文件） */
const maximized = ref(false)

/** 打开主 AI 时，自动收起右侧「关于此频道」面板，避免两栏挤占空间 */
function closeRightPanel() {
  useRightPanel().hide()
}

export function useAiPanel() {
  return {
    visible,
    expanded,
    maximized,
    show:           () => { visible.value = true; closeRightPanel() },
    hide:           () => { visible.value = false; expanded.value = false; maximized.value = false },
    toggle:         () => {
      visible.value = !visible.value
      if (visible.value) closeRightPanel()
      else { expanded.value = false; maximized.value = false }
    },
    toggleExpanded: () => {
      expanded.value = !expanded.value
      if (expanded.value) maximized.value = false
    },
    // 放大 / 还原：进入放大态时退出 720px 展开态，二者互斥
    toggleMaximized: () => {
      maximized.value = !maximized.value
      if (maximized.value) expanded.value = false
    }
  }
}
