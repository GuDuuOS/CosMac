<template>
  <!-- 社媒数据源配置弹窗：配各平台账号 + 取数模式（官方 API / AI 爬取）。
       存 cosmac.social_sources（按工作区、多端同步）。凭据只填「名字」，真值在服务端 env。 -->
  <div v-if="modalOpen" class="ssm-mask" @click.self="closeModal">
    <div class="ssm">
      <div class="ssm-head">
        <div class="ssm-title">🔌 接入社媒数据源</div>
        <button class="ssm-x" title="关闭" @click="closeModal">×</button>
      </div>

      <div class="ssm-body">
        <p class="ssm-intro">
          配置各平台账号后，中枢 AI 采集器会按设定周期取「粉丝 / 播放 / 互动」回填到数据看板。
          <b>官方 API</b> 准确稳定（需平台开发者资质）；<b>AI 爬取</b> 走工作流抓公开主页（无需授权，稳定性较弱）。
        </p>

        <!-- 已配置列表 -->
        <div v-if="sources.length" class="ssm-list">
          <div v-for="(s, i) in sources" :key="i" class="ssm-row">
            <div class="ssm-row-main">
              <span class="ssm-plat">{{ platformIcon(s.platform) }} {{ platformLabel(s.platform) }}</span>
              <span class="ssm-acc">{{ s.account || '—' }}</span>
              <span class="ssm-mode" :class="s.mode">{{ s.mode === 'api' ? '官方 API' : 'AI 爬取' }}</span>
              <span class="ssm-status" :class="s.lastStatus || 'never'">{{ statusText(s) }}</span>
            </div>
            <div class="ssm-row-sub">
              <label class="ssm-sw">
                <input type="checkbox" v-model="s.enabled" /> 启用
              </label>
              <span v-if="s.mode === 'api' && s.credName" class="ssm-meta">凭据名 {{ s.credName }}</span>
              <span v-if="s.mode === 'crawl' && s.workflow" class="ssm-meta">工作流 {{ s.workflow }}</span>
              <span class="ssm-meta">每 {{ s.intervalH ?? 6 }}h</span>
              <span class="ssm-spacer" />
              <button class="ssm-mini" title="后端采集器上线后生效（P2）" @click="syncNow(i)">立即同步</button>
              <button class="ssm-mini del" title="移除" @click="removeSource(i)">移除</button>
            </div>
          </div>
        </div>
        <p v-else class="ssm-empty">还没有数据源 —— 在下面添加一个。</p>

        <!-- 添加表单 -->
        <div class="ssm-add">
          <div class="ssm-add-h">＋ 添加数据源</div>
          <div class="ssm-grid">
            <label class="ssm-field">
              <span>平台</span>
              <select v-model="nPlatform">
                <option v-for="p in SOCIAL_PLATFORMS" :key="p.key" :value="p.key">{{ p.icon }} {{ p.label }}</option>
              </select>
            </label>
            <label class="ssm-field">
              <span>账号 / 主页 URL / UID</span>
              <input v-model="nAccount" placeholder="如 @anqistudio 或主页链接" @keyup.enter="doAdd" />
            </label>
            <label class="ssm-field">
              <span>取数模式</span>
              <select v-model="nMode">
                <option value="api">官方 API</option>
                <option value="crawl">AI 爬取（工作流）</option>
              </select>
            </label>
            <label v-if="nMode === 'api'" class="ssm-field">
              <span>凭据名（服务端 env）</span>
              <input v-model="nCred" placeholder="如 YOUTUBE_API（只填名，不填 key）" @keyup.enter="doAdd" />
            </label>
            <label v-else class="ssm-field">
              <span>抓取工作流名</span>
              <input v-model="nWorkflow" placeholder="cosmac.workflows 里的连接器名" @keyup.enter="doAdd" />
            </label>
            <label class="ssm-field">
              <span>同步间隔（小时）</span>
              <input v-model.number="nInterval" type="number" min="1" max="168" />
            </label>
          </div>
          <button class="ssm-addbtn" :disabled="!nAccount.trim()" @click="doAdd">添加数据源</button>
        </div>

        <div class="ssm-foot">
          <span class="ssm-save" :class="saveState">{{ saveHint }}</span>
          <span class="ssm-note">
            凭据 key/token 永不存这里——只填凭据名，真值放服务端 env <code>COSMAC_SOCIAL_*</code>。真实采集为后端 P2 项。
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import {
  useSocialSources,
  SOCIAL_PLATFORMS,
  platformLabel,
  platformIcon,
  type SocialMode,
  type SocialSource,
} from '@/composables/useSocialSources'

const {
  sources, saveState, modalOpen, closeModal, addSource, removeSource,
} = useSocialSources()

// 添加表单字段
const nPlatform = ref(SOCIAL_PLATFORMS[0].key)
const nAccount = ref('')
const nMode = ref<SocialMode>('api')
const nCred = ref('')
const nWorkflow = ref('')
const nInterval = ref(6)

function doAdd() {
  if (!nAccount.value.trim()) return
  addSource({
    platform: nPlatform.value,
    account: nAccount.value,
    mode: nMode.value,
    credName: nMode.value === 'api' ? nCred.value : undefined,
    workflow: nMode.value === 'crawl' ? nWorkflow.value : undefined,
    intervalH: nInterval.value,
  })
  nAccount.value = ''
  nCred.value = ''
  nWorkflow.value = ''
}

