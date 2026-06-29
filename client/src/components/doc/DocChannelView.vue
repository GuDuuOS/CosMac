<template>
  <div class="doc">
    <!-- 左：页面树 -->
    <aside class="doc-side">
      <div class="doc-side-head">
        <span class="doc-side-title">📄 页面</span>
        <button v-if="canWrite" class="doc-mini" title="新建顶级页面" @click="createPage(null)">＋</button>
      </div>
      <div v-if="!flatTree.length" class="doc-empty-tree">
        还没有页面{{ canWrite ? '，点 ＋ 新建' : '' }}
      </div>
      <ul class="doc-tree">
        <li
          v-for="n in flatTree" :key="n.id"
          class="doc-node" :class="{ active: n.id === currentId }"
          :style="{ paddingLeft: 8 + n.depth * 14 + 'px' }"
        >
          <span class="doc-node-title" @click="select(n.id)">{{ n.title || '未命名页面' }}</span>
          <span v-if="canWrite" class="doc-node-ops">
            <button class="doc-mini" title="新建子页" @click.stop="createPage(n.id)">＋</button>
            <button class="doc-mini danger" title="删除(含子页)" @click.stop="removePage(n)">×</button>
          </span>
        </li>
      </ul>
    </aside>

    <!-- 右：页面正文 -->
    <section class="doc-main">
      <div v-if="loading" class="doc-hint">加载中…</div>
      <div v-else-if="!currentId" class="doc-hint">
        {{ flatTree.length ? '选择左侧一个页面查看' : '这是一个文档频道，' + (canWrite ? '新建第一个页面开始吧' : '内容还没准备好') }}
      </div>
      <template v-else>
        <header class="doc-head">
          <input
            v-if="editing" v-model="editTitle" class="doc-title-input" placeholder="页面标题"
          />
          <h1 v-else class="doc-title">{{ current?.title || '未命名页面' }}</h1>
          <div class="doc-head-ops" v-if="canWrite">
            <template v-if="editing">
              <button class="doc-btn" :disabled="saving" @click="save">{{ saving ? '保存中…' : '保存' }}</button>
              <button class="doc-btn ghost" :disabled="saving" @click="cancelEdit">取消</button>
            </template>
            <button v-else class="doc-btn ghost" @click="startEdit">编辑</button>
          </div>
        </header>
        <div v-if="err" class="doc-err">{{ err }}</div>
        <!-- 编辑态：左写 Markdown 右实时预览 -->
        <div v-if="editing" class="doc-editor">
          <textarea v-model="editBody" class="doc-textarea" placeholder="用 Markdown 写教程…&#10;# 标题  - 列表  **加粗**  `代码`  ![图](http url)"></textarea>
          <!-- eslint-disable-next-line vue/no-v-html -->
          <div class="doc-preview md" v-html="renderMarkdown(editBody)"></div>
        </div>
        <!-- 阅读态 -->
        <!-- eslint-disable-next-line vue/no-v-html -->
        <article v-else class="doc-body md" v-html="renderMarkdown(current?.content_md || '')"></article>
      </template>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import {
  docTree, docGetPage, docCreatePage, docUpdatePage, docDeletePage,
  type DocPage,
} from '@/matrix/client'
import { renderMarkdown } from '@/utils/md'

const props = defineProps<{ roomId: string }>()

const pages = ref<DocPage[]>([])
const canWrite = ref(false)
const currentId = ref<number | null>(null)
const current = ref<DocPage | null>(null)
const loading = ref(false)
const err = ref('')

const editing = ref(false)
const saving = ref(false)
const editTitle = ref('')
const editBody = ref('')

// 扁平化成「带层级深度」的有序列表（按 parent + sort 组织），避免递归组件。
interface FlatNode extends DocPage { depth: number }
const flatTree = ref<FlatNode[]>([])
function rebuildTree() {
  const byParent = new Map<number | null, DocPage[]>()
  for (const p of pages.value) {
    const k = p.parent_id ?? null
    if (!byParent.has(k)) byParent.set(k, [])
    byParent.get(k)!.push(p)
  }
  for (const arr of byParent.values()) arr.sort((a, b) => a.sort - b.sort || a.id - b.id)
  const out: FlatNode[] = []
  const walk = (parent: number | null, depth: number) => {
    for (const p of byParent.get(parent) || []) {
      out.push({ ...p, depth })
      walk(p.id, depth + 1)
    }
  }
  walk(null, 0)
  flatTree.value = out
}

async function loadTree(selectFirst = true) {
  loading.value = true
  try {
    const res = await docTree(props.roomId)
    pages.value = res.pages
    canWrite.value = res.canWrite
    rebuildTree()
    // 当前选中页若已被删，或首次进入，挑第一页
    if (currentId.value && !pages.value.some((p) => p.id === currentId.value)) {
      currentId.value = null; current.value = null
    }
    if (selectFirst && !currentId.value && flatTree.value.length) {
      await select(flatTree.value[0].id)
    }
  } finally {
    loading.value = false
  }
}

async function select(id: number) {
  if (editing.value) return  // 编辑中不切页，避免丢未保存内容
  currentId.value = id
  current.value = await docGetPage(id)
}

async function createPage(parentId: number | null) {
  err.value = ''
  try {
    const p = await docCreatePage(props.roomId, { title: '新页面', parent_id: parentId })
    await loadTree(false)
    await select(p.id)
    startEdit()  // 新建后直接进编辑
  } catch (e: any) {
    err.value = e?.message || '新建失败'
  }
}

