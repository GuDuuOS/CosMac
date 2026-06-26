import { ref, computed, type Ref } from 'vue'

/**
 * 通用列表搜索：给一个数据源 ref + "取可搜索文本"函数，返回 query ref 和过滤后的列表。
 * 后台各列表页（用户/频道/技能/智能体/模板/工作流/套餐…）复用它，避免每页重写一遍过滤。
 */
export function useListSearch<T>(source: Ref<T[]>, textOf: (item: T) => string) {
  const query = ref('')
  const filtered = computed(() => {
    const q = query.value.trim().toLowerCase()
    if (!q) return source.value
    return source.value.filter((it) => textOf(it).toLowerCase().includes(q))
  })
  return { query, filtered }
}
