import { ref } from 'vue'
import { getMyUsage, type UsageItem } from '@/matrix/client'

/** 「我的额度」弹窗（变现第二步）：展示各计量项的 已用/上限。模块级单例。 */
const visible = ref(false)
const items = ref<UsageItem[]>([])
const loading = ref(false)

export function useMyUsage() {
  async function load() {
    loading.value = true
    try { items.value = await getMyUsage() } finally { loading.value = false }
  }
  function open() { visible.value = true; load() }
  function close() { visible.value = false }
  return { visible, items, loading, open, close, load }
}