async function removePage(n: FlatNode) {
  if (!confirm(`删除「${n.title || '未命名页面'}」及其所有子页？此操作不可撤销。`)) return
  const ok = await docDeletePage(n.id)
  if (!ok) { err.value = '删除失败'; return }
  if (currentId.value === n.id) { currentId.value = null; current.value = null }
  editing.value = false
  await loadTree()
}

function startEdit() {
  if (!current.value) return
  editTitle.value = current.value.title
  editBody.value = current.value.content_md || ''
  editing.value = true
}
function cancelEdit() { editing.value = false; err.value = '' }

async function save() {
  if (!currentId.value) return
  saving.value = true; err.value = ''
  try {
    const updated = await docUpdatePage(currentId.value, {
      title: editTitle.value.trim() || '未命名页面',
      content_md: editBody.value,
    })
    current.value = updated
    editing.value = false
    await loadTree(false)  // 标题可能变，刷新树
  } catch (e: any) {
    err.value = e?.message || '保存失败'
  } finally {
    saving.value = false
  }
}

// 切换文档频道时重载（roomId 变）
watch(() => props.roomId, () => {
  currentId.value = null; current.value = null; editing.value = false; err.value = ''
  if (props.roomId) loadTree()
}, { immediate: true })
</script>

<style scoped>
.doc { display: flex; height: 100%; min-height: 0; background: #fff; }
.doc-side {
  width: 240px; flex-shrink: 0; border-right: 1px solid #eae6df;
  display: flex; flex-direction: column; background: #faf9f6; overflow-y: auto;
}
.doc-side-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 12px 8px; font-size: 13px; color: #6b665e;
}
.doc-side-title { font-weight: 600; }
.doc-empty-tree { padding: 12px; font-size: 12px; color: #ada699; }
.doc-tree { list-style: none; margin: 0; padding: 0 4px 12px; }
.doc-node {
  display: flex; align-items: center; justify-content: space-between;
  border-radius: 6px; padding-right: 4px; cursor: default;
}
.doc-node:hover { background: #f1efe9; }
.doc-node.active { background: #faece7; }
.doc-node-title {
  flex: 1; padding: 6px 4px; font-size: 13px; color: #2c2a26; cursor: pointer;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.doc-node-ops { display: none; gap: 2px; }
.doc-node:hover .doc-node-ops { display: inline-flex; }
.doc-mini {
  border: none; background: transparent; color: #8a8378; cursor: pointer;
  font-size: 14px; line-height: 1; padding: 4px 6px; border-radius: 4px;
}
.doc-mini:hover { background: #e8e3da; color: #2c2a26; }
.doc-mini.danger:hover { background: #f6d9cf; color: #993c1d; }

.doc-main { flex: 1; min-width: 0; display: flex; flex-direction: column; overflow: hidden; }
.doc-hint { padding: 40px; color: #ada699; font-size: 14px; }
.doc-head {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 20px 32px 8px;
}
.doc-title { font-size: 24px; font-weight: 700; color: #2c2a26; margin: 0; }
.doc-title-input {
  flex: 1; font-size: 22px; font-weight: 700; color: #2c2a26;
  border: none; border-bottom: 1px solid #eae6df; padding: 4px 0; outline: none;
}
.doc-head-ops { display: flex; gap: 8px; flex-shrink: 0; }
.doc-btn {
  border: 1px solid #c96442; background: #c96442; color: #fff; border-radius: 8px;
  padding: 6px 14px; font-size: 13px; cursor: pointer;
}
.doc-btn.ghost { background: #fff; color: #6b665e; border-color: #d8d2c8; }
.doc-btn:disabled { opacity: .6; cursor: default; }
.doc-err { margin: 0 32px; color: #993c1d; font-size: 13px; }

.doc-editor { flex: 1; display: flex; min-height: 0; gap: 1px; background: #eae6df; margin-top: 8px; }
.doc-textarea {
  flex: 1; border: none; outline: none; padding: 20px 32px; font-size: 14px;
  line-height: 1.7; resize: none; font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  background: #fff;
}
.doc-preview { flex: 1; overflow-y: auto; padding: 20px 32px; background: #fff; }
.doc-body { flex: 1; overflow-y: auto; padding: 8px 32px 40px; }

/* Markdown 渲染样式 */
.md { font-size: 15px; line-height: 1.8; color: #2c2a26; }
.md :deep(h1) { font-size: 22px; margin: 20px 0 10px; }
.md :deep(h2) { font-size: 18px; margin: 18px 0 8px; }
.md :deep(h3) { font-size: 16px; margin: 16px 0 6px; }
.md :deep(p) { margin: 8px 0; }
.md :deep(ul), .md :deep(ol) { margin: 8px 0; padding-left: 24px; }
.md :deep(li) { margin: 4px 0; }
.md :deep(blockquote) {
  margin: 10px 0; padding: 6px 14px; border-left: 3px solid #d8d2c8;
  color: #6b665e; background: #faf9f6;
}
.md :deep(.md-pre) {
  background: #2c2a26; color: #f1efe9; border-radius: 8px; padding: 12px 14px;
  overflow-x: auto; font-size: 13px; line-height: 1.5;
}
.md :deep(.md-code) {
  background: #f1efe9; border-radius: 4px; padding: 1px 5px; font-size: 13px;
}
.md :deep(.md-img) { max-width: 100%; border-radius: 8px; margin: 8px 0; }
.md :deep(a) { color: #c96442; }
.md :deep(.mention) { color: #4a7a8c; font-weight: 600; }
</style>
