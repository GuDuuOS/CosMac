<template>
  <!-- 放大态：半透明遮罩，点击空白处还原 -->
  <div v-if="maximized" class="ai-backdrop" @click="onToggleMaximized" />

  <aside
    class="ai-panel"
    :class="{ expanded, maximized }"
  >
    <!-- Header（放大态作为弹窗顶栏）-->
    <div class="ai-head">
      <span class="ai-title">筱雨中枢 AI</span>
      <div class="ai-head-actions">
        <button class="ai-ic-btn" title="筱雨中枢 AI 设置" @click="openSettings">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z" />
            <circle cx="12" cy="12" r="3" />
          </svg>
        </button>
        <button v-if="!floating" class="ai-ic-btn" :title="expanded ? '收起' : '展开'" @click="toggleExpanded">
          <!-- 展开态：箭头朝内 -->
          <svg v-if="expanded" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="4 14 10 14 10 20" />
            <polyline points="20 10 14 10 14 4" />
            <line x1="14" y1="10" x2="21" y2="3" />
            <line x1="3" y1="21" x2="10" y2="14" />
          </svg>
          <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="15 3 21 3 21 9" />
            <polyline points="9 21 3 21 3 15" />
            <line x1="21" y1="3" x2="14" y2="10" />
            <line x1="3" y1="21" x2="10" y2="14" />
          </svg>
        </button>
        <button class="ai-ic-btn" :title="floating ? '收回侧栏' : '弹出浮窗'" @click="onToggleFloating">
          <!-- floating 态：四角合并 -->
          <svg v-if="floating" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M3 7V3h4M21 7V3h-4M3 17v4h4M21 17v4h-4" />
          </svg>
          <!-- 默认态：windowed grid -->
          <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect width="18" height="18" x="3" y="3" rx="2" />
            <path d="M12 3v18M3 12h18" />
          </svg>
        </button>
        <button class="ai-ic-btn" title="关闭" @click="hide">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M18 6 6 18M6 6l12 12" />
          </svg>
        </button>
      </div>
    </div>

    <!-- 主体：默认单列；floating 时三栏 -->
    <div class="ai-main">

    <!-- 左栏：最近对话（仅 floating）-->
    <div v-if="floating" class="ai-side ai-side-left">
      <button class="ai-new-chat-btn">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M5 12h14M12 5v14" />
        </svg>
        新对话
      </button>
      <div class="ai-side-sec">
        <div class="ai-side-title">最近对话</div>
        <ul class="ai-side-list">
          <li class="act">选题灵感 · 职场反内耗</li>
          <li>本周内容复盘草稿</li>
          <li>副业避坑 完播率诊断</li>
          <li>探店视频 评论区舆情</li>
          <li>国货护肤 商单报价</li>
          <li>本周发布排期</li>
        </ul>
      </div>
    </div>

    <!-- 中间主对话 -->
    <div class="ai-center">
    <div ref="bodyRef" class="ai-body">
      <div class="ai-intro">
        <img class="ai-avatar" src="/gudu-logo.svg" alt="筱雨工作室" />
        <div class="ai-meta">
          <div class="ai-name">筱雨中枢 AI</div>
          <div class="ai-handle">@xiaoyu_ai</div>
        </div>
        <button class="ai-clear-btn" @click="reset">清空本频道记录</button>
      </div>

      <p class="ai-desc">
        由 CosMac Star Main AI 插件提供服务，在右侧栏与你对话。
      </p>
      <p class="ai-desc dim">
        对话记录由服务端保存（按频道）；切换频道可查看各频道独立记录。
      </p>

      <div class="ai-divider" />

      <p v-if="agentMessages.length === 0" class="ai-tip">
        我是能操控系统的主 AI——在对话里就能<b>建群、自动拉人、查询工作室任务状态</b>。
        试试下面的快捷动作，或直接输入需求。
      </p>

      <!-- 对话流 -->
      <div v-else class="ai-convo">
        <div v-for="m in agentMessages" :key="m.id" class="ai-msg" :class="m.role">
          <!-- 思考进度（Claude Code 式 ⏺ 工具调用流）-->
          <div v-if="m.thinking" class="ai-thinking tool">
            <div
              v-for="(s, si) in stepsOf(m)"
              :key="si"
              class="ai-think-step"
              :class="{ done: s.done, active: !s.done && si === firstPendingIdx(m) }"
            >
              <span class="ai-think-ic">
                <span v-if="s.done" class="ai-dot">⏺</span>
                <span v-else-if="si === firstPendingIdx(m)" class="ai-spin" />
                <span v-else class="ai-dot pending">⏺</span>
              </span>
              <span class="ai-think-label">{{ s.label }}</span>
            </div>
          </div>

          <!-- 承办 Agent 署名（主 AI 派单后由谁交付）-->
          <div v-if="!m.thinking && m.agent" class="ai-by">
            <span class="ai-by-ava">{{ m.agent.slice(0, 1) }}</span>
            <span class="ai-by-tx">由 <b>{{ m.agent }}</b> 交付 · 筱雨中枢派单</span>
          </div>

          <TypeOut
            v-if="m.text"
            class="ai-bubble"
            :text="m.text"
            :animate="m.role === 'ai'"
            @tick="scrollToBottom"
          />

          <!-- 建群人员提案卡（先确认再建群）-->
          <div v-if="m.card && m.card.kind === 'proposal'" class="ai-card">
            <div class="ai-card-h">🤝 建群提案 · <b>#{{ m.card.label }}</b></div>
            <div class="ai-card-sub">勾选要拉入的成员（按任务推荐），确认后建群</div>
            <div class="ai-propose">
              <label
                v-for="c in m.card.candidates"
                :key="c.name"
                class="ai-cand"
                :class="{ off: !c.selected, locked: m.card.done }"
              >
                <input type="checkbox" v-model="c.selected" :disabled="m.card.done" />
                <span class="ai-cand-name">{{ c.name }}</span>
                <span class="ai-cand-role">{{ c.role }}</span>
                <span class="ai-cand-reason">{{ c.reason }}</span>
              </label>
            </div>
            <div v-if="!m.card.done" class="ai-card-actions">
              <button class="ai-card-btn" @click="confirmProposal(m.card)">确认建群（{{ selectedCount(m.card) }} 人）</button>
              <button class="ai-card-btn ghost" @click="cancelProposal(m.card)">取消</button>
            </div>
            <div v-else class="ai-card-done">— 已处理 —</div>
          </div>

          <!-- 建群结果卡 -->
          <div v-else-if="m.card && m.card.kind === 'channel'" class="ai-card">
            <div class="ai-card-h">✅ 已建群 <b>#{{ m.card.label }}</b> · {{ m.card.workspace }}</div>
            <div class="ai-card-sub">自动拉入 {{ m.card.members.length }} 人</div>
            <div class="ai-card-members">
              <span v-for="n in m.card.members" :key="n" class="ai-chip-m">{{ n }}</span>
            </div>
            <button class="ai-card-btn" @click="goChannel(m.card.channelId)">前往频道 →</button>
          </div>

          <!-- 任务状态卡 -->
          <div v-else-if="m.card && m.card.kind === 'tasks'" class="ai-card">
            <div class="ai-card-h">📋 工作室任务状态</div>
            <table class="ai-task-table">
              <thead>
                <tr><th>工作区</th><th>待办</th><th>进行</th><th>完成</th><th>逾期</th></tr>
              </thead>
              <tbody>
                <tr v-for="r in m.card.rows" :key="r.name">
                  <td class="nm">{{ r.name }}</td>
                  <td>{{ r.pending }}</td>
                  <td>{{ r.inProgress }}</td>
                  <td>{{ r.done }}</td>
                  <td :class="{ over: r.overdue > 0 }">{{ r.overdue }}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- 选题灵感卡 -->
          <div v-else-if="m.card && m.card.kind === 'topics'" class="ai-card">
            <div class="ai-card-h">💡 选题灵感 · <b>{{ m.card.theme }}</b></div>
            <div class="ai-card-sub">按预估热度排序，点「写脚本」直接生成分镜</div>
            <div class="ai-topics">
              <div v-for="(t, ti) in m.card.topics" :key="ti" class="ai-topic">
                <div class="ai-topic-top">
                  <span class="ai-topic-rank">{{ ti + 1 }}</span>
                  <span class="ai-topic-title">{{ t.title }}</span>
                </div>
                <div class="ai-topic-meta">
                  <span class="ai-tag">{{ t.angle }}</span>
                  <span class="ai-tag plat">{{ t.platform }}</span>
                  <span class="ai-heat"><i class="ai-heat-bar"><i :style="{ width: t.heat + '%' }" /></i>热度 {{ t.heat }}</span>
                </div>
                <div class="ai-topic-hook">🎣 {{ t.hook }}</div>
                <button class="ai-card-btn sm" @click="draftFromTopic(t)">写脚本 →</button>
              </div>
            </div>
          </div>

          <!-- 数据分析卡 -->
          <div v-else-if="m.card && m.card.kind === 'analysis'" class="ai-card">
            <div class="ai-card-h">📈 数据分析 · <b>{{ m.card.theme }}</b> · 近 7 天</div>
            <div class="ai-metric-row">
              <div v-for="mt in m.card.metrics" :key="mt.label" class="ai-metric">
                <div class="ai-metric-v">{{ mt.value }}</div>
                <div class="ai-metric-l">{{ mt.label }}</div>
                <div class="ai-metric-d" :class="{ up: mt.up, down: !mt.up }">{{ mt.delta }}</div>
              </div>
            </div>
            <svg class="ai-spark" viewBox="0 0 280 64" preserveAspectRatio="none">
              <polyline :points="sparkPoints(m.card.spark)" fill="none" stroke="var(--accent)" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
            <ul class="ai-findings">
              <li v-for="(f, fi) in m.card.findings" :key="fi">{{ f }}</li>
            </ul>
          </div>

          <!-- 发布排期卡 -->
          <div v-else-if="m.card && m.card.kind === 'schedule'" class="ai-card">
            <div class="ai-card-h">🗓 发布排期 · <b>{{ m.card.theme }}</b></div>
            <table class="ai-task-table">
              <thead><tr><th>日期</th><th>时间</th><th>平台</th><th>内容</th><th>状态</th></tr></thead>
              <tbody>
                <tr v-for="(r, ri) in m.card.rows" :key="ri">
                  <td class="nm">{{ r.day }}</td>
                  <td>{{ r.time }}</td>
                  <td>{{ r.platform }}</td>
                  <td class="ai-sch-content">{{ r.content }}</td>
                  <td><span class="ai-status">{{ r.status }}</span></td>
                </tr>
              </tbody>
            </table>
            <button class="ai-card-btn" @click="notify('已同步到「发布-排期日历」', '本周 ' + m.card.rows.length + ' 条内容已写入日历')">同步到发布日历 →</button>
          </div>

          <!-- 周报卡 -->
          <div v-else-if="m.card && m.card.kind === 'report'" class="ai-card">
            <div class="ai-card-h">📑 数据周报 · <b>{{ m.card.period }}</b></div>
            <div class="ai-metric-row">
              <div v-for="mt in m.card.metrics" :key="mt.label" class="ai-metric">
                <div class="ai-metric-v">{{ mt.value }}</div>
                <div class="ai-metric-l">{{ mt.label }}</div>
                <div class="ai-metric-d" :class="{ up: mt.up, down: !mt.up }">{{ mt.delta }}</div>
              </div>
            </div>
            <div v-for="(sec, si) in m.card.sections" :key="si" class="ai-report-sec">
              <div class="ai-report-t">{{ sec.title }}</div>
              <ul><li v-for="(l, li) in sec.lines" :key="li">{{ l }}</li></ul>
            </div>
            <div class="ai-card-actions">
              <button class="ai-card-btn" @click="notify('周报 PDF 已生成', 'CosMac Star_数据周报_' + m.card.period.replace(/[^0-9/]/g, '') + '.pdf')">导出 PDF</button>
              <button class="ai-card-btn ghost" @click="notify('已推送到「数据-涨粉复盘」频道')">推送到频道</button>
            </div>
          </div>

          <!-- 脚本卡 -->
          <div v-else-if="m.card && m.card.kind === 'script'" class="ai-card">
            <div class="ai-card-h">🎬 短视频脚本 · <b>{{ m.card.theme }}</b></div>
            <div class="ai-script-titles">
              <div class="ai-script-sub">备选标题</div>
              <div v-for="(t, ti) in m.card.titles" :key="ti" class="ai-script-title">{{ ti + 1 }}. {{ t }}</div>
            </div>
            <table class="ai-task-table ai-shot-table">
              <thead><tr><th>分镜</th><th>画面</th><th>口播</th></tr></thead>
              <tbody>
                <tr v-for="(s, si) in m.card.shots" :key="si">
                  <td class="nm">{{ s.scene }}</td>
                  <td>{{ s.visual }}</td>
                  <td class="ai-shot-voice">{{ s.voice }}</td>
                </tr>
              </tbody>
            </table>
            <div class="ai-script-cta">📣 {{ m.card.cta }}</div>
            <button class="ai-card-btn" @click="notify('脚本已存入「拍摄-脚本分镜」频道')">存到脚本频道 →</button>
          </div>

          <!-- 开题问卷卡（主 AI 逐题反问 · Claude Code 式选项框）-->
          <div v-else-if="m.card && m.card.kind === 'intake'" class="ai-ask">
            <!-- 已答过的问题：折叠成一行回显 -->
            <div
              v-for="(q, qi) in m.card.questions"
              :key="q.key"
              v-show="qi < m.card.step || (m.card.done && qi <= m.card.step)"
              class="ai-ask-answered"
            >
              <span class="ai-ask-done-ic">⏺</span>
              <span class="ai-ask-q">{{ q.label }}</span>
              <span class="ai-ask-a">{{ q.selected }}</span>
            </div>

            <!-- 当前问题：编号选项框（仿 Claude Code AskUserQuestion：标签 + 选项标题 + 说明 + 其他）-->
            <div v-if="!m.card.done" class="ai-ask-box">
              <div class="ai-ask-head">
                <span class="ai-ask-prompt">?</span>
                <span class="ai-ask-tag">{{ m.card.questions[m.card.step].tag }}</span>
                <span class="ai-ask-title">{{ m.card.questions[m.card.step].label }}</span>
                <span class="ai-ask-step">{{ m.card.step + 1 }}/{{ m.card.questions.length }}</span>
              </div>
              <button
                v-for="(opt, oi) in m.card.questions[m.card.step].options"
                :key="opt.label"
                class="ai-ask-opt"
                :class="{ active: cursor === oi }"
                @mouseenter="cursor = oi"
                @click="answerIntake(m.card, opt.label)"
              >
                <span class="ai-ask-cursor">❯</span>
                <span class="ai-ask-num">{{ oi + 1 }}</span>
                <span class="ai-ask-opt-bd">
                  <span class="ai-ask-opt-tx">{{ opt.label }}</span>
                  <span class="ai-ask-opt-desc">{{ opt.desc }}</span>
                </span>
              </button>
              <!-- 其他…自定义 -->
              <div
                class="ai-ask-opt other"
                :class="{ active: cursor === m.card.questions[m.card.step].options.length }"
                @mouseenter="cursor = m.card.questions[m.card.step].options.length"
              >
                <span class="ai-ask-cursor">❯</span>
                <span class="ai-ask-num">{{ m.card.questions[m.card.step].options.length + 1 }}</span>
                <button
                  v-if="otherOpenFor !== m.card.step"
                  class="ai-ask-other-btn"
                  @click="otherOpenFor = m.card.step"
                >其他…（自定义输入）</button>
                <span v-else class="ai-ask-other-row">
                  <input
                    class="ai-ask-other-input"
                    v-model="m.card.questions[m.card.step].custom"
                    placeholder="输入自定义答案，回车确认"
                    @keyup.enter="confirmOther(m.card)"
                  />
                  <button class="ai-ask-other-go" @click="confirmOther(m.card)">❯</button>
                </span>
              </div>
              <div class="ai-ask-hint">↑↓ 移动 · Enter 选中 · 数字 1–{{ m.card.questions[m.card.step].options.length }} 直选 · 选完自动下一项</div>
            </div>
          </div>

          <!-- 爆款全链路方案卡 -->
          <div v-else-if="m.card && m.card.kind === 'plan'" class="ai-card">
            <div class="ai-card-h">🚀 爆款全链路方案 · <b>{{ m.card.theme }}</b></div>
            <div class="ai-plan-brief">
              <span class="ai-tag plat">{{ m.card.brief.platform }}</span>
              <span class="ai-tag">{{ m.card.brief.format }}</span>
              <span class="ai-tag">{{ m.card.brief.audience }}</span>
              <span class="ai-tag">{{ m.card.brief.goal }}</span>
            </div>
            <div class="ai-plan-topic">🎯 {{ m.card.topic.title }}</div>
            <div class="ai-plan-steps">
              <div v-for="(s, si) in m.card.steps" :key="si" class="ai-plan-step">
                <span class="ai-plan-n">{{ si + 1 }}</span>
                <div class="ai-plan-tx">
                  <div class="ai-plan-agent">
                    {{ s.agent }}
                    <span class="ai-plan-kind" :class="s.human ? 'human' : 'bot'">{{ s.human ? '@真人' : 'AI' }}</span>
                    <span class="ai-plan-task">· {{ s.task }}</span>
                  </div>
                  <div class="ai-plan-out">→ {{ s.output }}</div>
                </div>
              </div>
            </div>
            <div class="ai-plan-next">
              <div class="ai-report-t">下一步</div>
              <ul><li v-for="(a, ai2) in m.card.nextActions" :key="ai2">{{ a }}</li></ul>
            </div>
            <button v-if="!m.card.launched" class="ai-card-btn" @click="launchCampaign(m.card)">一键启动全链路 ⚡（建专班频道 + 派单）</button>
            <button v-else class="ai-card-btn ghost" @click="m.card.channelId && router.push({ name: 'ops', params: { id: m.card.channelId } })">前往「爆款专班」频道 →</button>
          </div>

          <!-- 商单报价方案卡 -->
          <div v-else-if="m.card && m.card.kind === 'deal'" class="ai-card">
            <div class="ai-card-h">💼 商单报价方案 · <b>{{ m.card.brand }}</b></div>
            <div class="ai-plan-brief">
              <span class="ai-tag plat">{{ m.card.brief.form }}</span>
              <span class="ai-tag">{{ m.card.brief.pricing }}</span>
              <span class="ai-tag">{{ m.card.brief.bottomLine }}</span>
            </div>
            <table class="ai-task-table">
              <thead><tr><th>形式</th><th>粉丝</th><th>均播</th><th>建议报价</th></tr></thead>
              <tbody>
                <tr v-for="(q, qi) in m.card.quotes" :key="qi">
                  <td class="nm">{{ q.form }}</td>
                  <td>{{ q.fans }}</td>
                  <td>{{ q.avgPlay }}</td>
                  <td class="ai-deal-price">{{ q.price }}</td>
                </tr>
              </tbody>
            </table>
            <div class="ai-plan-steps">
              <div v-for="(s, si) in m.card.steps" :key="si" class="ai-plan-step">
                <span class="ai-plan-n">{{ si + 1 }}</span>
                <div class="ai-plan-tx">
                  <div class="ai-plan-agent">
                    {{ s.agent }}
                    <span class="ai-plan-kind" :class="s.human ? 'human' : 'bot'">{{ s.human ? '@真人' : 'AI' }}</span>
                    <span class="ai-plan-task">· {{ s.task }}</span>
                  </div>
                  <div class="ai-plan-out">→ {{ s.output }}</div>
                </div>
              </div>
            </div>
            <div class="ai-plan-next">
              <div class="ai-report-t">下一步</div>
              <ul><li v-for="(a, ai3) in m.card.nextActions" :key="ai3">{{ a }}</li></ul>
            </div>
            <button v-if="!m.card.launched" class="ai-card-btn" @click="launchDealCampaign(m.card)">确认报价，启动商单专班 💼（建频道 + 派单）</button>
            <button v-else class="ai-card-btn ghost" @click="m.card.channelId && router.push({ name: 'ops', params: { id: m.card.channelId } })">前往「商单专班」频道 →</button>
          </div>

          <!-- 舆情应对方案卡 -->
          <div v-else-if="m.card && m.card.kind === 'crisis'" class="ai-card">
            <div class="ai-card-h">🚨 舆情应对方案 · <b>{{ m.card.event }}</b></div>
            <div class="ai-plan-brief">
              <span class="ai-tag plat">{{ m.card.brief.tone }}</span>
              <span class="ai-tag">{{ m.card.brief.scope }}</span>
              <span class="ai-tag">{{ m.card.brief.action }}</span>
            </div>
            <div class="ai-crisis-draft">
              <div class="ai-crisis-draft-t">📝 {{ m.card.draftTitle }}</div>
              <p v-for="(l, li) in m.card.draftLines" :key="li">{{ l }}</p>
            </div>
            <div class="ai-plan-steps">
              <div v-for="(s, si) in m.card.steps" :key="si" class="ai-plan-step">
                <span class="ai-plan-n">{{ si + 1 }}</span>
                <div class="ai-plan-tx">
                  <div class="ai-plan-agent">
                    {{ s.agent }}
                    <span class="ai-plan-kind" :class="s.human ? 'human' : 'bot'">{{ s.human ? '@真人' : 'AI' }}</span>
                    <span class="ai-plan-task">· {{ s.task }}</span>
                  </div>
                  <div class="ai-plan-out">→ {{ s.output }}</div>
                </div>
              </div>
            </div>
            <div class="ai-plan-next">
              <div class="ai-report-t">下一步</div>
              <ul><li v-for="(a, ai4) in m.card.nextActions" :key="ai4">{{ a }}</li></ul>
            </div>
            <button v-if="!m.card.launched" class="ai-card-btn" @click="launchCrisisCampaign(m.card)">审定回应，启动舆情应对 🚨（建频道 + 派单）</button>
            <button v-else class="ai-card-btn ghost" @click="m.card.channelId && router.push({ name: 'ops', params: { id: m.card.channelId } })">前往「舆情应对」频道 →</button>
          </div>

          <!-- 复盘优化方案卡 -->
          <div v-else-if="m.card && m.card.kind === 'review'" class="ai-card">
            <div class="ai-card-h">🔧 复盘优化方案 · <b>{{ m.card.subject }}</b></div>
            <div class="ai-plan-brief">
              <span class="ai-tag plat">{{ m.card.brief.problem }}</span>
              <span class="ai-tag">{{ m.card.brief.fix }}</span>
              <span class="ai-tag">{{ m.card.brief.redistribute }}</span>
            </div>
            <div class="ai-metric-row">
              <div v-for="mt in m.card.metrics" :key="mt.label" class="ai-metric">
                <div class="ai-metric-v">{{ mt.value }}</div>
                <div class="ai-metric-l">{{ mt.label }}</div>
                <div class="ai-metric-d" :class="{ up: mt.up, down: !mt.up }">{{ mt.delta }}</div>
              </div>
            </div>
            <div class="ai-crisis-draft">
              <div class="ai-crisis-draft-t">🎣 文案 Agent 改写的新钩子</div>
              <p v-for="(h, hi) in m.card.hooks" :key="hi">{{ hi + 1 }}. {{ h }}</p>
            </div>
            <div class="ai-plan-steps">
              <div v-for="(s, si) in m.card.steps" :key="si" class="ai-plan-step">
                <span class="ai-plan-n">{{ si + 1 }}</span>
                <div class="ai-plan-tx">
                  <div class="ai-plan-agent">{{ s.agent }}<span class="ai-plan-kind" :class="s.human ? 'human' : 'bot'">{{ s.human ? '@真人' : 'AI' }}</span><span class="ai-plan-task">· {{ s.task }}</span></div>
                  <div class="ai-plan-out">→ {{ s.output }}</div>
                </div>
              </div>
            </div>
            <div class="ai-plan-next">
              <div class="ai-report-t">下一步</div>
              <ul><li v-for="(a, ai5) in m.card.nextActions" :key="ai5">{{ a }}</li></ul>
            </div>
            <button v-if="!m.card.launched" class="ai-card-btn" @click="launchReviewCampaign(m.card)">确认优化，启动复盘专班 🔧（建频道 + 派单）</button>
            <button v-else class="ai-card-btn ghost" @click="m.card.channelId && router.push({ name: 'ops', params: { id: m.card.channelId } })">前往「复盘专班」频道 →</button>
          </div>

          <!-- 私域增长方案卡 -->
          <div v-else-if="m.card && m.card.kind === 'growth'" class="ai-card">
            <div class="ai-card-h">📣 私域增长方案 · <b>{{ m.card.brief.goal }}</b></div>
            <div class="ai-plan-brief">
              <span class="ai-tag plat">{{ m.card.brief.base }}</span>
              <span class="ai-tag">{{ m.card.brief.hook }}</span>
              <span class="ai-tag">{{ m.card.brief.rhythm }}</span>
            </div>
            <div class="ai-metric-row">
              <div v-for="mt in m.card.metrics" :key="mt.label" class="ai-metric">
                <div class="ai-metric-v">{{ mt.value }}</div>
                <div class="ai-metric-l">{{ mt.label }}</div>
                <div class="ai-metric-d up">{{ mt.delta }}</div>
              </div>
            </div>
            <div class="ai-crisis-draft">
              <div class="ai-crisis-draft-t">📅 文案 Agent 拟的打卡话题</div>
              <p v-for="(a, ai6) in m.card.activities" :key="ai6">{{ a }}</p>
            </div>
            <div class="ai-plan-steps">
              <div v-for="(s, si) in m.card.steps" :key="si" class="ai-plan-step">
                <span class="ai-plan-n">{{ si + 1 }}</span>
                <div class="ai-plan-tx">
                  <div class="ai-plan-agent">{{ s.agent }}<span class="ai-plan-kind" :class="s.human ? 'human' : 'bot'">{{ s.human ? '@真人' : 'AI' }}</span><span class="ai-plan-task">· {{ s.task }}</span></div>
                  <div class="ai-plan-out">→ {{ s.output }}</div>
                </div>
              </div>
            </div>
            <div class="ai-plan-next">
              <div class="ai-report-t">下一步</div>
              <ul><li v-for="(a, ai7) in m.card.nextActions" :key="ai7">{{ a }}</li></ul>
            </div>
            <button v-if="!m.card.launched" class="ai-card-btn" @click="launchGrowthCampaign(m.card)">确认方案，启动私域增长 📣（建频道 + 派单）</button>
            <button v-else class="ai-card-btn ghost" @click="m.card.channelId && router.push({ name: 'ops', params: { id: m.card.channelId } })">前往「私域增长」频道 →</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Slash 命令面板 -->
    <div v-if="showSlash" class="ai-slash-pop">
      <div class="ai-slash-sh">SLASH COMMANDS</div>
      <div
        v-for="(c, i) in slashCommands"
        :key="c.cmd"
        class="ai-slash-si"
        :class="{ act: i === 0 }"
        @mousedown.prevent="pickCommand(c.cmd)"
      >
        <span class="cmd">{{ c.cmd }}</span>
        <span class="desc">{{ c.desc }}</span>
      </div>
    </div>

    <!-- 底部输入区 -->
    <div class="ai-composer">
      <div class="ai-quick">
        <button class="ai-quick-chip" @click="quick('建群')">＋ 建群并拉人</button>
        <button class="ai-quick-chip" @click="quick('任务')">📋 查任务状态</button>
      </div>
      <div class="ai-input-box">
        <span class="ai-prompt-mark">&gt;</span>
        <textarea
          v-model="text"
          class="cli"
          placeholder="描述目标，或输入 / 调用命令　·　Enter 发送"
          @keydown.enter.exact.prevent="send"
          @input="onInput"
          @blur="onBlur"
        />
        <div class="ai-toolbar">
          <div class="ai-tb-left">
            <button class="ai-tb-btn" title="添加附件" @click="toast('📎 添加附件')">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l8.57-8.57A4 4 0 1 1 17.93 8.8L9.41 17.32a2 2 0 0 1-2.83-2.83l8.49-8.48" />
              </svg>
            </button>
            <button class="ai-tb-btn" title="@提及" @click="insert('@')">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="12" cy="12" r="4" />
                <path d="M16 8v5a3 3 0 0 0 6 0v-1a10 10 0 1 0-4 8" />
              </svg>
            </button>
            <button class="ai-tb-btn" title="命令" @click="insert('/')">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="m17 6-10 12" />
              </svg>
            </button>
            <button class="ai-tb-btn" title="表情" @click="toast('😊 表情')">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="12" cy="12" r="10" />
                <path d="M8 14s1.5 2 4 2 4-2 4-2M9 9h.01M15 9h.01" />
              </svg>
            </button>
            <button class="ai-tb-btn" title="语音输入" @click="toast('🎤 语音输入（演示）')">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <rect width="6" height="11" x="9" y="2" rx="3" />
                <path d="M19 10v1a7 7 0 0 1-14 0v-1M12 18v4M8 22h8" />
              </svg>
            </button>
          </div>
          <button class="ai-send-ic" :disabled="!text.trim()" title="发送" @click="send">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">
              <path d="M22 2 11 13" />
              <path d="M22 2 15 22l-4-9-9-4Z" />
            </svg>
          </button>
        </div>
      </div>
    </div>
    </div><!-- /ai-center -->

    <!-- 右栏：进度 + 上下文（仅 floating）-->
    <div v-if="floating" class="ai-side ai-side-right">
      <div class="ai-side-sec">
        <div class="ai-side-title with-meta">
          <span>Progress</span>
          <span class="ai-side-meta">5/8</span>
        </div>
        <ul class="ai-progress-list">
          <li class="done">热点选题扫描</li>
          <li class="done">对标账号拆解</li>
          <li class="done">爆款标题生成</li>
          <li class="done">脚本初稿草拟</li>
          <li class="done">封面方案生成</li>
          <li class="in">数据复盘报告生成中…</li>
          <li>素材库去重</li>
          <li>推送发布排期</li>
        </ul>
      </div>
      <div class="ai-side-sec">
        <div class="ai-side-title">CosMac StarOS · 上下文</div>
        <ul class="ai-ctx-list">
          <li><span class="ic">📄</span>Instructions · CLAUDE.md</li>
          <li><span class="ic">📊</span>全平台数据_2026Q2.xlsx</li>
          <li><span class="ic">📑</span>平台规则与避雷.pdf</li>
          <li><span class="ic">🧾</span>商单合作合同模板.docx</li>
        </ul>
      </div>
    </div>

    </div><!-- /ai-main -->
  </aside>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useAiPanel } from '@/composables/useAiPanel'
