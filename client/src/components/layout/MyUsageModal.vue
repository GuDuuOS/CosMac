<template>
  <div v-if="visible" class="uq-overlay" @click.self="close">
    <div class="uq-modal" role="dialog" aria-modal="true">
      <div class="uq-head">
        <div class="uq-title-wrap">
          <span class="uq-title">我的额度</span>
          <span class="uq-sub">免费版有用量上限，升级会员解锁更多</span>
        </div>
        <button class="uq-close" title="关闭" @click="close">×</button>
      </div>
      <div class="uq-body">
        <div v-if="loading" class="uq-empty">加载额度…</div>
        <ul v-else-if="items.length" class="uq-list">
          <li v-for="u in items" :key="u.key" class="uq-item">
            <div class="uq-item-top">
              <span class="uq-name">{{ u.label }}</span>
              <span class="uq-val" :class="{ over: u.limit >= 0 && u.used >= u.limit }">
                {{ u.used }}<template v-if="u.limit >= 0"> / {{ u.limit }}</template>
                <span v-else class="uq-unlimited">不限</span>
              </span>
            </div>
            <div v-if="u.limit >= 0" class="uq-bar">
              <div class="uq-bar-fill" :class="{ over: u.used >= u.limit }" :style="{ width: pct(u) + '%' }" />
            </div>
          </li>
        </ul>
        <div v-else class="uq-empty">暂时拿不到额度信息。</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useMyUsage } from '@/composables/useMyUsage'
import type { UsageItem } from '@/matrix/client'
const { visible, items, loading, close } = useMyUsage()
function pct(u: UsageItem): number {
  if (u.limit <= 0) return 0
  return Math.min(100, Math.round((u.used / u.limit) * 100))
}
</script>

<style scoped>
.uq-overlay { position: fixed; inset: 0; z-index: 210; background: rgba(0,0,0,0.34); display: flex; align-items: center; justify-content: center; }
.uq-modal { width: min(440px, 94vw); max-height: 80vh; display: flex; flex-direction: column; background: var(--bg-panel); border-radius: 16px; box-shadow: 0 28px 72px rgba(0,0,0,0.24); overflow: hidden; }
.uq-head { display: flex; align-items: center; gap: 16px; padding: 16px 20px; border-bottom: 1px solid var(--border); }
.uq-title-wrap { display: flex; flex-direction: column; gap: 2px; }
.uq-title { font-family: var(--font-heading); font-weight: var(--fw-bold); font-size: var(--fs-400); color: var(--text); }
.uq-sub { font-size: var(--fs-75); color: var(--text-3); }
.uq-close { margin-left: auto; width: 30px; height: 30px; border: none; background: transparent; font-size: 22px; color: var(--text-3); cursor: pointer; border-radius: 6px; }
.uq-close:hover { background: var(--bg-hover); color: var(--text); }
.uq-body { flex: 1; overflow-y: auto; padding: 16px 20px; }
.uq-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 16px; }
.uq-item-top { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: 6px; }
.uq-name { font-size: var(--fs-100); color: var(--text); }
.uq-val { font-size: var(--fs-75); color: var(--text-2); font-weight: var(--fw-bold); }
.uq-val.over { color: #c0392b; }
.uq-unlimited { color: #2f7d4f; }
.uq-bar { height: 7px; border-radius: 999px; background: var(--bg-soft); overflow: hidden; }
.uq-bar-fill { height: 100%; background: var(--accent); border-radius: 999px; transition: width 0.2s ease; }
.uq-bar-fill.over { background: #c0392b; }
.uq-empty { padding: 30px 12px; text-align: center; color: var(--text-3); font-size: var(--fs-75); }
</style>
