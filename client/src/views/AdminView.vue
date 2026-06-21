<template>
  <div class="admin-view channel-view">
    <!-- 关闭管理后台，回到工作台 -->
    <button class="adm-close" title="关闭" @click="emit('close')">✕</button>
    <!-- 左侧管理菜单（用户管理已就绪，其余占位，后续逐块填） -->
    <aside class="adm-nav">
      <div class="adm-brand">
        <span class="adm-logo">⚙</span>
        <div>
          <div class="adm-title">管理后台</div>
          <div class="adm-sub">CosMac Star 运营控制台</div>
        </div>
      </div>
      <nav class="adm-menu">
        <button class="adm-mi" :class="{ active: tab === 'users' }" @click="tab = 'users'">
          <span class="adm-mi-ic">👤</span> 用户管理
        </button>
        <button class="adm-mi" :class="{ active: tab === 'rooms' }" @click="switchToRooms">
          <span class="adm-mi-ic">＃</span> 频道管理
        </button>
        <button class="adm-mi" :class="{ active: tab === 'ai' }" @click="switchToAi">
          <span class="adm-mi-ic">🤖</span> AI 配置
        </button>
        <button class="adm-mi" :class="{ active: tab === 'skills' }" @click="switchToSkills">
          <span class="adm-mi-ic">🛠</span> 技能库
        </button>
        <button class="adm-mi" :class="{ active: tab === 'agents' }" @click="switchToAgents">
          <span class="adm-mi-ic">🧑‍🚀</span> 智能体
        </button>
        <button class="adm-mi" :class="{ active: tab === 'rules' }" @click="switchToRules">
          <span class="adm-mi-ic">⚖️</span> 规则
        </button>
        <button class="adm-mi" :class="{ active: tab === 'workflows' }" @click="switchToWorkflows">
          <span class="adm-mi-ic">🔗</span> 工作流
        </button>
        <button class="adm-mi" :class="{ active: tab === 'gating' }" @click="switchToGating">
          <span class="adm-mi-ic">🔐</span> 会员权限
        </button>
        <button class="adm-mi" :class="{ active: tab === 'overview' }" @click="switchToOverview">
          <span class="adm-mi-ic">📊</span> 数据概览
        </button>
      </nav>
    </aside>

    <!-- 右侧内容区 -->
    <section class="adm-main">
      <!-- 1) 权限校验中 -->
      <div v-if="state === 'checking'" class="adm-center">
        <div class="adm-spin" /> 正在校验管理员权限…
      </div>

      <!-- 2) 无权限 -->
      <div v-else-if="state === 'denied'" class="adm-center adm-denied">
        <div class="adm-denied-ic">🔒</div>
        <div class="adm-denied-t">无法进入管理后台</div>
        <div class="adm-denied-d">
          可能原因：① 当前账号不是服务器管理员（请用 <code>@admin</code> 登录）；
          ② 服务器未对管理接口 <code>/_synapse/admin</code> 开放跨域（CORS），
          导致浏览器无法调用。若你确认是管理员，多半是第 ② 种，需在 hs 的 nginx 放开 CORS。
        </div>
        <button class="adm-btn" @click="check">重新校验</button>
      </div>

      <!-- 3) 已是管理员：按 tab 显示用户管理 / 频道管理 -->
      <template v-else-if="tab === 'users'">
        <header class="adm-head">
          <div>
            <h1 class="adm-h1">用户管理</h1>
            <p class="adm-hint">
              共 {{ users.length }} 个账号 ·
              管理员 {{ users.filter(u => u.admin).length }} ·
              已停用 {{ users.filter(u => u.deactivated).length }}
            </p>
          </div>
          <div class="adm-actions">
            <button class="adm-btn ghost" :disabled="loading" @click="loadUsers">
              {{ loading ? '刷新中…' : '刷新' }}
            </button>
            <button class="adm-btn" @click="showCreate = true">＋ 新建用户</button>
          </div>
        </header>

        <div v-if="loading" class="adm-center"><div class="adm-spin" /> 加载用户列表…</div>

        <table v-else class="adm-table">
          <thead>
            <tr>
              <th>用户</th>
              <th>角色</th>
              <th>会员等级</th>
              <th>状态</th>
              <th class="adm-ops-h">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="u in users" :key="u.id" :class="{ off: u.deactivated }">
              <td>
                <div class="adm-user">
                  <span class="adm-ava">{{ avatarOf(u) }}</span>
                  <div class="adm-u-id">
                    <div class="adm-u-name">
                      {{ u.name }}
                      <span v-if="u.isBot" class="adm-tag bot">中枢AI</span>
                    </div>
                    <div class="adm-u-handle">{{ u.id }}</div>
                  </div>
                </div>
              </td>
              <td>
                <span class="adm-tag" :class="u.admin ? 'admin' : 'member'">
                  {{ u.admin ? '管理员' : '成员' }}
                </span>
              </td>
              <td>
                <!-- 会员等级独立于"管理员"：直接下拉调整，即时写控制室 cosmac.members。
                     中枢AI 不是会员、不显示下拉。 -->
                <select
                  v-if="!u.isBot"
                  class="adm-tier"
                  :class="memberTier(u.id)"
                  :value="memberTier(u.id)"
                  :disabled="tierBusy === u.id"
                  @change="onTierChange(u, ($event.target as HTMLSelectElement).value)"
                >
                  <option v-for="t in MEMBER_TIERS" :key="t.slug" :value="t.slug">
                    {{ t.label }}
                  </option>
                </select>
                <span v-else class="adm-muted">—</span>
              </td>
              <td>
                <span class="adm-tag" :class="u.deactivated ? 'off' : 'ok'">
                  {{ u.deactivated ? '已停用' : '正常' }}
                </span>
              </td>
              <td class="adm-ops">
                <button class="adm-op" :disabled="u.isBot || busy === u.id" @click="toggleAdmin(u)">
                  {{ u.admin ? '撤销管理员' : '设为管理员' }}
                </button>
                <button class="adm-op" :disabled="busy === u.id" @click="doResetPassword(u)">
                  重置密码
                </button>
                <button
                  v-if="!u.deactivated"
                  class="adm-op danger"
                  :disabled="u.isBot || busy === u.id"
                  @click="doDeactivate(u)"
                >停用</button>
                <button v-else class="adm-op" :disabled="busy === u.id" @click="doReactivate(u)">
                  恢复
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </template>

      <!-- 频道管理面板 -->
      <template v-else-if="tab === 'rooms'">
        <header class="adm-head">
          <div>
            <h1 class="adm-h1">频道管理</h1>
            <p class="adm-hint">
              全服共 {{ rooms.length }} 个频道 ·
              公开 {{ rooms.filter(r => r.isPublic).length }} ·
              加密 {{ rooms.filter(r => r.encrypted).length }}
            </p>
          </div>
          <div class="adm-actions">
            <button class="adm-btn ghost" :disabled="roomsLoading" @click="loadRooms">
              {{ roomsLoading ? '刷新中…' : '刷新' }}
            </button>
          </div>
        </header>

        <div v-if="roomsLoading" class="adm-center"><div class="adm-spin" /> 加载频道列表…</div>

        <table v-else class="adm-table">
          <thead>
            <tr>
              <th>频道</th>
              <th>成员</th>
              <th>类型</th>
              <th class="adm-ops-h">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in rooms" :key="r.id">
              <td>
                <div class="adm-user">
                  <span class="adm-ava">{{ (r.name || '#').charAt(0).toUpperCase() }}</span>
                  <div class="adm-u-id">
                    <div class="adm-u-name">{{ r.name }}</div>
                    <div class="adm-u-handle">{{ r.alias || r.id }}</div>
                  </div>
                </div>
              </td>
              <td>{{ r.members }}<span class="adm-dim"> / 本服 {{ r.localMembers }}</span></td>
              <td>
                <span class="adm-tag" :class="r.isPublic ? 'admin' : 'member'">
                  {{ r.isPublic ? '公开' : '私有' }}
                </span>
                <span v-if="r.encrypted" class="adm-tag bot" title="端到端加密">🔒 加密</span>
              </td>
              <td class="adm-ops">
                <button class="adm-op" :disabled="roomBusy === r.id" @click="viewMembers(r)">
                  查看成员
                </button>
                <button class="adm-op danger" :disabled="roomBusy === r.id" @click="doDeleteRoom(r)">
                  删除
                </button>
              </td>
            </tr>
            <tr v-if="!rooms.length"><td colspan="4" class="adm-empty">暂无频道</td></tr>
          </tbody>
        </table>
      </template>

      <!-- AI 配置面板 -->
      <template v-else-if="tab === 'ai'">
        <header class="adm-head">
          <div>
            <h1 class="adm-h1">AI 配置</h1>
            <p class="adm-hint">
              改主 AI 的人设/模型/工具开关 · 保存后写入控制室，bot 约 20 秒内热生效（无需重启）
            </p>
          </div>
          <div class="adm-actions">
            <button class="adm-btn ghost" :disabled="aiLoading || aiSaving" @click="loadAi">
              {{ aiLoading ? '加载中…' : '重新加载' }}
            </button>
            <button class="adm-btn" :disabled="aiLoading || aiSaving" @click="saveAi">
              {{ aiSaving ? '保存中…' : '保存' }}
            </button>
          </div>
        </header>

        <div v-if="aiLoading" class="adm-center"><div class="adm-spin" /> 加载配置…</div>

        <div v-else class="adm-form">
          <!-- 模型后端：选 provider + 模型 id。API Key 不在网页配，只在服务端 -->
          <label class="adm-field">
            <span>模型后端</span>
            <select v-model="aiForm.provider">
              <option v-for="p in AI_PROVIDERS" :key="p.value" :value="p.value">{{ p.label }}</option>
            </select>
            <em class="adm-note">选「默认」= 用服务器配置的后端；选某家则切到它（需服务器已配好它的 API Key）。</em>
          </label>

          <template v-if="aiForm.provider">
            <label class="adm-field">
              <span>模型 id</span>
              <input v-model.trim="aiForm.model" :placeholder="providerMeta.modelPlaceholder" />
              <em class="adm-note">⚠️ 填错会让 AI 回话报错；DeepSeek/Gemini 填方舟/Google 的模型 id 或接入点。</em>
            </label>
            <em class="adm-note">🔒 出于安全，<b>API Key 不在网页配置</b>——密钥只在服务器环境变量/Secret&nbsp;Manager 里设（平台事件无法加密，存进去会明文泄露）。切到服务器没配 key 的后端，AI 将无法回话。</em>
          </template>

          <label class="adm-field">
            <span>主 AI 人设（system prompt）</span>
            <textarea v-model="aiForm.system_prompt" rows="5"
              placeholder="留空 = 用服务器默认人设" />
          </label>

          <div class="adm-field">
            <span>工具开关（关掉的工具主 AI 将无法调用）</span>
            <div class="adm-tools">
              <label v-for="t in AI_TOOL_CATALOG" :key="t.name" class="adm-tool">
                <input type="checkbox" :checked="isToolOn(t.name)" @change="toggleTool(t.name, ($event.target as HTMLInputElement).checked)" />
                <span class="adm-tool-l">{{ t.label }}</span>
                <code>{{ t.name }}</code>
              </label>
            </div>
            <em class="adm-note">全部勾选 = 不限制（默认）。</em>
          </div>
        </div>
      </template>

      <!-- 技能库面板：编辑全局技能（写控制室 state event，主 AI 注入到所有群）-->
      <template v-else-if="tab === 'skills'">
        <header class="adm-head">
          <div>
            <h1 class="adm-h1">技能库</h1>
            <p class="adm-hint">
              全局技能 · 主 AI 在所有群回话时按需运用 · 保存后约 20 秒内热生效（无需重启）
            </p>
          </div>
          <div class="adm-actions">
            <button class="adm-btn ghost" :disabled="skLoading || skSaving" @click="loadSkills">
              {{ skLoading ? '加载中…' : '重新加载' }}
            </button>
            <button class="adm-btn" :disabled="skLoading || skSaving" @click="startAddSkill">＋ 新建技能</button>
          </div>
        </header>

        <div v-if="skLoading" class="adm-center"><div class="adm-spin" /> 加载技能…</div>

        <div v-else class="adm-form">
          <!-- 编辑/新建表单 -->
          <div v-if="skEditing" class="adm-skill-edit">
            <label class="adm-field">
              <span>标识 slug（英文/数字/-，全局唯一）</span>
              <input v-model.trim="skForm.slug" :disabled="skForm._isEdit" placeholder="weekly-report" />
            </label>
            <label class="adm-field">
              <span>名称</span>
              <input v-model.trim="skForm.name" placeholder="周报" />
            </label>
            <label class="adm-field">
              <span>一句话说明</span>
              <input v-model.trim="skForm.description" placeholder="生成本周数据周报" />
            </label>
            <label class="adm-field">
              <span>技能正文（喂给主 AI 的提示/步骤）</span>
              <textarea v-model="skForm.instructions" rows="5" placeholder="按…步骤生成…" />
            </label>
            <label class="adm-tool">
              <input type="checkbox" v-model="skForm.enabled" />
              <span class="adm-tool-l">启用</span>
            </label>
            <div class="adm-actions">
              <button class="adm-btn ghost" :disabled="skSaving" @click="skEditing = false">取消</button>
              <button class="adm-btn" :disabled="skSaving || !skForm.slug" @click="saveSkill">
                {{ skSaving ? '保存中…' : '保存' }}
              </button>
            </div>
          </div>

          <!-- 技能列表 -->
          <p v-if="!skills.length" class="adm-hint">还没有全局技能。点右上「新建技能」加一个。</p>
          <table v-else class="adm-table">
            <thead>
              <tr><th>标识</th><th>名称</th><th>说明</th><th>状态</th><th>操作</th></tr>
            </thead>
            <tbody>
              <tr v-for="s in skills" :key="s.slug">
                <td><code>{{ s.slug }}</code></td>
                <td>{{ s.name || '—' }}</td>
                <td class="adm-skill-desc">{{ s.description || '—' }}</td>
                <td>
                  <span class="adm-badge" :class="{ on: s.enabled }">{{ s.enabled ? '启用' : '停用' }}</span>
                </td>
                <td class="adm-row-actions">
                  <button class="adm-btn ghost sm" :disabled="skSaving" @click="startEditSkill(s)">编辑</button>
                  <button class="adm-btn ghost sm" :disabled="skSaving" @click="toggleSkill(s)">{{ s.enabled ? '停用' : '启用' }}</button>
                  <button class="adm-btn ghost sm danger" :disabled="skSaving" @click="removeSkill(s)">删除</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>

      <!-- 智能体面板：编辑全局 Agent（人设+模型+绑定技能，写控制室 state event）-->
      <template v-else-if="tab === 'agents'">
        <header class="adm-head">
          <div>
            <h1 class="adm-h1">智能体</h1>
            <p class="adm-hint">
              定义可复用的 AI 角色（人设 + 模型 + 绑定技能）· 后续可把某群绑定到一个智能体
            </p>
          </div>
          <div class="adm-actions">
            <button class="adm-btn ghost" :disabled="agLoading || agSaving" @click="loadAgents">
              {{ agLoading ? '加载中…' : '重新加载' }}
            </button>
            <button class="adm-btn" :disabled="agLoading || agSaving" @click="startAddAgent">＋ 新建智能体</button>
          </div>
        </header>

        <div v-if="agLoading" class="adm-center"><div class="adm-spin" /> 加载智能体…</div>

        <div v-else class="adm-form">
          <!-- 编辑/新建表单 -->
          <div v-if="agEditing" class="adm-skill-edit">
            <label class="adm-field">
              <span>标识 slug（英文/数字/-，全局唯一）</span>
              <input v-model.trim="agForm.slug" :disabled="agForm._isEdit" placeholder="planner" />
            </label>
            <label class="adm-field">
              <span>名称</span>
              <input v-model.trim="agForm.name" placeholder="策划助手" />
            </label>
            <label class="adm-field">
              <span>一句话说明</span>
              <input v-model.trim="agForm.description" placeholder="负责选题与排期" />
            </label>
            <label class="adm-field">
              <span>人设（system prompt）</span>
              <textarea v-model="agForm.system_prompt" rows="4" placeholder="你是…，说话风格…" />
            </label>
            <label class="adm-field">
              <span>模型覆盖（留空 = 跟随全局 AI 配置）</span>
              <input v-model.trim="agForm.model" placeholder="如 claude-opus-4-8（可留空）" />
            </label>
            <div class="adm-field">
              <span>绑定技能（勾选全局技能库里的技能）</span>
              <div v-if="!skills.length" class="adm-note">技能库为空，可先去「技能库」建技能。</div>
              <div v-else class="adm-tools">
                <label v-for="s in skills" :key="s.slug" class="adm-tool">
                  <input type="checkbox" :checked="agForm.skill_slugs.includes(s.slug)"
                    @change="toggleAgentSkill(s.slug, ($event.target as HTMLInputElement).checked)" />
                  <span class="adm-tool-l">{{ s.name || s.slug }}</span>
                  <code>{{ s.slug }}</code>
                </label>
              </div>
            </div>
            <label class="adm-tool">
              <input type="checkbox" v-model="agForm.enabled" />
              <span class="adm-tool-l">启用</span>
            </label>
            <div class="adm-actions">
              <button class="adm-btn ghost" :disabled="agSaving" @click="agEditing = false">取消</button>
              <button class="adm-btn" :disabled="agSaving || !agForm.slug" @click="saveAgent">
                {{ agSaving ? '保存中…' : '保存' }}
              </button>
            </div>
          </div>

          <!-- 智能体列表 -->
          <p v-if="!agents.length" class="adm-hint">还没有智能体。点右上「新建智能体」加一个。</p>
          <table v-else class="adm-table">
            <thead>
              <tr><th>标识</th><th>名称</th><th>模型</th><th>技能</th><th>状态</th><th>操作</th></tr>
            </thead>
            <tbody>
              <tr v-for="a in agents" :key="a.slug">
                <td><code>{{ a.slug }}</code></td>
                <td>{{ a.name || '—' }}</td>
                <td>{{ a.model || '默认' }}</td>
                <td class="adm-skill-desc">{{ a.skill_slugs.length ? a.skill_slugs.join('、') : '—' }}</td>
                <td><span class="adm-badge" :class="{ on: a.enabled }">{{ a.enabled ? '启用' : '停用' }}</span></td>
                <td class="adm-row-actions">
                  <button class="adm-btn ghost sm" :disabled="agSaving" @click="startEditAgent(a)">编辑</button>
                  <button class="adm-btn ghost sm" :disabled="agSaving" @click="toggleAgent(a)">{{ a.enabled ? '停用' : '启用' }}</button>
                  <button class="adm-btn ghost sm danger" :disabled="agSaving" @click="removeAgent(a)">删除</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>

      <!-- 规则面板:平台级硬约束(写控制室 state event,主 AI 所有群都注入、优先级最高) -->
      <template v-else-if="tab === 'rules'">
        <header class="adm-head">
          <div>
            <h1 class="adm-h1">规则</h1>
            <p class="adm-hint">
              平台级硬约束 · 主 AI 在所有群都须遵守、优先级高于人设/技能 · 保存后约 20 秒热生效
            </p>
          </div>
          <div class="adm-actions">
            <button class="adm-btn ghost" :disabled="ruLoading || ruSaving" @click="loadRules">
              {{ ruLoading ? '加载中…' : '重新加载' }}
            </button>
            <button class="adm-btn" :disabled="ruLoading || ruSaving" @click="saveRules">
              {{ ruSaving ? '保存中…' : '保存' }}
            </button>
          </div>
        </header>

        <div v-if="ruLoading" class="adm-center"><div class="adm-spin" /> 加载规则…</div>

        <div v-else class="adm-form">
          <p class="adm-hint">每条一行规则;停用的不注入。例:「对外报价/发布等动作必须先经负责人确认」「不得编造数据,引用须标注来源」。</p>
          <div v-for="(r, i) in rules" :key="i" class="adm-rule-row">
            <input type="checkbox" v-model="r.enabled" title="启用" />
            <textarea v-model="r.text" rows="2" class="adm-rule-text" placeholder="写一条主 AI 必须遵守的规则…" />
            <button class="adm-btn ghost sm danger" @click="rules.splice(i, 1)">删除</button>
          </div>
          <button class="adm-btn ghost sm" @click="rules.push({ text: '', enabled: true })">＋ 加一条规则</button>
        </div>
      </template>

      <!-- 工作流面板:配置外部连接器(n8n/Make 等),写控制室 state event -->
      <template v-else-if="tab === 'workflows'">
        <header class="adm-head">
          <div>
            <h1 class="adm-h1">工作流</h1>
            <p class="adm-hint">
              对接 n8n / Make 等外部平台 · 群里发「工作流 跑 &lt;slug&gt;」或直接让主 AI 触发 · 保存后约 20 秒热生效
            </p>
          </div>
          <div class="adm-actions">
            <button class="adm-btn ghost" :disabled="wfLoading || wfSaving" @click="loadWorkflows">
              {{ wfLoading ? '加载中…' : '重新加载' }}
            </button>
            <button class="adm-btn" :disabled="wfLoading || wfSaving" @click="startAddWorkflow">＋ 新建连接器</button>
          </div>
        </header>

        <div v-if="wfLoading" class="adm-center"><div class="adm-spin" /> 加载连接器…</div>

        <div v-else class="adm-form">
          <div v-if="wfEditing" class="adm-skill-edit">
            <label class="adm-field">
              <span>标识 slug（英文/数字/-，全局唯一）</span>
              <input v-model.trim="wfForm.slug" :disabled="wfForm._isEdit" placeholder="cover-gen" />
            </label>
            <label class="adm-field">
              <span>名称</span>
              <input v-model.trim="wfForm.name" placeholder="封面生成" />
            </label>
            <label class="adm-field">
              <span>平台</span>
              <select v-model="wfForm.platform" class="cam-select">
                <option value="webhook">Webhook（n8n / Make / 自建）</option>
                <option value="dify">Dify</option>
                <option value="coze">Coze</option>
                <option value="comfyui">ComfyUI（图/视频）</option>
              </select>
            </label>
            <label class="adm-field">
              <span>{{ wfForm.platform === 'webhook' ? 'Webhook URL' : '服务地址（base url）' }}</span>
              <input v-model.trim="wfForm.url" :placeholder="wfUrlPlaceholder" />
            </label>
            <label v-if="wfForm.platform === 'webhook'" class="adm-field">
              <span>请求方法</span>
              <select v-model="wfForm.method" class="cam-select">
                <option value="POST">POST</option>
                <option value="GET">GET</option>
              </select>
            </label>
            <label v-if="wfForm.platform === 'dify'" class="adm-field">
              <span>Dify 应用类型</span>
              <select v-model="wfForm.mode" class="cam-select">
                <option value="workflow">workflow（工作流应用）</option>
                <option value="chat">chat（对话应用）</option>
              </select>
            </label>
            <label v-if="wfForm.platform === 'coze'" class="adm-field">
              <span>Coze workflow_id</span>
              <input v-model.trim="wfForm.ref_id" placeholder="如 7401234567890" />
            </label>
            <label v-if="wfForm.platform === 'dify' || wfForm.platform === 'coze'" class="adm-field">
              <span>输入变量名（可选）</span>
              <input v-model.trim="wfForm.input_key" placeholder="默认 input（要与平台里定义的输入变量名一致）" />
            </label>
            <label v-if="wfForm.platform === 'comfyui'" class="adm-field">
              <span>工作流图（API 格式 JSON）</span>
              <textarea v-model="wfForm.graph" rows="6" class="adm-rule-text"
                placeholder='把 ComfyUI 导出的"API 格式"工作流 JSON 粘进来，要被用户输入替换的地方写成 {{input}}' />
              <em class="adm-note">ComfyUI 菜单「Save (API Format)」导出；把提示词节点的文本改成 <code v-pre>{{input}}</code> 占位。生成的图会自动发回触发的群。</em>
            </label>
            <label class="adm-field">
              <span>凭据名（可选）</span>
              <input v-model.trim="wfForm.cred" placeholder="如 n8n_main（可留空）" />
              <em class="adm-note">🔒 这里只填"名字"。真密钥在服务器环境变量 <code>COSMAC_WF_&lt;大写名字&gt;</code> 里配，不进网页或聊天数据。留空=URL 自带令牌/无需鉴权。</em>
            </label>
            <label class="adm-field">
              <span>输入提示（给用户看的，可选）</span>
              <input v-model.trim="wfForm.input_hint" placeholder="如 描述要生成的封面" />
            </label>
            <label v-if="wfForm.platform === 'webhook'" class="adm-tool">
              <input type="checkbox" v-model="wfForm.async" />
              <span class="adm-tool-l">异步(长任务)</span>
              <em class="adm-note">勾上=提交后不等结果,平台跑完反向回调再把结果发回群(需服务端配 COSMAC_PUBLIC_URL + nginx 放行 /cosmac/)。</em>
            </label>
            <label class="adm-tool">
              <input type="checkbox" v-model="wfForm.enabled" />
              <span class="adm-tool-l">启用</span>
            </label>
            <div class="adm-actions">
              <button class="adm-btn ghost" :disabled="wfSaving" @click="wfEditing = false">取消</button>
              <button class="adm-btn" :disabled="wfSaving || !wfForm.slug || !wfForm.url" @click="saveWorkflow">
                {{ wfSaving ? '保存中…' : '保存' }}
              </button>
            </div>
          </div>

          <p v-if="!workflows.length" class="adm-hint">还没有连接器。点右上「新建连接器」加一个(先在 n8n/Make 建好 webhook,把 URL 填进来)。</p>
          <table v-else class="adm-table">
            <thead>
              <tr><th>标识</th><th>名称</th><th>平台</th><th>URL</th><th>状态</th><th>操作</th></tr>
            </thead>
            <tbody>
              <tr v-for="w in workflows" :key="w.slug">
                <td><code>{{ w.slug }}</code></td>
                <td>{{ w.name || '—' }}</td>
                <td>{{ w.platform }}</td>
                <td class="adm-skill-desc">{{ w.url }}</td>
                <td><span class="adm-badge" :class="{ on: w.enabled }">{{ w.enabled ? '启用' : '停用' }}</span></td>
                <td class="adm-row-actions">
                  <button class="adm-btn ghost sm" :disabled="wfSaving" @click="startEditWorkflow(w)">编辑</button>
                  <button class="adm-btn ghost sm" :disabled="wfSaving" @click="toggleWorkflow(w)">{{ w.enabled ? '停用' : '启用' }}</button>
                  <button class="adm-btn ghost sm danger" :disabled="wfSaving" @click="removeWorkflow(w)">删除</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>

      <!-- 会员权限(功能门控)面板:逐项配「能力→最低会员等级」,写控制室 cosmac.gating,bot 服务端强制 -->
      <template v-else-if="tab === 'gating'">
        <header class="adm-head">
          <div>
            <h1 class="adm-h1">会员权限</h1>
            <p class="adm-hint">
              给每项能力设一个最低会员等级 · 主 AI 在服务端强制(客户端只是配置) · 保存后约 15 秒热生效
            </p>
          </div>
          <div class="adm-actions">
            <button class="adm-btn ghost" :disabled="gateLoading || gateSaving" @click="loadGating">
              {{ gateLoading ? '加载中…' : '重新加载' }}
            </button>
            <button class="adm-btn" :disabled="gateLoading || gateSaving" @click="saveGating">
              {{ gateSaving ? '保存中…' : '保存' }}
            </button>
          </div>
        </header>

        <div v-if="gateLoading" class="adm-center"><div class="adm-spin" /> 加载门控策略…</div>

        <div v-else class="adm-form">
          <p class="adm-hint">
            「免费」= 不限制,人人可用;选更高等级则低于该等级的用户被挡并提示升级。
            「仅平台管理员」用于高危/付费共享凭据的能力(如跑工作流)。
            管理员永远不受会员等级门控限制。以后新增功能会出现在这张表里。
          </p>
          <table class="adm-table">
            <thead>
              <tr><th>能力</th><th>最低会员等级</th></tr>
            </thead>
            <tbody>
              <tr v-for="g in GATE_CATALOG" :key="g.key">
                <td>{{ g.label }}</td>
                <td>
                  <select class="adm-tier" :class="gates[g.key]" v-model="gates[g.key]">
                    <option v-for="lv in GATE_LEVELS" :key="lv.slug" :value="lv.slug">
                      {{ lv.label }}
                    </option>
                  </select>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>

      <!-- 数据概览面板 -->
      <template v-else-if="tab === 'overview'">
        <header class="adm-head">
          <div>
            <h1 class="adm-h1">数据概览</h1>
            <p class="adm-hint">
              平台实时概况 · 数据来自服务器管理接口
              <span v-if="ov.version"> · 服务端 {{ ov.version }}</span>
            </p>
          </div>
          <div class="adm-actions">
            <button class="adm-btn ghost" :disabled="ovLoading" @click="loadOverview">
              {{ ovLoading ? '刷新中…' : '刷新' }}
            </button>
          </div>
        </header>

        <div v-if="ovLoading" class="adm-center"><div class="adm-spin" /> 统计中…</div>

        <template v-else>
          <!-- KPI 卡片 -->
          <div class="adm-kpis">
            <div class="adm-kpi">
              <div class="adm-kpi-v">{{ ov.userTotal }}</div>
              <div class="adm-kpi-l">账号总数</div>
              <div class="adm-kpi-s">管理员 {{ ov.adminCount }} · 停用 {{ ov.deactivated }}</div>
            </div>
            <div class="adm-kpi">
              <div class="adm-kpi-v">{{ ov.roomTotal }}</div>
              <div class="adm-kpi-l">频道总数</div>
              <div class="adm-kpi-s">公开 {{ ov.publicRooms }} · 加密 {{ ov.encryptedRooms }}</div>
            </div>
            <div class="adm-kpi">
              <div class="adm-kpi-v">{{ ov.memberSum }}</div>
              <div class="adm-kpi-l">成员人次合计</div>
              <div class="adm-kpi-s">平均每频道 {{ ov.avgMembers }}</div>
            </div>
            <div class="adm-kpi">
              <div class="adm-kpi-v">{{ ov.activeRooms }}</div>
              <div class="adm-kpi-l">活跃频道</div>
              <div class="adm-kpi-s">成员 ≥ 2 的频道数</div>
            </div>
          </div>

          <!-- 最活跃频道 Top -->
          <h2 class="adm-h2">最活跃频道 Top {{ ov.topRooms.length }}</h2>
          <table class="adm-table">
            <thead>
              <tr><th>频道</th><th>成员</th><th>类型</th></tr>
            </thead>
            <tbody>
              <tr v-for="r in ov.topRooms" :key="r.id">
                <td>
                  <div class="adm-user">
                    <span class="adm-ava">{{ (r.name || '#').charAt(0).toUpperCase() }}</span>
                    <div class="adm-u-id">
                      <div class="adm-u-name">{{ r.name }}</div>
                      <div class="adm-u-handle">{{ r.alias || r.id }}</div>
                    </div>
                  </div>
                </td>
                <td>{{ r.members }}</td>
                <td>
                  <span class="adm-tag" :class="r.isPublic ? 'admin' : 'member'">
                    {{ r.isPublic ? '公开' : '私有' }}
                  </span>
                </td>
              </tr>
              <tr v-if="!ov.topRooms.length"><td colspan="3" class="adm-empty">暂无数据</td></tr>
            </tbody>
          </table>
        </template>
      </template>
    </section>

    <!-- 新建用户弹窗 -->
    <div v-if="showCreate" class="adm-mask" @click.self="showCreate = false">
      <div class="adm-modal">
        <div class="adm-modal-h">新建用户</div>
        <label class="adm-field">
          <span>用户名</span>
          <input v-model.trim="form.username" placeholder="如 alice（自动补 :{{ domain }}）" />
        </label>
        <label class="adm-field">
          <span>显示名（可选）</span>
          <input v-model.trim="form.displayname" placeholder="如 爱丽丝" />
        </label>
        <label class="adm-field">
          <span>初始密码</span>
          <input v-model="form.password" type="text" placeholder="至少 8 位" />
        </label>
        <div class="adm-modal-f">
          <button class="adm-btn ghost" @click="showCreate = false">取消</button>
          <button class="adm-btn" :disabled="!canCreate || busy === 'create'" @click="doCreate">
            {{ busy === 'create' ? '创建中…' : '创建' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 频道成员弹窗 -->
    <div v-if="membersOf" class="adm-mask" @click.self="membersOf = null">
      <div class="adm-modal">
        <div class="adm-modal-h">{{ membersOf.name }} · 成员</div>
        <div class="adm-mlist">
          <div v-if="membersLoading" class="adm-center"><div class="adm-spin" /> 加载中…</div>
          <template v-else>
            <div v-for="m in memberList" :key="m" class="adm-mrow">
              <span class="adm-ava sm">{{ m.replace(/^@/, '').charAt(0).toUpperCase() }}</span>
              <span class="adm-mid">{{ m }}</span>
            </div>
            <div v-if="!memberList.length" class="adm-empty">没有成员</div>
          </template>
        </div>
        <div class="adm-modal-f">
          <button class="adm-btn ghost" @click="membersOf = null">关闭</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import {
  isServerAdmin,
  listUsers,
  createUser,
  deactivateUser,
  reactivateUser,
  resetPassword,
  setUserAdmin,
  serverName,
  listAdminRooms,
  getRoomMembers,
  deleteRoom,
  getServerVersion,
  getAiConfig,
  setAiConfig,
  getGlobalSkills,
  setGlobalSkills,
  getGlobalAgents,
  setGlobalAgents,
  getGlobalRules,
  setGlobalRules,
  getWorkflows,
  setWorkflows,
  getMembers,
  setMemberTier,
  memberTierLabel,
  MEMBER_TIERS,
  type MemberMap,
  getGating,
  setGating,
  GATE_CATALOG,
  GATE_LEVELS,
  type GatingMap,
  AI_TOOL_CATALOG,
  AI_PROVIDERS,
  type AdminUser,
  type AdminRoom,
  type GlobalSkill,
  type GlobalAgent,
  type GlobalRule,
  type WorkflowDef,
} from '@/matrix/client'
import { useToast } from '@/composables/useToast'

// 作为覆盖层使用：关闭时通知父组件（LiveView）收起
const emit = defineEmits<{ (e: 'close'): void }>()

const { success, warn } = useToast()

// 当前管理模块：用户/频道/AI配置/技能库/智能体/规则/工作流/数据概览
const tab = ref<'users' | 'rooms' | 'ai' | 'skills' | 'agents' | 'rules' | 'workflows' | 'gating' | 'overview'>('users')

// 页面状态机：checking 校验中 / denied 无权限 / ok 已是管理员
const state = ref<'checking' | 'denied' | 'ok'>('checking')
const loading = ref(false)
const users = ref<AdminUser[]>([])
// busy 存"正在操作的用户 id"或 'create'，用于禁用对应按钮、防重复点击
const busy = ref<string | null>(null)
// 会员等级 map（userId→slug，只含非免费的）+ 正在调整的用户 id（禁用对应下拉防抖）
const members = ref<MemberMap>({})
const tierBusy = ref<string | null>(null)

/** 取某用户的会员等级 slug（map 里没有即免费）。 */
function memberTier(userId: string): string {
  return members.value[userId] || 'free'
}

const domain = computed(() => serverName())

// 新建用户表单
const showCreate = ref(false)
const form = reactive({ username: '', displayname: '', password: '' })
const canCreate = computed(
  () => form.username.length > 0 && form.password.length >= 8,
)

/** 取头像首字（显示名首字，没有就用 id 首字母） */
function avatarOf(u: AdminUser): string {
  const s = u.name || u.id.replace(/^@/, '')
  return s.charAt(0).toUpperCase()
}

/** 进页面先校验管理员；是管理员才拉用户列表 */
async function check() {
  state.value = 'checking'
  const ok = await isServerAdmin()
  if (!ok) { state.value = 'denied'; return }
  state.value = 'ok'
  await loadUsers()
}

async function loadUsers() {
  loading.value = true
  try {
    // 用户列表是主体；会员 map 并行读、失败不阻断（读不到就全员按免费显示）
    const [list, mp] = await Promise.all([
      listUsers(),
      getMembers().catch(() => ({} as MemberMap)),
    ])
    users.value = list
    members.value = mp
  } catch (e: any) {
    warn('加载失败', e?.message || '无法获取用户列表')
  } finally {
    loading.value = false
  }
}

/** 下拉切换会员等级：即时写控制室 cosmac.members；失败回滚 UI。 */
async function onTierChange(u: AdminUser, tier: string) {
  const prev = memberTier(u.id)
  if (tier === prev) return
  tierBusy.value = u.id
  // 乐观更新（select 已显示新值）；失败再回滚
  if (tier === 'free') delete members.value[u.id]
  else members.value = { ...members.value, [u.id]: tier }
  try {
    await setMemberTier(u.id, tier)
    success('已更新会员等级', `${u.name} 现在是「${memberTierLabel(tier)}」`)
  } catch (e: any) {
    // 回滚
    if (prev === 'free') delete members.value[u.id]
    else members.value = { ...members.value, [u.id]: prev }
    warn('设置失败', e?.message || '无法写入会员等级')
  } finally {
    tierBusy.value = null
  }
}

async function toggleAdmin(u: AdminUser) {
  const next = !u.admin
  if (!confirm(`确认${next ? '把' : '撤销'} ${u.name} ${next ? '设为管理员' : '的管理员权限'}？`)) return
  busy.value = u.id
  try {
    const synced = await setUserAdmin(u.id, next)
    u.admin = next // 服务器管理员身份已改成功（无论控制室是否同步）
    if (next) {
      success('已更新', `${u.name} 现在是管理员`)
    } else if (synced) {
      success('已撤为普通成员', `${u.name} 的控制室写权限将由主 AI 同步移除`)
    } else {
      // 控制室同步没成功 → 不能假装撤干净了，明确提示重试
      warn('已撤管理员，但控制室同步失败', `请重试，否则 ${u.name} 可能仍能写 AI 配置`)
    }
  } catch (e: any) {
    warn('操作失败', e?.message || '权限修改失败')
  } finally {
    busy.value = null
  }
}

async function doResetPassword(u: AdminUser) {
  const pwd = prompt(`给 ${u.name} 设置新密码（至少 8 位，会同时踢下线所有设备）：`)
  if (!pwd) return
  if (pwd.length < 8) { warn('密码太短', '至少 8 位'); return }
  busy.value = u.id
  try {
    await resetPassword(u.id, pwd)
    success('密码已重置', `${u.name} 需用新密码重新登录`)
  } catch (e: any) {
    warn('重置失败', e?.message || '无法重置密码')
  } finally {
    busy.value = null
  }
}

async function doDeactivate(u: AdminUser) {
  if (!confirm(`确认停用 ${u.name}？停用后该账号无法登录（可恢复）。`)) return
  busy.value = u.id
  try {
    await deactivateUser(u.id)
    u.deactivated = true
    success('已停用', `${u.name} 已无法登录`)
  } catch (e: any) {
    warn('停用失败', e?.message || '无法停用账号')
  } finally {
    busy.value = null
  }
}

async function doReactivate(u: AdminUser) {
  const pwd = prompt(`恢复 ${u.name} 需同时设新密码（服务器要求，至少 8 位）：`)
  if (!pwd) return
  if (pwd.length < 8) { warn('密码太短', '至少 8 位'); return }
  busy.value = u.id
  try {
    await reactivateUser(u.id, pwd)
    u.deactivated = false
    success('已恢复', `${u.name} 可用新密码登录了`)
  } catch (e: any) {
    warn('恢复失败', e?.message || '无法恢复账号')
  } finally {
    busy.value = null
  }
}

async function doCreate() {
  busy.value = 'create'
  try {
    const uid = await createUser(form.username, form.password, form.displayname || undefined)
    success('已创建', uid)
    showCreate.value = false
    form.username = ''; form.displayname = ''; form.password = ''
    await loadUsers()
  } catch (e: any) {
    warn('创建失败', e?.message || '无法创建账号')
  } finally {
    busy.value = null
  }
}

/* —— 频道管理 —— */
const rooms = ref<AdminRoom[]>([])
const roomsLoading = ref(false)
const roomsLoaded = ref(false)        // 懒加载：首次切到频道 tab 才拉
const roomBusy = ref<string | null>(null)
// 成员弹窗：membersOf 为当前查看的房间，null 表示关闭
const membersOf = ref<AdminRoom | null>(null)
const memberList = ref<string[]>([])
const membersLoading = ref(false)

/** 切到频道 tab；首次进入时懒加载列表 */
function switchToRooms() {
  tab.value = 'rooms'
  if (!roomsLoaded.value) loadRooms()
}

async function loadRooms() {
  roomsLoading.value = true
  try {
    rooms.value = await listAdminRooms()
    roomsLoaded.value = true
  } catch (e: any) {
    warn('加载失败', e?.message || '无法获取频道列表')
  } finally {
    roomsLoading.value = false
  }
}

async function viewMembers(r: AdminRoom) {
  membersOf.value = r
  membersLoading.value = true
  memberList.value = []
  try {
    memberList.value = await getRoomMembers(r.id)
  } catch (e: any) {
    warn('加载失败', e?.message || '无法获取成员')
  } finally {
    membersLoading.value = false
  }
}

async function doDeleteRoom(r: AdminRoom) {
  // 删除不可逆，二次确认；并询问是否一并封禁（禁止重建/重新加入）
  if (!confirm(`确认删除频道「${r.name}」？\n将踢出所有成员并清除历史，不可恢复。`)) return
  const block = confirm('是否同时【封禁】此频道？\n确定 = 封禁（禁止任何人再加入/重建，用于违规群）\n取消 = 仅删除')
  roomBusy.value = r.id
  try {
    await deleteRoom(r.id, block)
    rooms.value = rooms.value.filter(x => x.id !== r.id)
    success('已删除', `频道「${r.name}」已${block ? '删除并封禁' : '删除'}`)
  } catch (e: any) {
    warn('删除失败', e?.message || '无法删除频道')
  } finally {
    roomBusy.value = null
  }
}

/* —— AI 配置 —— */
const aiLoading = ref(false)
const aiSaving = ref(false)
const aiLoaded = ref(false)
// enabled_tools=null 表示全开；UI 里用一个集合表示"当前开启的工具"
const aiForm = reactive<{
  provider: string
  model: string
  system_prompt: string
  tools: Set<string>
}>({
  provider: '',
  model: '',
  system_prompt: '',
  tools: new Set(AI_TOOL_CATALOG.map((t) => t.name)), // 默认全开
})

// 当前选中 provider 的元信息（模型占位符等）
const providerMeta = computed(
  () => AI_PROVIDERS.find((p) => p.value === aiForm.provider) || AI_PROVIDERS[0],
)

function isToolOn(name: string): boolean {
  return aiForm.tools.has(name)
}
function toggleTool(name: string, on: boolean) {
  if (on) aiForm.tools.add(name)
  else aiForm.tools.delete(name)
}

function switchToAi() {
  tab.value = 'ai'
  if (!aiLoaded.value) loadAi()
}

async function loadAi() {
  aiLoading.value = true
  try {
    const cfg = await getAiConfig()
    aiForm.provider = cfg?.provider || ''
    aiForm.model = cfg?.model || ''
    aiForm.system_prompt = cfg?.system_prompt || ''
    const all = AI_TOOL_CATALOG.map((t) => t.name)
    aiForm.tools = new Set(cfg?.enabled_tools ?? all)
    aiLoaded.value = true
  } catch (e: any) {
    warn('加载失败', e?.message || '无法读取 AI 配置')
  } finally {
    aiLoading.value = false
  }
}

async function saveAi() {
  // 选了某家 provider → 提醒「key 在服务器配」（网页不再收 key）
  if (aiForm.provider) {
    if (!confirm(`已选「${providerMeta.value.label}」。请确认服务器已为它配好 API Key（环境变量/Secret Manager），否则 AI 无法回话。仍要保存吗？`)) return
  }
  aiSaving.value = true
  try {
    const all = AI_TOOL_CATALOG.map((t) => t.name)
    // 全开 → 存 null（表示不限制）；否则存当前集合
    const enabled = all.every((n) => aiForm.tools.has(n)) ? null : [...aiForm.tools]
    await setAiConfig({
      provider: aiForm.provider,
      model: aiForm.model,
      system_prompt: aiForm.system_prompt,
      enabled_tools: enabled,
    })
    success('已保存', '主 AI 约 20 秒内热生效')
  } catch (e: any) {
    warn('保存失败', e?.message || '无法写入控制室')
  } finally {
    aiSaving.value = false
  }
}

/* —— 技能库（全局技能，写控制室 state event）—— */
const skills = ref<GlobalSkill[]>([])
const skLoading = ref(false)
const skSaving = ref(false)
const skLoaded = ref(false)
const skEditing = ref(false)
// _isEdit=true 表示编辑已有技能（slug 锁定不可改）
const skForm = reactive<GlobalSkill & { _isEdit: boolean }>({
  slug: '', name: '', description: '', instructions: '', enabled: true, _isEdit: false,
})

function switchToSkills() {
  tab.value = 'skills'
  if (!skLoaded.value) loadSkills()
}

async function loadSkills() {
  skLoading.value = true
  try {
    skills.value = await getGlobalSkills()
    skLoaded.value = true
  } catch (e: any) {
    warn('加载失败', e?.message || '无法读取技能')
  } finally {
    skLoading.value = false
  }
}

function startAddSkill() {
  Object.assign(skForm, {
    slug: '', name: '', description: '', instructions: '', enabled: true, _isEdit: false,
  })
  skEditing.value = true
}

function startEditSkill(s: GlobalSkill) {
  Object.assign(skForm, { ...s, _isEdit: true })
  skEditing.value = true
}

/** 把当前 skills 列表整体写回控制室（全局技能是一个 state event 里的数组）。 */
async function persistSkills(next: GlobalSkill[], okMsg: string) {
  skSaving.value = true
  try {
    await setGlobalSkills(next)
    skills.value = next
    success('已保存', okMsg)
  } catch (e: any) {
    warn('保存失败', e?.message || '无法写入控制室')
    throw e
  } finally {
    skSaving.value = false
  }
}

async function saveSkill() {
  const slug = skForm.slug.trim()
  if (!slug) return
  const item: GlobalSkill = {
    slug,
    name: skForm.name.trim(),
    description: skForm.description.trim(),
    instructions: skForm.instructions,
    enabled: skForm.enabled,
  }
  // 已有同 slug → 覆盖；否则追加
  const next = skills.value.slice()
  const i = next.findIndex((s) => s.slug === slug)
  if (i >= 0) next[i] = item
  else next.push(item)
  try {
    await persistSkills(next, '主 AI 约 20 秒内热生效')
    skEditing.value = false
  } catch { /* persistSkills 已提示 */ }
}

async function toggleSkill(s: GlobalSkill) {
  const next = skills.value.map((x) =>
    x.slug === s.slug ? { ...x, enabled: !x.enabled } : x,
  )
  try { await persistSkills(next, s.enabled ? '已停用' : '已启用') } catch { /* 已提示 */ }
}

async function removeSkill(s: GlobalSkill) {
  if (!confirm(`确认删除技能「${s.name || s.slug}」？`)) return
  const next = skills.value.filter((x) => x.slug !== s.slug)
  try { await persistSkills(next, '已删除') } catch { /* 已提示 */ }
}

/* —— 智能体（全局 Agent，写控制室 state event）—— */
const agents = ref<GlobalAgent[]>([])
const agLoading = ref(false)
const agSaving = ref(false)
const agLoaded = ref(false)
const agEditing = ref(false)
const agForm = reactive<GlobalAgent & { _isEdit: boolean }>({
  slug: '', name: '', description: '', system_prompt: '', model: '',
  skill_slugs: [], enabled: true, _isEdit: false,
})

function switchToAgents() {
  tab.value = 'agents'
  if (!agLoaded.value) loadAgents()
  if (!skLoaded.value) loadSkills() // 绑定技能用的勾选列表
}

async function loadAgents() {
  agLoading.value = true
  try {
    agents.value = await getGlobalAgents()
    agLoaded.value = true
  } catch (e: any) {
    warn('加载失败', e?.message || '无法读取智能体')
  } finally {
    agLoading.value = false
  }
}

function startAddAgent() {
  Object.assign(agForm, {
    slug: '', name: '', description: '', system_prompt: '', model: '',
    skill_slugs: [], enabled: true, _isEdit: false,
  })
  agEditing.value = true
}

function startEditAgent(a: GlobalAgent) {
  Object.assign(agForm, { ...a, skill_slugs: [...a.skill_slugs], _isEdit: true })
  agEditing.value = true
}

function toggleAgentSkill(slug: string, on: boolean) {
  const i = agForm.skill_slugs.indexOf(slug)
  if (on && i < 0) agForm.skill_slugs.push(slug)
  else if (!on && i >= 0) agForm.skill_slugs.splice(i, 1)
}

async function persistAgents(next: GlobalAgent[], okMsg: string) {
  agSaving.value = true
  try {
    await setGlobalAgents(next)
    agents.value = next
    success('已保存', okMsg)
  } catch (e: any) {
    warn('保存失败', e?.message || '无法写入控制室')
    throw e
  } finally {
    agSaving.value = false
  }
}

async function saveAgent() {
  const slug = agForm.slug.trim()
  if (!slug) return
  const item: GlobalAgent = {
    slug,
    name: agForm.name.trim(),
    description: agForm.description.trim(),
    system_prompt: agForm.system_prompt,
    model: agForm.model.trim(),
    skill_slugs: [...agForm.skill_slugs],
    enabled: agForm.enabled,
  }
  const next = agents.value.slice()
  const i = next.findIndex((a) => a.slug === slug)
  if (i >= 0) next[i] = item
  else next.push(item)
  try {
    await persistAgents(next, '已保存智能体')
    agEditing.value = false
  } catch { /* 已提示 */ }
}

async function toggleAgent(a: GlobalAgent) {
  const next = agents.value.map((x) =>
    x.slug === a.slug ? { ...x, enabled: !x.enabled } : x,
  )
  try { await persistAgents(next, a.enabled ? '已停用' : '已启用') } catch { /* 已提示 */ }
}

async function removeAgent(a: GlobalAgent) {
  if (!confirm(`确认删除智能体「${a.name || a.slug}」？`)) return
  const next = agents.value.filter((x) => x.slug !== a.slug)
  try { await persistAgents(next, '已删除') } catch { /* 已提示 */ }
}

/* —— 规则（全局硬约束，写控制室 state event）—— */
const rules = ref<GlobalRule[]>([])
const ruLoading = ref(false)
const ruSaving = ref(false)
const ruLoaded = ref(false)

function switchToRules() {
  tab.value = 'rules'
  if (!ruLoaded.value) loadRules()
}

async function loadRules() {
  ruLoading.value = true
  try {
    rules.value = await getGlobalRules()
    ruLoaded.value = true
  } catch (e: any) {
    warn('加载失败', e?.message || '无法读取规则')
  } finally {
    ruLoading.value = false
  }
}

async function saveRules() {
  ruSaving.value = true
  try {
    // 去掉空行后保存（空文本规则没意义）
    const clean = rules.value
      .map((r) => ({ text: r.text.trim(), enabled: r.enabled }))
      .filter((r) => r.text)
    await setGlobalRules(clean)
    rules.value = clean
    success('已保存', '主 AI 约 20 秒内热生效')
  } catch (e: any) {
    warn('保存失败', e?.message || '无法写入控制室')
  } finally {
    ruSaving.value = false
  }
}

/* —— 会员权限（功能门控，写控制室 cosmac.gating）—— */
const gates = ref<GatingMap>({})
const gateLoading = ref(false)
const gateSaving = ref(false)
const gateLoaded = ref(false)

function switchToGating() {
  tab.value = 'gating'
  if (!gateLoaded.value) loadGating()
}

async function loadGating() {
  gateLoading.value = true
  try {
    gates.value = await getGating() // 已合并默认，目录每项都有值
    gateLoaded.value = true
  } catch (e: any) {
    warn('加载失败', e?.message || '无法读取门控策略')
  } finally {
    gateLoading.value = false
  }
}

async function saveGating() {
  gateSaving.value = true
  try {
    await setGating(gates.value)
    success('已保存', '主 AI 约 15 秒内热生效')
  } catch (e: any) {
    warn('保存失败', e?.message || '无法写入控制室')
  } finally {
    gateSaving.value = false
  }
}

/* —— 工作流连接器（写控制室 state event）—— */
const workflows = ref<WorkflowDef[]>([])
const wfLoading = ref(false)
const wfSaving = ref(false)
const wfLoaded = ref(false)
const wfEditing = ref(false)
const wfForm = reactive<WorkflowDef & { _isEdit: boolean }>({
  slug: '', name: '', platform: 'webhook', url: '', method: 'POST',
  cred: '', input_hint: '', enabled: true,
  mode: 'workflow', ref_id: '', input_key: '', graph: '', async: false, _isEdit: false,
})

const wfUrlPlaceholder = computed(() => ({
  webhook: 'https://n8n.example.com/webhook/xxx',
  dify: 'https://api.dify.ai（或自建 Dify 地址）',
  coze: 'https://api.coze.cn（国际版 https://api.coze.com）',
  comfyui: 'http://你的ComfyUI地址:8188',
}[wfForm.platform] || ''))

function switchToWorkflows() {
  tab.value = 'workflows'
  if (!wfLoaded.value) loadWorkflows()
}

async function loadWorkflows() {
  wfLoading.value = true
  try {
    workflows.value = await getWorkflows()
    wfLoaded.value = true
  } catch (e: any) {
    warn('加载失败', e?.message || '无法读取连接器')
  } finally {
    wfLoading.value = false
  }
}

function startAddWorkflow() {
  Object.assign(wfForm, {
    slug: '', name: '', platform: 'webhook', url: '', method: 'POST',
    cred: '', input_hint: '', enabled: true,
    mode: 'workflow', ref_id: '', input_key: '', graph: '', async: false, _isEdit: false,
  })
  wfEditing.value = true
}

function startEditWorkflow(w: WorkflowDef) {
  Object.assign(wfForm, { ...w, _isEdit: true })
  wfEditing.value = true
}

async function persistWorkflows(next: WorkflowDef[], okMsg: string) {
  wfSaving.value = true
  try {
    await setWorkflows(next)
    workflows.value = next
    success('已保存', okMsg)
  } catch (e: any) {
    warn('保存失败', e?.message || '无法写入控制室')
    throw e
  } finally {
    wfSaving.value = false
  }
}

async function saveWorkflow() {
  const slug = wfForm.slug.trim()
  if (!slug || !wfForm.url.trim()) return
  const item: WorkflowDef = {
    slug, name: wfForm.name.trim(), platform: wfForm.platform,
    url: wfForm.url.trim(), method: wfForm.method, cred: wfForm.cred.trim(),
    input_hint: wfForm.input_hint.trim(), enabled: wfForm.enabled,
    mode: wfForm.mode, ref_id: wfForm.ref_id.trim(), input_key: wfForm.input_key.trim(),
    graph: wfForm.graph,
    // #3：只有 webhook 支持异步回调；切到 dify/coze/comfyui 时 async 复选框是隐藏的，
    // 这里强制清成 false，免得残留 async=true 让后端挂一个永远等不到回调的 pending。
    async: wfForm.platform === 'webhook' ? wfForm.async : false,
  }
  const next = workflows.value.slice()
  const i = next.findIndex((w) => w.slug === slug)
  if (i >= 0) next[i] = item
  else next.push(item)
  try {
    await persistWorkflows(next, '已保存连接器')
    wfEditing.value = false
  } catch { /* 已提示 */ }
}

async function toggleWorkflow(w: WorkflowDef) {
  const next = workflows.value.map((x) =>
    x.slug === w.slug ? { ...x, enabled: !x.enabled } : x,
  )
  try { await persistWorkflows(next, w.enabled ? '已停用' : '已启用') } catch { /* 已提示 */ }
}

async function removeWorkflow(w: WorkflowDef) {
  if (!confirm(`确认删除连接器「${w.name || w.slug}」？`)) return
  const next = workflows.value.filter((x) => x.slug !== w.slug)
  try { await persistWorkflows(next, '已删除') } catch { /* 已提示 */ }
}

/* —— 数据概览 —— */
const ovLoading = ref(false)
const ovLoaded = ref(false)
const ov = reactive({
  version: '',
  userTotal: 0, adminCount: 0, deactivated: 0,
  roomTotal: 0, publicRooms: 0, encryptedRooms: 0,
  memberSum: 0, avgMembers: 0, activeRooms: 0,
  topRooms: [] as AdminRoom[],
})

function switchToOverview() {
  tab.value = 'overview'
  if (!ovLoaded.value) loadOverview()
}

/** 聚合统计：复用 listUsers + listAdminRooms + getServerVersion，前端算汇总 */
async function loadOverview() {
  ovLoading.value = true
  try {
    const [us, rs, ver] = await Promise.all([listUsers(), listAdminRooms(), getServerVersion()])
    ov.version = ver
    ov.userTotal = us.length
    ov.adminCount = us.filter((u) => u.admin).length
    ov.deactivated = us.filter((u) => u.deactivated).length
    ov.roomTotal = rs.length
    ov.publicRooms = rs.filter((r) => r.isPublic).length
    ov.encryptedRooms = rs.filter((r) => r.encrypted).length
    ov.memberSum = rs.reduce((sum, r) => sum + r.members, 0)
    ov.avgMembers = rs.length ? Math.round((ov.memberSum / rs.length) * 10) / 10 : 0
    ov.activeRooms = rs.filter((r) => r.members >= 2).length
    // 客户端按成员数降序取前 8（不依赖接口排序——实测 Admin API 的 dir=b 在本版未降序）
    ov.topRooms = [...rs].sort((a, b) => b.members - a.members).slice(0, 8)
    ovLoaded.value = true
  } catch (e: any) {
    warn('统计失败', e?.message || '无法获取概览数据')
  } finally {
    ovLoading.value = false
  }
}

onMounted(check)
</script>

<style scoped>
/* 全屏覆盖层：盖住整个工作台，自带关闭按钮 */
.admin-view {
  position: fixed;
  inset: 0;
  z-index: 200;
  display: flex;
  min-height: 0;
  background: var(--bg);
  color: var(--text);
  animation: adm-fade 0.15s ease;
}
@keyframes adm-fade { from { opacity: 0; } to { opacity: 1; } }

.adm-close {
  position: absolute;
  top: 14px; right: 18px;
  z-index: 3;
  width: 30px; height: 30px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-panel);
  color: var(--text-3);
  font-size: 15px; cursor: pointer;
  transition: background 0.1s ease, color 0.1s ease;
}
.adm-close:hover { background: var(--bg-soft); color: var(--text); }

/* —— 左侧菜单 —— */
.adm-nav {
  width: 220px;
  flex-shrink: 0;
  border-right: 1px solid var(--border);
  background: var(--bg-panel);
  display: flex;
  flex-direction: column;
  padding: 16px 12px;
  gap: 18px;
}
.adm-brand { display: flex; align-items: center; gap: 10px; padding: 4px; }
.adm-logo {
  width: 34px; height: 34px; border-radius: 9px;
  background: var(--accent); color: #fff;
  display: inline-flex; align-items: center; justify-content: center; font-size: 17px;
}
.adm-title { font-size: var(--fs-200); font-weight: var(--fw-bold); }
.adm-sub { font-size: var(--fs-75); color: var(--text-3); margin-top: 1px; }
.adm-menu { display: flex; flex-direction: column; gap: 2px; }
.adm-mi {
  display: flex; align-items: center; gap: 9px;
  padding: 9px 10px; border: none; border-radius: 8px;
  background: transparent; color: var(--text-2);
  font-size: var(--fs-100); text-align: left; cursor: pointer;
  transition: background 0.1s ease;
}
.adm-mi:hover:not(:disabled) { background: var(--bg-soft); color: var(--text); }
.adm-mi.active { background: var(--accent-soft); color: var(--accent); font-weight: var(--fw-bold); }
.adm-mi:disabled { color: var(--text-3); cursor: default; }
.adm-mi-ic { width: 18px; text-align: center; }
.adm-soon {
  margin-left: auto; font-size: 10px; color: var(--text-3);
  background: var(--bg-soft); padding: 1px 6px; border-radius: 8px;
}

/* —— 右侧内容 —— */
.adm-main { flex: 1; min-width: 0; overflow-y: auto; padding: 22px 26px; }
.adm-head { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 18px; padding-right: 44px; }
.adm-h1 { font-size: 20px; font-weight: var(--fw-bold); }
.adm-hint { font-size: var(--fs-75); color: var(--text-3); margin-top: 4px; }
.adm-actions { display: flex; gap: 8px; }

.adm-btn {
  border: none; border-radius: 8px; cursor: pointer;
  padding: 8px 14px; font-size: var(--fs-100);
  background: var(--accent); color: #fff; font-weight: var(--fw-bold);
  transition: opacity 0.1s ease;
}
.adm-btn:hover:not(:disabled) { opacity: 0.88; }
.adm-btn:disabled { opacity: 0.5; cursor: default; }
.adm-btn.ghost { background: var(--bg-soft); color: var(--text-2); font-weight: 400; }
.adm-btn.sm { padding: 5px 10px; font-size: var(--fs-75); border-radius: 7px; }
.adm-btn.danger { color: var(--danger); }
.adm-btn.danger:hover:not(:disabled) { background: #fee2e2; opacity: 1; }

/* 技能库 */
.adm-row-actions { display: flex; gap: 6px; justify-content: flex-end; }
.adm-rule-row { display: flex; align-items: flex-start; gap: 10px; margin-bottom: 10px; }
.adm-rule-row input[type=checkbox] { margin-top: 10px; flex-shrink: 0; }
.adm-rule-text { flex: 1; resize: vertical; }
.adm-rule-row .adm-btn { flex-shrink: 0; margin-top: 4px; }
.adm-skill-desc { color: var(--text-2); max-width: 320px; }
.adm-skill-edit {
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 16px;
  margin-bottom: 16px;
  background: var(--bg-soft);
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.adm-badge {
  font-size: var(--fs-75);
  padding: 2px 9px;
  border-radius: 999px;
  background: var(--bg-soft);
  color: var(--text-3);
  border: 1px solid var(--border);
}
.adm-badge.on {
  color: var(--ok, #2e7d32);
  border-color: color-mix(in srgb, var(--ok, #2e7d32) 40%, var(--border));
  background: color-mix(in srgb, var(--ok, #2e7d32) 10%, transparent);
}

/* 表格 */
.adm-table { width: 100%; border-collapse: collapse; font-size: var(--fs-100); }
.adm-table th {
  text-align: left; font-size: var(--fs-75); color: var(--text-3); font-weight: 400;
  padding: 8px 10px; border-bottom: 1px solid var(--border);
}
.adm-ops-h { text-align: right; }
.adm-table td { padding: 11px 10px; border-bottom: 1px solid var(--border-soft); vertical-align: middle; }
.adm-table tr.off td { opacity: 0.55; }

.adm-user { display: flex; align-items: center; gap: 10px; }
.adm-ava {
  width: 32px; height: 32px; border-radius: 8px; flex-shrink: 0;
  background: var(--accent); color: #fff;
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 14px; font-weight: 600;
}
.adm-u-name { font-weight: var(--fw-bold); display: flex; align-items: center; gap: 6px; }
.adm-u-handle { font-size: var(--fs-75); color: var(--text-3); font-family: var(--mono); margin-top: 1px; }

.adm-tag { font-size: 11px; padding: 2px 8px; border-radius: 8px; }
.adm-tag.admin { color: var(--accent); background: var(--accent-soft); }
.adm-tag.member { color: var(--text-3); background: var(--bg-soft); }
.adm-tag.ok { color: var(--ok); background: color-mix(in srgb, var(--ok) 14%, transparent); }
.adm-tag.off { color: var(--danger); background: #fee2e2; }
.adm-tag.bot { color: #fff; background: var(--accent); }

/* 会员等级下拉：免费=低调，付费/创作者=带强调色，一眼可辨 */
.adm-tier {
  font-size: 11px; padding: 3px 8px; border-radius: 8px; cursor: pointer;
  border: 1px solid var(--border); background: var(--bg-panel); color: var(--text-2);
}
.adm-tier:disabled { opacity: 0.5; cursor: default; }
.adm-tier.paid {
  color: var(--accent); border-color: color-mix(in srgb, var(--accent) 40%, var(--border));
  background: var(--accent-soft);
}
.adm-tier.creator {
  color: #b45309; border-color: #f59e0b;
  background: color-mix(in srgb, #f59e0b 14%, transparent);
}
.adm-muted { color: var(--text-3); }

.adm-ops { text-align: right; white-space: nowrap; }
.adm-op {
  border: 1px solid var(--border); background: var(--bg-panel); color: var(--text-2);
  font-size: var(--fs-75); padding: 5px 9px; border-radius: 7px; margin-left: 6px; cursor: pointer;
  transition: background 0.1s ease;
}
.adm-op:hover:not(:disabled) { background: var(--bg-soft); color: var(--text); }
.adm-op:disabled { opacity: 0.4; cursor: default; }
.adm-op.danger { color: var(--danger); border-color: color-mix(in srgb, var(--danger) 40%, var(--border)); }
.adm-op.danger:hover:not(:disabled) { background: #fee2e2; }

/* 居中态（loading / denied） */
.adm-center {
  display: flex; align-items: center; justify-content: center; gap: 10px;
  padding: 60px 0; color: var(--text-3); font-size: var(--fs-100);
}
.adm-spin {
  width: 18px; height: 18px; border-radius: 50%;
  border: 2px solid var(--border); border-top-color: var(--accent);
  animation: adm-rot 0.7s linear infinite;
}
@keyframes adm-rot { to { transform: rotate(360deg); } }

.adm-denied { flex-direction: column; gap: 8px; text-align: center; padding-top: 80px; }
.adm-denied-ic { font-size: 40px; }
.adm-denied-t { font-size: 17px; font-weight: var(--fw-bold); color: var(--text); }
.adm-denied-d { max-width: 380px; line-height: 1.6; }
.adm-denied-d code { font-family: var(--mono); color: var(--accent); }

/* 新建弹窗 */
.adm-mask {
  position: fixed; inset: 0; z-index: 80;
  background: rgba(0, 0, 0, 0.28);
  display: flex; align-items: center; justify-content: center;
}
.adm-modal {
  width: 380px; background: var(--bg-panel);
  border: 1px solid var(--border); border-radius: 14px; padding: 20px;
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.18);
}
.adm-modal-h { font-size: var(--fs-200); font-weight: var(--fw-bold); margin-bottom: 14px; }
.adm-field { display: flex; flex-direction: column; gap: 5px; margin-bottom: 12px; }
.adm-field span { font-size: var(--fs-75); color: var(--text-3); }
.adm-field input {
  border: 1px solid var(--border); border-radius: 8px; padding: 8px 10px;
  font-size: var(--fs-100); background: var(--bg); color: var(--text);
}
.adm-field input:focus { outline: none; border-color: var(--accent); }
.adm-modal-f { display: flex; justify-content: flex-end; gap: 8px; margin-top: 6px; }

/* 频道管理补充 */
.adm-dim { color: var(--text-3); font-size: var(--fs-75); }
.adm-empty { text-align: center; color: var(--text-3); padding: 24px 0; }
.adm-tag.bot { margin-left: 6px; }

/* AI 配置表单 */
.adm-form { max-width: 640px; display: flex; flex-direction: column; gap: 18px; }
.adm-form .adm-field textarea,
.adm-form .adm-field input,
.adm-form .adm-field select {
  border: 1px solid var(--border); border-radius: 8px; padding: 9px 11px;
  font-size: var(--fs-100); background: var(--bg); color: var(--text);
  font-family: inherit; resize: vertical; line-height: 1.5;
}
/* select 高度按内容自适应：覆盖全局 .cam-select 的固定 height:34px——
   它与本表单更高内边距(9px)叠加会把选项文字竖直切掉(34-18<行高)。 */
.adm-form .adm-field select { height: auto; resize: none; }
.adm-form .adm-field textarea:focus,
.adm-form .adm-field input:focus,
.adm-form .adm-field select:focus { outline: none; border-color: var(--accent); }
.adm-note { font-size: var(--fs-75); color: var(--text-3); font-style: normal; line-height: 1.5; }
.adm-tools { display: flex; flex-direction: column; gap: 8px; margin-top: 4px; }
.adm-tool {
  display: flex; align-items: center; gap: 9px; cursor: pointer;
  padding: 8px 10px; border: 1px solid var(--border); border-radius: 8px; background: var(--bg-panel);
}
.adm-tool input { width: 16px; height: 16px; accent-color: var(--accent); }
.adm-tool-l { font-size: var(--fs-100); color: var(--text); }
.adm-tool code { margin-left: auto; font-family: var(--mono); font-size: var(--fs-75); color: var(--text-3); }

/* 数据概览 KPI 卡片 */
.adm-kpis {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px; margin-bottom: 24px;
}
.adm-kpi {
  border: 1px solid var(--border); border-radius: 12px;
  background: var(--bg-panel); padding: 16px 18px;
}
.adm-kpi-v { font-size: 30px; font-weight: var(--fw-bold); color: var(--accent); line-height: 1.1; }
.adm-kpi-l { font-size: var(--fs-100); color: var(--text); margin-top: 4px; }
.adm-kpi-s { font-size: var(--fs-75); color: var(--text-3); margin-top: 2px; }
.adm-h2 { font-size: var(--fs-200); font-weight: var(--fw-bold); margin: 4px 0 12px; }

/* 成员弹窗列表 */
.adm-mlist { max-height: 320px; overflow-y: auto; margin-bottom: 12px; }
.adm-mrow { display: flex; align-items: center; gap: 9px; padding: 6px 2px; }
.adm-ava.sm { width: 26px; height: 26px; font-size: 12px; border-radius: 7px; }
.adm-mid { font-family: var(--mono); font-size: var(--fs-75); color: var(--text-2); }
</style>