import { useRightPanel } from '@/composables/useRightPanel'
import { useSystemAi } from '@/composables/useSystemAi'
import { useAiAgent, type AiCard } from '@/composables/useAiAgent'
import { useToast } from '@/composables/useToast'
import TypeOut from '@/components/layout/TypeOut.vue'

const { hide, toggleExpanded, toggleMaximized, expanded, maximized } = useAiPanel()
const { hide: hideRight } = useRightPanel()
const { open: openSettings } = useSystemAi()
const { messages: agentMessages, runCommand, reset, confirmProposal, cancelProposal, draftFromTopic, answerIntake, launchPlan, launchDeal, launchCrisis, launchReview, launchGrowth } = useAiAgent()
const { success: notify, toast } = useToast()
const router = useRouter()

type PlanCard = Extract<AiCard, { kind: 'plan' }>
type DealCard = Extract<AiCard, { kind: 'deal' }>
type CrisisCard = Extract<AiCard, { kind: 'crisis' }>
type ReviewCard = Extract<AiCard, { kind: 'review' }>
type GrowthCard = Extract<AiCard, { kind: 'growth' }>
type IntakeCard = Extract<AiCard, { kind: 'intake' }>

/** 一键启动全链路：建专班频道 → 跳过去看群里运转 */
function launchCampaign(card: PlanCard) {
  const id = launchPlan(card)
  notify('爆款专班已启动', '已建频道派单 · 3 个拍板节点已加入「待办事宜」')
  router.push({ name: 'ops', params: { id } })
  hide()
}

