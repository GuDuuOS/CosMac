<template>
  <div class="dr">
    <!-- 详情：看单篇文章 -->
    <template v-if="current">
      <div class="dr-detail">
        <button class="dr-back" @click="current = null">← 返回列表</button>
        <h1 class="dr-title">{{ current.title || '未命名' }}</h1>
        <div class="dr-meta">{{ fmtTime(current.updated_ts) }}<span v-if="current.updated_by"> · {{ shortId(current.updated_by) }}</span></div>
        <img v-if="current.cover" class="dr-cover-banner" :src="coverUrl(current.cover)" alt="封面" />
        <!-- eslint-disable-next-line vue/no-v-html -->
        <article class="dr-body md" v-html="renderMarkdown(current.content_md || '')"></article>
      </div>
    </template>

    <!-- 列表：文章卡片（类公众号）-->
    <template v-else>
      <div class="dr-head">
        <span class="dr-h-title">📰 图文教程</span>
        <button class="dr-refresh" title="刷新" :disabled="loading" @click="load">{{ loading ? '加载中…' : '刷新' }}</button>
      </div>
      <div v-if="loading && !articles.length" class="dr-hint">加载中…</div>
      <div v-else-if="locked" class="dr-hint">
        🔒 图文教程是<b>付费会员</b>专享内容。<br>
        <span class="dr-hint-sub">升级会员后即可查看（在「升级会员」里开通）。</span>
      </div>
      <div v-else-if="!articles.length" class="dr-hint">
        这里还没有内容。<br><span class="dr-hint-sub">内容由管理员在「管理后台 → 图文教程」里编辑发布。</span>
      </div>
      <div v-else class="dr-list">
        <button v-for="a in articles" :key="a.id" class="dr-card" @click="open(a.id)">
          <div class="dr-card-body">
            <div class="dr-card-title">{{ a.title || '未命名' }}</div>
            <div v-if="a.excerpt" class="dr-card-ex">{{ a.excerpt }}</div>
            <div class="dr-card-meta">{{ fmtTime(a.updated_ts) }}</div>
          </div>
          <img v-if="a.cover" class="dr-card-cover" :src="coverUrl(a.cover, 200)" alt="" />
        </button>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { docTree, docGetPage, docCoverUrl, type DocPage } from '@/matrix/client'
import { renderMarkdown } from '@/utils/md'

const coverUrl = docCoverUrl

const articles = ref<DocPage[]>([])
const current = ref<DocPage | null>(null)
const loading = ref(false)
const locked = ref(false)   // 被付费门控拦下(非付费会员)

async function load() {
  loading.value = true
  try {
    const res = await docTree()
    locked.value = res.locked
    // 公众号式：扁平文章列表，按手动排序(sort)再 id 稳定排列
    articles.value = [...res.pages].sort((a, b) => a.sort - b.sort || a.id - b.id)
  } finally {
    loading.value = false
  }
}

async function open(id: number) {
  const p = await docGetPage(id)
  if (p) current.value = p
}

function fmtTime(ts?: number): string {
  if (!ts) return ''
  const d = new Date(ts * 1000)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
function shortId(uid: string): string { return uid.replace(/^@/, '').split(':')[0] }

onMounted(load)
</script>

<style scoped>
.dr { height: 100%; overflow-y: auto; background: #fff; }
.dr-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 20px 32px 12px; border-bottom: 1px solid #eee9e1;
}
.dr-h-title { font-size: 18px; font-weight: 700; color: #2c2a26; }
.dr-refresh {
  border: 1px solid #d8d2c8; background: #fff; color: #6b665e; border-radius: 8px;
  padding: 5px 12px; font-size: 13px; cursor: pointer;
}
.dr-hint { padding: 48px 32px; color: #ada699; font-size: 14px; line-height: 2; }
.dr-hint-sub { font-size: 12px; color: #c2bcb0; }

.dr-list { padding: 16px 24px 40px; display: flex; flex-direction: column; gap: 12px; max-width: 760px; }
.dr-card {
  display: flex; align-items: stretch; gap: 14px;
  text-align: left; border: 1px solid #eae6df; background: #fff; border-radius: 12px;
  padding: 16px 18px; cursor: pointer; transition: box-shadow .15s, border-color .15s;
}
.dr-card:hover { border-color: #d8c4ba; box-shadow: 0 2px 12px rgba(201,100,66,.08); }
.dr-card-body { flex: 1; min-width: 0; }
.dr-card-cover { width: 96px; height: 72px; object-fit: cover; border-radius: 8px; flex-shrink: 0; }
.dr-card-title { font-size: 16px; font-weight: 600; color: #2c2a26; }
.dr-card-ex { font-size: 13px; color: #8a8378; margin-top: 6px; line-height: 1.6; }
.dr-card-meta { font-size: 12px; color: #ada699; margin-top: 8px; }
.dr-cover-banner { display: block; width: 100%; max-height: 320px; object-fit: cover; border-radius: 10px; margin: 4px 0 16px; }

.dr-detail { padding: 20px 32px 48px; max-width: 760px; }
.dr-back {
  border: none; background: transparent; color: #c96442; cursor: pointer;
  font-size: 13px; padding: 4px 0; margin-bottom: 8px;
}
.dr-title { font-size: 26px; font-weight: 700; color: #2c2a26; margin: 4px 0 6px; }
.dr-meta { font-size: 12px; color: #ada699; margin-bottom: 18px; }
.dr-body { font-size: 15px; line-height: 1.85; color: #2c2a26; }

/* Markdown 渲染（与编辑器一致） */
.md :deep(h1) { font-size: 22px; margin: 20px 0 10px; }
.md :deep(h2) { font-size: 18px; margin: 18px 0 8px; }
.md :deep(h3) { font-size: 16px; margin: 16px 0 6px; }
.md :deep(p) { margin: 10px 0; }
.md :deep(ul), .md :deep(ol) { margin: 10px 0; padding-left: 24px; }
.md :deep(li) { margin: 4px 0; }
.md :deep(blockquote) { margin: 12px 0; padding: 6px 14px; border-left: 3px solid #d8d2c8; color: #6b665e; background: #faf9f6; }
.md :deep(.md-pre) { background: #2c2a26; color: #f1efe9; border-radius: 8px; padding: 12px 14px; overflow-x: auto; font-size: 13px; line-height: 1.5; }
.md :deep(.md-code) { background: #f1efe9; border-radius: 4px; padding: 1px 5px; font-size: 13px; }
.md :deep(.md-img) { max-width: 100%; border-radius: 8px; margin: 10px 0; }
.md :deep(a) { color: #c96442; }
.md :deep(.mention) { color: #4a7a8c; font-weight: 600; }
</style>