// P1：采集器未接，点「立即同步」先提示。P2 改成调后端触发一次采集。
function syncNow(_i: number) {
  // 仅占位反馈，避免误以为已取数
  alert('社媒采集器为后端 P2 项，尚未接入。配置已保存，待采集器上线后将按此自动取数。')
}

function statusText(s: SocialSource): string {
  if (!s.enabled) return '已停用'
  switch (s.lastStatus) {
    case 'ok': return s.lastSync ? '已同步' : '待同步'
    case 'error': return '同步失败'
    default: return '待同步'
  }
}

const saveHint = computed(() => ({
  idle: '编辑后自动保存到本工作区 · 多端同步',
  saving: '保存中…',
  saved: '✓ 已保存 · 多端同步',
  error: '保存失败：你可能没有本工作区改配置的权限',
}[saveState.value]))
</script>

<style scoped>
.ssm-mask { position: fixed; inset: 0; background: rgba(0,0,0,.38); display: flex; align-items: center; justify-content: center; z-index: 2000; padding: 24px; }
.ssm { width: 100%; max-width: 720px; max-height: 86vh; display: flex; flex-direction: column; background: var(--bg-panel); border: 1px solid var(--border); border-radius: 14px; box-shadow: 0 18px 50px rgba(0,0,0,.22); overflow: hidden; }
.ssm-head { display: flex; align-items: center; padding: 16px 18px; border-bottom: 1px solid var(--border); }
.ssm-title { font-weight: var(--fw-bold); font-size: var(--fs-150, 16px); color: var(--text); }
.ssm-x { margin-left: auto; border: none; background: transparent; color: var(--text-3); font-size: 22px; line-height: 1; cursor: pointer; border-radius: 6px; width: 28px; height: 28px; }
.ssm-x:hover { background: var(--bg-hover); color: var(--text); }
.ssm-body { padding: 16px 18px; overflow-y: auto; }
.ssm-intro { font-size: 12px; color: var(--text-2); line-height: 1.7; margin: 0 0 14px; }

.ssm-list { display: flex; flex-direction: column; gap: 8px; margin-bottom: 16px; }
.ssm-row { border: 1px solid var(--border); border-radius: 10px; padding: 10px 12px; background: var(--bg); }
.ssm-row-main { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.ssm-plat { font-weight: var(--fw-bold); color: var(--text); font-size: 13px; }
.ssm-acc { font-size: 12px; color: var(--text-2); font-family: var(--font-mono, monospace); }
.ssm-mode { font-size: 11px; padding: 1px 8px; border-radius: 999px; border: 1px solid var(--border); color: var(--text-dim, #888); }
.ssm-mode.api { color: var(--accent); border-color: color-mix(in srgb, var(--accent) 40%, transparent); }
.ssm-status { margin-left: auto; font-size: 11px; color: var(--text-3); }
.ssm-status.ok { color: var(--ok, #6b8e4e); }
.ssm-status.error { color: #b94a4a; }
.ssm-row-sub { display: flex; align-items: center; gap: 12px; margin-top: 8px; padding-top: 8px; border-top: 1px dashed var(--border); flex-wrap: wrap; }
.ssm-sw { display: flex; align-items: center; gap: 5px; font-size: 12px; color: var(--text-2); cursor: pointer; }
.ssm-meta { font-size: 11px; color: var(--text-3); }
.ssm-spacer { flex: 1; }
.ssm-mini { border: 1px solid var(--border); background: var(--bg-panel); color: var(--text-2); font-size: 11px; padding: 3px 10px; border-radius: 6px; cursor: pointer; }
.ssm-mini:hover { border-color: var(--accent); color: var(--accent); }
.ssm-mini.del:hover { border-color: #b94a4a; color: #b94a4a; }
.ssm-empty { font-size: 12px; color: var(--text-3); padding: 6px 0 16px; }

.ssm-add { border: 1px solid var(--border); border-radius: 10px; padding: 12px 14px; background: var(--bg); }
.ssm-add-h { font-size: 13px; font-weight: var(--fw-bold); color: var(--text); margin-bottom: 10px; }
.ssm-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.ssm-field { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.ssm-field > span { font-size: 11px; color: var(--text-3); }
.ssm-field input, .ssm-field select { width: 100%; box-sizing: border-box; padding: 7px 9px; border: 1px solid var(--border); border-radius: 7px; background: var(--bg-input, var(--bg-panel)); color: var(--text); font-size: 13px; }
.ssm-field input:focus, .ssm-field select:focus { outline: none; border-color: var(--accent); }
.ssm-addbtn { width: 100%; margin-top: 12px; padding: 9px; border: none; border-radius: 8px; background: var(--accent); color: #fff; font-size: 13px; font-weight: var(--fw-bold); cursor: pointer; }
.ssm-addbtn:disabled { opacity: .5; cursor: not-allowed; }

.ssm-foot { margin-top: 14px; display: flex; flex-direction: column; gap: 4px; }
.ssm-save { font-size: 11px; color: var(--text-3); }
.ssm-save.saved { color: var(--ok, #6b8e4e); }
.ssm-save.error { color: #b94a4a; }
.ssm-note { font-size: 11px; color: var(--text-3); line-height: 1.5; }
.ssm-note code { font-family: var(--font-mono, monospace); background: var(--bg-hover); padding: 0 4px; border-radius: 4px; }
</style>