/** 一键启动商单：建商单专班频道 → 跳过去看群里运转 */
function launchDealCampaign(card: DealCard) {
  const id = launchDeal(card)
  notify('商单专班已启动', '已建频道派单 · 3 个拍板节点已加入「待办事宜」')
  router.push({ name: 'ops', params: { id } })
  hide()
}

/** 一键启动舆情应对：建舆情频道 → 跳过去看群里运转 */
function launchCrisisCampaign(card: CrisisCard) {
  const id = launchCrisis(card)
  notify('舆情应对已启动', '已建频道派单 · 3 个拍板节点已加入「待办事宜」')
  router.push({ name: 'ops', params: { id } })
  hide()
}

/** 一键启动复盘优化：建复盘专班频道 → 跳过去看群里运转 */
function launchReviewCampaign(card: ReviewCard) {
  const id = launchReview(card)
  notify('复盘专班已启动', '已建频道派单 · 3 个拍板节点已加入「待办事宜」')
  router.push({ name: 'ops', params: { id } })
  hide()
}

/** 一键启动私域增长：建私域增长频道 → 跳过去看群里运转 */
function launchGrowthCampaign(card: GrowthCard) {
  const id = launchGrowth(card)
  notify('私域增长已启动', '已建频道派单 · 3 个拍板节点已加入「待办事宜」')
  router.push({ name: 'ops', params: { id } })
  hide()
}

/** 当前等待作答的开题问题（用于数字键选择）*/
const activeIntake = computed<IntakeCard | null>(() => {
  for (let i = agentMessages.length - 1; i >= 0; i--) {
    const c = agentMessages[i].card
    if (c && c.kind === 'intake') return c.done ? null : c
  }
  return null
})

/** 「其他…」展开所在的题号（-1 表示都没展开）*/
const otherOpenFor = ref(-1)
/** 当前高亮的选项序号（鼠标悬停 / ↑↓ 共用一个光标，含末尾「其他」行）*/
const cursor = ref(0)

/** 切换到新问题时，光标落到「已预选/默认」那一项——AI 预填后 Enter 即确认 */
watch(
  () => (activeIntake.value ? activeIntake.value.step : -1),
  () => {
    otherOpenFor.value = -1
    const card = activeIntake.value
    if (!card) { cursor.value = 0; return }
    const q = card.questions[card.step]
    const idx = q ? q.options.findIndex((o) => o.label === q.selected) : -1
    cursor.value = idx >= 0 ? idx : 0
  }
)

/** 确认自定义答案 */
function confirmOther(card: IntakeCard) {
  const q = card.questions[card.step]
  const v = (q?.custom ?? '').trim()
  if (!v) return
  otherOpenFor.value = -1
  answerIntake(card, v)
}

/** Claude Code 式键盘选项：↑↓ 移动光标、Enter 选中、数字直选；焦点在输入框时不拦截 */
function onIntakeKey(e: KeyboardEvent) {
  const card = activeIntake.value
  if (!card) return
  const el = document.activeElement
  if (el && (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT')) return
  const q = card.questions[card.step]
  if (!q) return
  const total = q.options.length + 1 // 末尾「其他」行

  if (e.key === 'ArrowDown') { e.preventDefault(); cursor.value = (cursor.value + 1) % total; return }
  if (e.key === 'ArrowUp')   { e.preventDefault(); cursor.value = (cursor.value - 1 + total) % total; return }
  if (e.key === 'Enter') {
    e.preventDefault()
    if (cursor.value < q.options.length) answerIntake(card, q.options[cursor.value].label)
    else otherOpenFor.value = card.step
    return
  }
  const n = Number(e.key)
  if (n >= 1 && n <= q.options.length) {
    e.preventDefault()
    cursor.value = n - 1
    answerIntake(card, q.options[n - 1].label)
  }
}
onMounted(() => window.addEventListener('keydown', onIntakeKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onIntakeKey))

/** 把 0-100 的数列映射成 sparkline 折线点（viewBox 280×64）*/
function sparkPoints(data: number[]): string {
  const n = data.length
  if (n === 0) return ''
  const w = 280, h = 64, pad = 4
  return data
    .map((v, i) => {
      const x = pad + (i * (w - pad * 2)) / (n - 1)
      const y = h - pad - (v / 100) * (h - pad * 2)
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')
}

function selectedCount(card: { candidates: { selected: boolean }[] }) {
  return card.candidates.filter((c) => c.selected).length
}

function stepsOf(m: { steps?: { label: string; done: boolean }[] }) {
  return m.steps ?? []
}
function firstPendingIdx(m: { steps?: { label: string; done: boolean }[] }) {
  return (m.steps ?? []).findIndex((s) => !s.done)
}

/** 对话区随内容增长自动滚到底部（含思考步骤、结果填充）*/
const bodyRef = ref<HTMLElement | null>(null)
function scrollToBottom() {
  const el = bodyRef.value
  if (el) el.scrollTop = el.scrollHeight
}
watch(agentMessages, () => nextTick(scrollToBottom), { deep: true })
onMounted(() => nextTick(scrollToBottom))

/** 展开时自动收起 RightPanel，腾出空间 */
watch(expanded, (e) => { if (e) hideRight() })

/** 放大 / 还原：进入放大态（Cowork 全屏弹窗）时顺手收起右侧「关于此频道」面板 */
function onToggleMaximized() {
  toggleMaximized()
  if (maximized.value) hideRight()
}

const text = ref('')
const showSlash = ref(false)

const slashCommands = [
  { cmd: '/help',    desc: '查看所有命令' },
  { cmd: '/summary', desc: '总结当前频道近期内容' },
  { cmd: '/script',  desc: '帮我起草短视频脚本' },
  { cmd: '/title',   desc: '生成爆款标题' },
  { cmd: '/kb',      desc: '在我的素材库中搜索' }
]

function send() {
  if (!text.value.trim()) return
  runCommand(text.value)
  text.value = ''
  showSlash.value = false
}

/** 快捷动作：给出一句代表性指令交给 agent 执行 */
function quick(kind: '建群' | '任务') {
  if (kind === '建群') runCommand('新建一个商单合作协作群，拉入相关成员')
  else runCommand('汇总工作室的任务状态')
}

/** 卡片「前往频道」：跳到新建的频道 */
function goChannel(id: string) {
  router.push({ name: 'ops', params: { id } })
}

function onInput() {
  showSlash.value = text.value.startsWith('/')
}
function onBlur() {
  setTimeout(() => (showSlash.value = false), 200)
}
function pickCommand(cmd: string) {
  text.value = cmd + ' '
  showSlash.value = false
  nextTick(() => {
    const ta = document.querySelector<HTMLTextAreaElement>('.ai-panel textarea')
    ta?.focus()
  })
}
function insert(s: string) {
  text.value = (text.value + s).trim().length ? text.value + s : s
  if (s === '/') showSlash.value = true
  nextTick(() => {
    const ta = document.querySelector<HTMLTextAreaElement>('.ai-panel textarea')
    ta?.focus()
  })
}
</script>

<style scoped>
/* —— 快捷动作 —— */
.ai-quick { display: flex; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.ai-quick-chip {
  border: 1px solid var(--border);
  background: var(--bg-panel);
  color: var(--text-2);
  font-size: var(--fs-75);
  padding: 5px 11px;
  border-radius: 999px;
  cursor: pointer;
  transition: background 0.12s ease, border-color 0.12s ease, color 0.12s ease;
}
.ai-quick-chip:hover { background: var(--accent-soft); border-color: var(--accent); color: var(--accent); }

/* —— 对话流 —— */
.ai-convo { display: flex; flex-direction: column; gap: 12px; padding-top: 4px; }
.ai-msg { display: flex; flex-direction: column; gap: 8px; align-items: flex-start; }
.ai-msg.user { align-items: flex-end; }
.ai-bubble {
  max-width: 88%;
  font-size: var(--fs-100);
  line-height: 1.55;
  padding: 9px 12px;
  border-radius: 12px;
  background: var(--bg-soft);
  color: var(--text);
  white-space: pre-wrap;
}
.ai-msg.user .ai-bubble { background: var(--accent); color: #fff; }

/* —— 思考进度 —— */
.ai-thinking {
  display: flex;
  flex-direction: column;
  gap: 5px;
  padding: 11px 13px;
  border-radius: 12px;
  background: var(--bg-soft);
  border: 1px solid var(--border-soft);
}
/* Claude Code 式：等宽字体的工具调用流 */
.ai-thinking.tool { font-family: var(--font-mono, var(--mono, monospace)); }
.ai-think-step {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: var(--fs-75);
  color: var(--text-3);
  transition: color 0.2s ease;
}
.ai-think-step.done { color: var(--text-2); }
.ai-think-step.active { color: var(--text); font-weight: var(--fw-bold); }
.ai-think-ic {
  width: 14px; height: 14px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.ai-dot { font-size: 11px; line-height: 1; color: var(--ok, #6b8e4e); }
.ai-dot.pending { color: var(--border); }
.ai-spin {
  width: 11px; height: 11px;
  border: 2px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: ai-spin 0.7s linear infinite;
}
@keyframes ai-spin { to { transform: rotate(360deg); } }

/* —— 结果卡片 —— */
.ai-card {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 12px 14px;
  background: var(--bg-panel);
}
.ai-card-h { font-size: var(--fs-100); font-weight: var(--fw-bold); color: var(--text); }
.ai-card-sub { font-size: var(--fs-75); color: var(--text-3); margin-top: 2px; }
.ai-card-members { display: flex; flex-wrap: wrap; gap: 6px; margin: 10px 0; }

/* —— 建群提案：候选成员勾选 —— */
.ai-propose { display: flex; flex-direction: column; margin: 10px 0; }
.ai-cand {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 4px;
  border-bottom: 1px solid var(--border-soft);
  cursor: pointer;
  font-size: var(--fs-75);
}
.ai-cand:last-child { border-bottom: none; }
.ai-cand input { accent-color: var(--accent); cursor: pointer; }
.ai-cand-name { font-size: var(--fs-100); font-weight: var(--fw-bold); color: var(--text); }
.ai-cand-role {
  font-family: var(--mono);
  font-size: 10px;
  color: var(--text-3);
  background: var(--bg-soft);
  padding: 1px 6px;
  border-radius: 9px;
}
.ai-cand-reason { margin-left: auto; color: var(--text-3); }
.ai-cand.off .ai-cand-name { color: var(--text-3); font-weight: var(--fw-regular); }
.ai-cand.locked { cursor: default; }

.ai-card-actions { display: flex; gap: 8px; margin-top: 4px; }
.ai-card-btn.ghost { background: transparent; color: var(--text-2); border: 1px solid var(--border); }
.ai-card-btn.ghost:hover { background: var(--bg-soft); filter: none; }
.ai-card-done { font-size: var(--fs-75); color: var(--text-3); text-align: center; margin-top: 4px; }
.ai-chip-m {
  font-size: var(--fs-75);
  padding: 2px 9px;
  border-radius: 999px;
  background: var(--bg-soft);
  color: var(--text-2);
}
.ai-card-btn {
  border: none;
  background: var(--accent);
  color: #fff;
  font-size: var(--fs-75);
  font-weight: var(--fw-bold);
  padding: 6px 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: filter 0.12s ease;
}
.ai-card-btn:hover { filter: brightness(1.05); }

/* —— 任务状态表 —— */
.ai-task-table { width: 100%; border-collapse: collapse; margin-top: 10px; font-size: var(--fs-75); }
.ai-task-table th {
  text-align: center;
  color: var(--text-3);
  font-weight: var(--fw-regular);
  padding: 4px 6px;
  border-bottom: 1px solid var(--border);
}
.ai-task-table th:first-child { text-align: left; }
.ai-task-table td {
  text-align: center;
  padding: 5px 6px;
  border-bottom: 1px solid var(--border-soft);
  color: var(--text-2);
}
.ai-task-table td.nm { text-align: left; color: var(--text); font-weight: var(--fw-bold); white-space: nowrap; }
.ai-task-table td.over { color: var(--danger); font-weight: var(--fw-bold); }

.ai-card-btn.sm { padding: 4px 10px; font-size: 11px; margin-top: 8px; }

/* —— 承办 Agent 署名 —— */
.ai-by { display: inline-flex; align-items: center; gap: 7px; margin-bottom: 2px; }
.ai-by-ava {
  width: 18px; height: 18px; flex-shrink: 0; border-radius: 6px;
  background: var(--accent); color: #fff; font-size: 10px; font-weight: var(--fw-bold);
  display: inline-flex; align-items: center; justify-content: center;
}
.ai-by-tx { font-size: 11px; color: var(--text-3); }
.ai-by-tx b { color: var(--text-2); }

/* —— 全链路 AI / 真人 标签 —— */
.ai-plan-kind {
  font-size: 9px; font-weight: var(--fw-bold); padding: 0 5px; border-radius: 6px;
  margin: 0 2px; vertical-align: middle;
}
.ai-plan-kind.bot { color: var(--accent); background: var(--accent-soft, rgba(201,100,66,0.1)); }
.ai-plan-kind.human { color: var(--ok, #6b8e4e); background: rgba(107,142,78,0.12); }

/* —— 选题灵感 —— */
.ai-topics { display: flex; flex-direction: column; gap: 10px; margin-top: 10px; }
.ai-topic { border: 1px solid var(--border-soft); border-radius: 10px; padding: 10px 11px; background: var(--bg-soft); }
.ai-topic-top { display: flex; align-items: flex-start; gap: 8px; }
.ai-topic-rank {
  flex-shrink: 0; width: 18px; height: 18px; border-radius: 6px;
  background: var(--accent); color: #fff; font-size: 11px; font-weight: var(--fw-bold);
  display: inline-flex; align-items: center; justify-content: center;
}
.ai-topic-title { font-size: var(--fs-100); font-weight: var(--fw-bold); color: var(--text); line-height: 1.4; }
.ai-topic-meta { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; margin: 7px 0; }
.ai-tag { font-size: 10px; color: var(--text-2); background: var(--bg-panel); border: 1px solid var(--border-soft); padding: 1px 7px; border-radius: 8px; }
.ai-tag.plat { color: var(--accent); border-color: var(--accent); }
.ai-heat { display: inline-flex; align-items: center; gap: 5px; font-size: 10px; color: var(--text-3); margin-left: auto; }
.ai-heat-bar { display: inline-block; width: 42px; height: 5px; border-radius: 4px; background: var(--bg-code, var(--border)); overflow: hidden; }
.ai-heat-bar > i { display: block; height: 100%; background: linear-gradient(90deg, var(--accent), #e0915f); }
.ai-topic-hook { font-size: var(--fs-75); color: var(--text-3); line-height: 1.45; }

/* —— 指标行（分析 / 周报）—— */
.ai-metric-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin: 10px 0; }
.ai-metric { border: 1px solid var(--border-soft); border-radius: 9px; padding: 8px; background: var(--bg-soft); text-align: center; }
.ai-metric-v { font-family: var(--font-heading); font-size: var(--fs-200); font-weight: var(--fw-bold); color: var(--text); line-height: 1.1; }
.ai-metric-l { font-size: 10px; color: var(--text-3); margin-top: 2px; }
.ai-metric-d { font-size: 10px; font-weight: var(--fw-bold); margin-top: 3px; }
.ai-metric-d.up { color: var(--ok, #6b8e4e); }
.ai-metric-d.down { color: var(--danger, #c0563f); }

.ai-spark { width: 100%; height: 56px; margin: 4px 0 10px; display: block; }

.ai-findings { margin: 0; padding-left: 16px; display: flex; flex-direction: column; gap: 6px; }
.ai-findings li { font-size: var(--fs-75); color: var(--text-2); line-height: 1.5; }

/* —— 排期 —— */
.ai-sch-content { text-align: left !important; color: var(--text-2); }
.ai-status { font-size: 10px; color: var(--accent); background: var(--accent-soft, rgba(201,100,66,0.1)); padding: 1px 7px; border-radius: 8px; white-space: nowrap; }

/* —— 周报分节 —— */
.ai-report-sec { margin-top: 12px; }
.ai-report-t { font-size: var(--fs-75); font-weight: var(--fw-bold); color: var(--accent); margin-bottom: 4px; }
.ai-report-sec ul, .ai-plan-next ul { margin: 0; padding-left: 16px; display: flex; flex-direction: column; gap: 4px; }
.ai-report-sec li, .ai-plan-next li { font-size: var(--fs-75); color: var(--text-2); line-height: 1.5; }

/* —— 脚本 —— */
.ai-script-titles { margin: 10px 0; }
.ai-script-sub { font-size: 10px; color: var(--text-3); margin-bottom: 4px; }
.ai-script-title { font-size: var(--fs-75); color: var(--text); line-height: 1.6; }
.ai-shot-table td { text-align: left; vertical-align: top; }
.ai-shot-table td.nm { white-space: normal; }
.ai-shot-voice { color: var(--text-2); }
.ai-script-cta { font-size: var(--fs-75); color: var(--text-2); background: var(--bg-soft); border-radius: 8px; padding: 8px 10px; margin: 10px 0; line-height: 1.5; }

/* —— 开题问卷 —— */
/* —— Claude Code 式逐题反问 —— */
.ai-ask { display: flex; flex-direction: column; gap: 6px; width: 100%; font-family: var(--font-mono, var(--mono, monospace)); }
.ai-ask-answered {
  display: flex; align-items: center; gap: 7px;
  font-size: var(--fs-75); color: var(--text-3);
  padding: 1px 2px;
}
.ai-ask-done-ic { color: var(--ok, #6b8e4e); font-size: 10px; }
.ai-ask-q { color: var(--text-3); }
.ai-ask-a { color: var(--text); font-weight: var(--fw-bold); margin-left: auto; }

.ai-ask-box {
  border: 1px solid var(--accent);
  border-radius: 10px;
  padding: 10px 12px;
  background: var(--accent-soft, rgba(201, 100, 66, 0.06));
  margin-top: 2px;
}
.ai-ask-head { display: flex; align-items: center; gap: 7px; margin-bottom: 8px; }
.ai-ask-prompt { color: var(--accent); font-weight: var(--fw-bold); }
.ai-ask-title { font-size: var(--fs-100); font-weight: var(--fw-bold); color: var(--text); }
.ai-ask-step { margin-left: auto; font-size: 10px; color: var(--text-3); }
.ai-ask-tag {
  font-size: 10px; color: var(--accent);
  background: var(--accent-soft, rgba(201,100,66,0.1));
  padding: 1px 7px; border-radius: 6px; font-weight: var(--fw-bold);
}
.ai-ask-opt {
  display: flex; align-items: flex-start; gap: 8px; width: 100%;
  border: 1px solid transparent; background: transparent;
  padding: 6px 7px; border-radius: 7px;
  font-family: inherit; font-size: var(--fs-75); color: var(--text-2);
  cursor: pointer; text-align: left;
  transition: background 0.1s ease, color 0.1s ease, border-color 0.1s ease;
}
.ai-ask-cursor { color: transparent; font-weight: var(--fw-bold); width: 9px; flex-shrink: 0; margin-top: 1px; }
/* 单一光标：鼠标悬停 / ↑↓ 都落到 .active 这一行，高亮风格统一 */
.ai-ask-opt.active { background: var(--bg-panel); color: var(--text); border-color: var(--accent); }
.ai-ask-opt.active .ai-ask-cursor { color: var(--accent); }
.ai-ask-num {
  width: 16px; height: 16px; flex-shrink: 0; margin-top: 1px;
  border: 1px solid var(--border); border-radius: 4px;
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 10px; color: var(--text-3);
}
.ai-ask-opt.active .ai-ask-num { border-color: var(--accent); color: var(--accent); }
.ai-ask-opt-tx { flex: 1; }
.ai-ask-opt-bd { display: flex; flex-direction: column; gap: 1px; flex: 1; min-width: 0; }
.ai-ask-opt-desc { font-size: 10px; color: var(--text-3); line-height: 1.4; }
.ai-ask-opt.other { align-items: center; }
.ai-ask-other-btn {
  border: none; background: transparent; color: var(--text-3);
  font-family: inherit; font-size: var(--fs-75); cursor: pointer; padding: 0;
}
.ai-ask-other-btn:hover { color: var(--accent); }
.ai-ask-other-row { display: flex; align-items: center; gap: 6px; flex: 1; }
.ai-ask-other-input {
  flex: 1; border: 1px solid var(--accent); border-radius: 6px;
  padding: 4px 8px; font-family: inherit; font-size: var(--fs-75);
  color: var(--text); background: var(--bg); outline: none;
}
.ai-ask-other-go {
  border: none; background: var(--accent); color: #fff; cursor: pointer;
  border-radius: 6px; padding: 3px 9px; font-size: var(--fs-75);
}
.ai-ask-hint { font-size: 10px; color: var(--text-dim, var(--text-3)); margin-top: 8px; }

/* —— CLI 式输入框 —— */
.ai-input-box { position: relative; }
.ai-prompt-mark {
  position: absolute; left: 12px; top: 11px;
  font-family: var(--font-mono, var(--mono, monospace));
  color: var(--accent); font-weight: var(--fw-bold); pointer-events: none;
}
textarea.cli { font-family: var(--font-mono, var(--mono, monospace)); padding-left: 26px; }

/* —— 全链路方案 brief 标签 —— */
.ai-plan-brief { display: flex; flex-wrap: wrap; gap: 6px; margin: 10px 0 4px; }

/* —— 商单报价 —— */
.ai-deal-price { text-align: center; color: var(--accent); font-weight: var(--fw-bold); white-space: nowrap; }

/* —— 舆情回应草稿 —— */
.ai-crisis-draft {
  border: 1px solid var(--border-soft); border-left: 3px solid var(--accent);
  border-radius: 8px; padding: 10px 12px; margin: 10px 0; background: var(--bg-soft);
}
.ai-crisis-draft-t { font-size: var(--fs-75); font-weight: var(--fw-bold); color: var(--text); margin-bottom: 6px; }
.ai-crisis-draft p { font-size: var(--fs-75); color: var(--text-2); line-height: 1.55; margin: 0 0 5px; }
.ai-crisis-draft p:last-child { margin-bottom: 0; }

/* —— 全链路方案 —— */
.ai-plan-topic { font-size: var(--fs-100); font-weight: var(--fw-bold); color: var(--text); background: var(--accent-soft, rgba(201,100,66,0.1)); border-radius: 8px; padding: 8px 10px; margin: 10px 0; line-height: 1.4; }
.ai-plan-steps { display: flex; flex-direction: column; gap: 8px; }
.ai-plan-step { display: flex; gap: 9px; }
.ai-plan-n {
  flex-shrink: 0; width: 20px; height: 20px; border-radius: 50%;
  background: var(--text); color: #fff; font-size: 11px; font-weight: var(--fw-bold);
  display: inline-flex; align-items: center; justify-content: center;
}
.ai-plan-agent { font-size: var(--fs-75); font-weight: var(--fw-bold); color: var(--text); }
.ai-plan-task { font-weight: var(--fw-regular); color: var(--text-3); }
.ai-plan-out { font-size: var(--fs-75); color: var(--text-2); margin-top: 1px; }
.ai-plan-next { margin-top: 12px; }
</style>
