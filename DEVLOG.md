# CosMac OS — 开发日志 (Dev Log)

> 按时间倒序的开发流水：**每次 commit 前**在顶部加一条。
> 记「哪天 / 哪个模块 / 做了什么 / 关键决策与为什么」，不记文件级细节（那是 git log 的活），
> 也**不记敏感信息**（key/口令/线上 IP 进本机已 gitignore 的 `DEPLOY.md`）。
> 长期有用的事实进 memory；这里只是流水账。

---

## 2026-06-25 — 登录/注册去掉默认 admin
- 用户名输入框默认值从 `'admin'` 改空,占位文案「用户名（如 admin）」改「用户名」。避免新用户/注册时误带 admin。
- 验证:build(`index-DihDBZx8.js`)+ 本地 preview 确认输入框空。纯前端,**发 dist**。
- (邮箱注册+验证是另一档讨论中:需服务端 SMTP + 前端多步验证流,见对话。)

## 2026-06-25 — 鉴权页加「注册」（退出后可注册/登录）
- 需求:退出登录后只到登录页、没有注册入口;应是「注册 + 登录」界面。
- 加:① client.ts `register(baseUrl,user,password)`——走 Matrix 标准注册 + dummy UIA(开放注册无验证码场景);M_USER_IN_USE/M_FORBIDDEN/需额外验证 都给友好中文错误。② 登录页改成「登录/注册」分段切换:注册模式多「确认密码」(校验一致)、按钮「注册并进入」、底部互切链接。注册成功即登录→自动触发首次引导。
- 验证:`npm run build`(产物 `index-f7_AexYR.js`);本地 preview 截图确认两种模式 UI 正确(登录=用户名+密码;注册=多确认密码)。纯前端,**发 dist**。
- ⚠️ 依赖服务端:注册要 Synapse `enable_registration: true`,否则前端报「服务器未开放注册」。开放注册有刷号风险,建议配注册令牌/验证码(届时前端 register() 需扩展处理对应 UIA 步骤)。服务端开关细节记 DEPLOY.md。

## 2026-06-25 — 注册后「主 AI 问答」首次引导（前端脚本化向导）
- 需求:新用户注册后进设置界面,以主 AI 问答形式自定义工作区名(左上角)/初始频道/AI人设,而非直接进满是演示数据的界面。
- 机制(负责人定):**前端脚本化对话向导**(聊天 UI 按固定步骤问,像在跟中枢 AI 聊),答完直接调现有 Matrix 接口真建。零后端、可部署、可控;以后可升级接真 LLM。
- 步骤:选行业模板(影视/电商/自媒体/教育/通用,预填频道+AI人设)→ 工作区名 → 频道增删 → 主 AI 人设 → 确认 → 真建(createSpace+createChannelInSpace+setAiConfig)→ 标记完成 → 切进新工作区。
- 文件:`useOnboarding.ts`(状态机+聊天日志+建库逻辑)、`OnboardingWizard.vue`(全屏聊天式 UI)、`onboardingTemplates.ts`(行业模板)、client.ts `isOnboarded/setOnboarded`(account data `cosmac.onboarding` 标记首次)。
- 触发:首屏 sync 就绪后,**无引导记录 且 无任何工作区**才弹(双保险,不打扰已有频道的老用户);可「跳过」(也标记已引导)。
- 决策:① 首次标记用 account data(比"无工作区"可靠、每账号多端同步、零基建)。② AI 人设走控制室 setAiConfig 是管理员级——非管理员写失败时 try/catch 静默跳过,不阻断引导。③ 保留演示数据作样板(负责人定):新建工作区 id 不在 dashboardMap→看板仍回退演示图,作参考;左上角工作区名已随真实 Space 名自定义。
- 验证:`npm run build`(产物 `index-C0novC9i.js`)。引导在登录后/新账号触发,画面需负责人用新号眼验。纯前端,**发 dist**。

## 2026-06-25 — 社媒数据源「官方 API」按平台分别认证（修一刀切）
- 负责人指出:官方 API 不能用一个笼统「凭据名」字段——每个平台认证/要填的东西都不同。属实,之前是占位错误。
- 重做:加 `SOCIAL_API_SPECS` 准确规格表(每平台:是否真有可用公开指标 API / 申请门槛 / 该配哪些服务端 env 密钥 / 哪些非密定位参数 / 官方文档)。
  - YouTube=API Key+频道ID(门槛低);X=Bearer Token(付费)+用户名;Instagram=Graph长期令牌+商业号UserID(高门槛,个人号无API);Facebook=主页令牌+PageID;Threads=令牌+UserID。
  - TikTok/抖音/B站/微博/小红书=**无可用官方公开指标 API**→标记 supported:false,弹窗提示「请用爬取」,并自动把模式切到爬取。
- 弹窗按所选平台**动态渲染**:支持的平台显示「①服务端 env 配哪个密钥(前端不碰真值)+②非密参数输入」;不支持的显示警示。schema 把 `credName` 换成 `apiParams`(各平台非密参数)。
- 验证:`npm run build`(产物 `index-I78If7ok.js`)。纯前端,**发 dist**。

## 2026-06-25 — 社媒数据源 P1 微调：海外平台 + N8N/Coze 接法说明
- 平台列表海外优先:加 Instagram/TikTok/Facebook/Threads(YouTube/X 已有),国内(抖音/B站/小红书/微博)保留在后。
- 负责人要用 N8N/Coze 对接爬取。安全决策:**不在 social_sources 里直接粘 webhook URL**(URL/密钥含 token,会泄进 Matrix state event)——按铁律走「管理后台·工作流面板」建 N8N(webhook 类型)/Coze 连接器(URL+密钥进服务端 env),这里爬取模式只引用连接器 slug。弹窗加了指向工作流面板的醒目说明 + 字段改「连接器 slug」。
- 验证:`npm run build`(产物 `index-CCs2fl5d.js`)。纯前端,**发 dist**。

## 2026-06-25 — 数据看板「接入社媒数据源」P1（前端配置 UI）
- 需求:看板社媒数据要接真实源——配各平台账号 API,或挂 AI Agent 爬。要按钮 + 逻辑设计。
- **设计**(写进 CLAUDE.md 存储表):两种取数模式 api(官方平台 API)/crawl(AI Agent 走模块3 工作流爬公开主页);与工作流连接器同构——定义存控制室·按工作区 state event `cosmac.social_sources`,凭据只放「名」、真值进服务端 env `COSMAC_SOCIAL_*`;取回指标进 cosmac DB `cosmac_social_metric`。数据流:配置+env凭据 → bot 采集器(定时/手动) → API直调 或 run_workflow → 归一化写 DB → 新 REST 端点回看板。
- **本次落地 P1(纯前端、可交付)**:看板「社媒数据」组旁加 **🔌 接入数据源** 按钮 → 配置弹窗(`SocialSourceModal.vue` + `useSocialSources.ts` + client.ts get/setSocialSources)。可增删数据源:平台(抖音/B站/YouTube/小红书/微博/X)、账号、模式(api/crawl)、凭据名 或 工作流名、同步间隔、启用开关;按工作区存 `cosmac.social_sources`、多端同步。配置结构即最终版。
- **暂未接(P2~P4,标记清楚)**:后端采集器/真实调 API/AI 爬取/写 DB/看板读真值。弹窗「立即同步」先占位提示;凭据真值永不进前端。
- 关键决策:先交付配置 UI 把数据结构钉死,后端分期接(涉及平台开发者资质/爬取合规,需负责人定先接哪个平台)。建议 P2 先接 YouTube Data API(最开放)。
- 验证:`npm run build`(产物 `index-DqzQTPqI.js`)。弹窗在登录后看板可见,画面需负责人眼验。纯前端,**发 dist**。

## 2026-06-25 — 左侧栏新增「粉丝社区」分组
- 需求:侧栏现有「频道」「私信」两组,再加一个「粉丝社区」分组。
- 实现:纯前端名称启发式,零后端。房间名带 后援会/歌迷会/粉丝/应援/社区/fans 等关键词的归「粉丝社区」组,其余留「频道」组(`channelRooms`/`fanRooms` 两个 computed 从 `filteredRooms` 派生)。新组带独立折叠态 `fanCommunityOpen` + 「添加粉丝频道」入口(复用新建频道弹窗,名字带粉丝关键词即自动归此组)。
- 关键决策:先用名称归类(影视场景里后援会/歌迷会本就这么命名),够用且即时生效;以后要精确归类再改成读房间 cosmac.* 状态事件标签。
- 验证:`npm run build`(产物 `index-DmnjiiyT.js`)。侧栏在登录后显示,画面需负责人眼验。纯前端,**发 dist**。

## 2026-06-24 — 数据看板改回社媒数据（演示）+ 社媒/平台运营 KPI 混排
- 需求:数据看板应是社媒数据(粉丝增长、播放量等)。负责人拍板:**先用演示数据铺满**、KPI **社媒在上 + 平台运营在下 混排**。
- 恢复之前「去 Demo」时删掉的看板图表组件(从 git 历史捞回并精简,去掉无用的 chartId/chartFactories 依赖):`useChart.ts`、`PanelChart.vue`、`UnitGrid.vue`。
- 看板上排 📈 **社媒数据(演示)**:KPI=今日播放/全网粉丝/本周新增粉丝/平均互动率;图表=近24h播放趋势(LIVE)、各周新增粉丝、剧集/明星/平台状态网格、各平台粉丝分布饼图(数据全来自 `dashboards.ts` 占位值)。
- 下排 ⚙️ **平台运营(真实)**:会员/工作流/订单/知识库,来自后端 `getPlatformStats`,拿不到时整组不渲染。两组用带「演示/真实」角标的小标题分开,避免假数据被当真。
- 关键决策:社媒数字 CosMac 不拥有,本轮只铺演示值;待负责人定真实源(后台手填 / 平台 API)再替换。
- 验证:`npm run build`(vue-tsc 严格类型检查 + vite 均通过,产物 `index-Juf0E12I.js`)。看板在 Matrix 登录后才出现、连生产 hs,登录后画面需负责人自行眼验。纯前端,**发 dist**。

## 2026-06-24 — 安全与可靠性复查修复：AI 工具权限 / appservice 重试 / 工作流幂等
- 修复 AI 工具跨房间越权：模型显式传其它 `room_id` 时，先确认发起人也是目标房间 joined 成员；否则拒绝读成员/历史/代发消息。
- appservice 事务改为“任一事件异常即不标记 done”，让 Synapse 重试，避免单事件失败被整批确认后永久丢失。
- 工作流按 Matrix `event_id` 登记 `source_key`，提交外部平台前先 reserve；事务重放时复用已有 run，不重复提交/扣费。老 `cosmac_workflow_run` 表缺列时用非破坏性 ALTER 补 `token/source_key/status`。
- 前端 Matrix 首次同步增加 ERROR/STOPPED/15s 超时处理；退出登录改为尽力调用服务端 `logout()` 撤销 access token，再清本地会话。
- 验证：聚焦单测、ruff、前端 build 通过；完整单测需允许本机测试 HTTP server 绑定端口。

## 2026-06-23 — 任务看板加「项目/剧集进度」（参考演示版剧集 Tab，用真实数据）
- 需求:任务看板要有剧集进度,参考之前演示版的剧集 Tab。
- **零后端改动**:任务本就带 `goal`(拆解时的总目标,如"做一条爆款短视频")——这就是天然的"项目/剧集"分组维度。
- 前端:`projects` 按 `goal` 分组,算每个项目的完成度(已完成算100%、其余按各自 progress 平均);看板顶部加**项目进度条**(每个项目一张卡:名称 + 渐变进度条 + 完成数/总数 + %),点卡过滤下面看板到该项目,「全部项目」看全部。
- 验证:build(`index-Ch14waf_.js`)。纯前端,**发 dist**。
- 说明:分组按用户下达目标的原文。把目标说成剧集(如"《夜航星》第3集…拆任务")即按剧集分组。

## 2026-06-23 — 任务看板再美化 + 修两侧顶边
- create_tasks 已验证可用(现场拆出 编剧/分镜/配音 3 卡)。本轮纯视觉:
- **两侧顶边**:任务看板内容直接贴容器边。加 `.kan-wrap` 包一层(padding `var(--content-pad-x)`、max-width 1180 居中),与数据看板留白一致。
- **更好看**:列顶加 3px 主题色条 + 圆点(待办灰/进行中橙/已完成绿)、计数胶囊加粗;卡片圆角更大+悬停上浮高亮、负责人改成**彩色头像 chip**(首字圆形头像 + 角色名)、进度条改渐变、空态图标更大。
- 验证:build(`index-L0mO4Bp5.js`)。纯前端,**发 dist**。

## 2026-06-23 — 任务编排 P1 修复：create_tasks 没被启用 + 看板美化
- 现场实测"让 AI 拆任务"**没反应**。根因:后台 AI 配置存的 `enabled_tools` 是"勾选的工具名列表",`create_tasks` 是新加的、不在旧配置里 → 被当成"未勾选=禁用",AI 调不了它(前端工具目录也没它)。
- 修:`create_tasks` 列为 **always-on 核心工具**(`Toolbox._ALWAYS_ON`,不受后台工具开关约束)——这类核心、低风险工具新增后不该被旧配置一存就关掉。**无需重存配置即生效**。改了 2 个相关单测断言。
- **看板美化**:三列加主题色圆点(待办灰/进行中橙/已完成绿)、卡片加阴影+悬停、进度条、完成卡置灰划线、空态带图标。
- 验证:**195 单测过**、ruff、build(`index-BWIOfi5H.js`)。需发 dist + 重启 bot。重启后再让中枢 AI "拆成几个任务"应能上板。

## 2026-06-23 — AI 任务编排 P1：主 AI 拆任务 → 真实任务看板（Kanban + 手动改状态）
- 负责人定的任务看板新形态(AI 任务调度中枢)开工。**P1 地基**:主 AI 拆解目标→落库→真实看板→手动改状态。派发执行/结果回填(P2)后续。
- **后端**:`cosmac_task` 表 + `db/task_repo.py`(create/list/update)+ 主 AI 新工具 **`create_tasks`**(`ai/tools.py`,把目标拆成子任务、每条带负责人、写库)+ bot 端点 `GET /cosmac/tasks`、`POST /cosmac/tasks/update`(whoami 校验 + CORS)。
- **前端**:任务看板从影视流水线 mock 换成**真实 Kanban**(待办/进行中/已完成三列,读 `/cosmac/tasks`)+ 卡片按钮改状态(`updateTask`);数据看板"一句话下达目标"→中枢 AI→AI 调 `create_tasks`→任务出现在看板。
- 验证:加 任务流 用例(拆解工具→列表→改状态、done 自动补满进度、空标题丢弃、无 token 401);**195 单测过**、ruff、build 通过。需发 dist + 重启 bot。
- **遗留**:P2 做派发(发频道@人/交AI/跑工作流)+结果回填。
- (同日续)清掉 LiveView 里旧影视流水线 mock:productionTabs(三部剧假数据)+甘特图弹窗+任务详情弹窗+一堆 helper(mkStages/epTasks/activeProd/statusLabel…),约 140 行死 mock 删净;残留引用 0、build 通过(`index-BFCB3x2T.js`)。任务看板至此**全真实无 mock**。

## 2026-06-22 — 去 Demo（第3刀·收尾）：看板"一句话下达目标"接真实中枢 AI（方案A）
- 负责人"继续"→ 走方案 A：把看板招牌交互"一句话下达创意"从 mock(`CommandCenter`+`useAiAgent` 假卡片)改成**真的驱动中枢 AI**。
- LiveView 新增 `askFromBoard()`:输入 → 设 `aiDraft` + 打开中枢 AI 面板 + 复用真实 `aiSend()` 发给 bot 的 DM 房间,结果在右侧面板真实显示。删 `CommandCenter`,换成简洁 hero 输入框。
- 级联删 6 个死文件:`CommandCenter` + `useAiAgent`(大块 mock 卡片生成器) + `useAiPanel` + `data/command.ts` + `data/todos.ts` + `useLiveChannels`。
- **数据看板至此全真实**:品牌标题 + "一句话下达目标"(真 AI) + 4 张真实 KPI 卡。build 通过(`index-Dv4_56u-.js`)。纯前端,**发 dist**。
- 剩余 demo(独立任务,非看板):任务看板(`productionTabs` 内联 mock 剧集数据,要做需任务后端)、ProfileHome(个人主页=模块5)。业务图表如需回来再定数据源。

## 2026-06-22 — 去 Demo（第3刀·续）：移除看板影视业务假图表（方案C）
- 负责人"继续"→ 走方案 C（只留真实平台数据）。把看板里剩下的**影视业务假图表**全部移除:播放趋势/制作量双图(grid-2)、剧集列表 UnitGrid + 饼图(grid-3)、BizPanels——这些是 CosMac 不拥有的业务数据。
- 级联删 5 个死文件:`PanelChart/UnitGrid/BizPanels` 组件 + `useChart` + `data/charts.ts`（build 验证无 live 引用）。
- 现在数据看板 = 品牌标题 + AI 指令中枢(`CommandCenter`) + **4 张真实 KPI 卡**。干净、真实。
- build 通过(`index-B3fs1BNA.js`)。纯前端,**发 dist**。
- **剩最后一处看板 demo**:`CommandCenter`（"一句话下达创意"→出选题/脚本/方案卡，走 `useAiAgent` mock）。它是真·中枢 AI 侧栏的演示重复版。待负责人定:接真实 AI / 移除 / 保留。业务图表若要回来,定数据源(后台手填 or 外部API)。

## 2026-06-22 — 去 Demo（第3刀·起步）：数据看板 headline KPI 接真实平台数据
- 看板原来 4 个大数字是影视业务假数据(剧集播放/粉丝数/AI制作)——这些 CosMac 不拥有(要工作室填或接外部API)。先把它们换成 **CosMac 真正拥有的平台运营指标**。
- **后端** `GET /cosmac/stats`(带本人 token,whoami 校验)：付费会员/创作者数(控制室)+ 工作流运行/完成订单/知识库文档数(cosmac DB)。每项独立兜底,缺 DB 不报错;CORS 预检放行。
- **前端**：`getPlatformStats()` + 看板 headline KPI 改用 `boardKpis`(真实数据→「付费会员/工作流运行/完成订单/知识库文档」;没拿到时回退占位防空屏)。
- 验证：加 stats 端点用例;**194 单测过**、ruff、build(`index-CcOREdpx.js`)。需发 dist + 重启 bot。
- **诚实边界**：只换了 **headline KPI 4 卡**;看板下面的图表/单元格(播放趋势/剧集列表等)仍是占位——那些是**影视业务数据,CosMac 不拥有**。要真实化需负责人定数据源:① 后台手填业务数据 ② 接抖音/B站等外部 API ③ 砍掉只留平台运营数。

## 2026-06-22 — 去 Demo（第2刀）：清占位按钮 + 删更多死组件
- 续上一刀。本轮发现 TopBar/Composer/ChannelSidebar/PluginRail/WorkspaceRail/DepartmentCreateModal 等组件**也从不被 import**（orphan 扫描此前被 CSS/注释里的同名字符串误判成"还在用"）——它们携带的占位按钮随组件一并删除。
- 又删一批死组件/composable/data（级联孤儿，build 全程绿验证无 live 引用）：上述组件 + ToastHost/TopUserMenu/TopAppSwitcher/ChannelHeader/ChartCard/RichCard/DocPreview/ChannelTitleMenu/CCTVFrame + useComposerAi/useDepartmentCreate/useCardAction/useFocusMode + data/messages/{safety,ops,energy,office,duu}。
- **LiveView 里真·live 的占位按钮**：移除全局搜索框、提及、收藏、附件(×2)、表情、放大态"Cowork 风"演示左栏(模式切换/项目/产物/定时任务/派发/最近)——都未接后端、点了只弹"(演示)"。频道检索本就有左侧栏「查找频道」真功能,保留。
- **唯一保留的占位**：`ProfileHome.vue`(个人主页)——负责人要把它做成模块5,整面保留待重写,不在本轮动。
- 本轮共删 **27 个文件**;build 通过(`index-CyB2NomE.js`)。**需发 dist**(产物继续变小)。
- 至此 live 用户可见层除"个人主页(模块5)+数据看板/任务看板(mock数据待接真)"外,占位假按钮已清干净。

## 2026-06-22 — 去 Demo（第1刀）：删除死代码（演示稿 App.vue 整棵树 + 路由视图）
- 负责人要求"代码里不能有 demo、要真实落地"。第一步**清死代码**:本应用根是 `LiveView.vue`(main.ts 直挂)、不走 `<router-view>`,所以演示稿的 `App.vue` 整棵组件树 + 路由整页视图**从不渲染=死代码**。
- 删除 **18 个死文件**(build 验证全程绿,确认无 live 引用):`App.vue`、`AiChatPanel.vue`(demo AI 面板)、7 个路由视图(`DashboardView/SafetyView/EnergyView/OfficeView/DuuChatView/TodoView/OpsChannelView`)、及级联孤儿(`SystemAiModal/TypeOut/MessageStream/MessageItem/CardActionModal`、`useSystemAi/useDashboardDetail/useClock/useAutoHideScrollbar`)。
- `router/index.ts`:移除死视图 import,`/` 等路由改指 `Blank`(保持 hash 合法;只有 `name:'dashboard'` 被 live 代码引用,已保留)。
- **对用户零影响**(这些本就不渲染);纯清理代码里的 demo。build 通过(`index-Lu8l49N_.js`)。**需发 dist**(产物变小)。
- **下一步(去 demo 第2/3刀)**:① 清 live 组件里的占位按钮(TopBar/Composer/ChannelSidebar/ProfileHome 里点了弹"(演示)"的);② 把 live 的「数据看板/任务看板」从 mock 数据(`canvas/*`+`data/*`+`useAiAgent`)接真实数据。

## 2026-06-22 — 体验：中枢 AI 对话区自动滚到底部
- 反馈:在右侧真·中枢 AI 面板聊天时,bot 回复出现在视口下方、不自动滚动,要手动下拉才看得到。
- 修(`LiveView.vue`):给 `.ai-body` 加 ref,`watch(aiMsgs)` 来新消息 + `watch(aiOpen)` 打开面板时 `nextTick` 滚到底。沿用 `AiChatPanel.vue` 既有同款逻辑(`.ai-body` 本就 overflow-y:auto)。
- 验证:build 通过(`index-BnHEoYzu.js`)。纯前端,**发 dist** 即可。

## 2026-06-22 — 关键修复：会员 state_key 不能用 @user_id（Matrix 403 "set others state"）
- 现场实测「模拟支付」最终卡在开会员：bot 写 `cosmac.member@<room>` 403 `M_FORBIDDEN "You are not allowed to set others state"`。
- 根因:per-user 会员事件用了 **state_key = 用户 @id**。但 **Matrix 硬规则:state_key 以 `@` 开头的事件只有该用户本人能写**——bot(@guduu)/管理员根本无权给"别人"开会员。单测的假 client 没模拟这条规则,所以一直没暴露(我的疏漏)。**注:那套"已支付但开通失败→回滚订单"的保护真生效了,没产生扣款脏数据。**
- 修:state_key 改用**去掉开头 @** 的形式(`@a:host`→`a:host`),不触发该规则;真实 user_id 存进 `content.uid`,读取以 uid 为准(兼容旧数据 state_key)。前后端一致(`members.py` + `client.ts`)。同样修好了**管理后台给别的用户设会员等级**(之前也会 403)。
- 防回归:测试假 client 现在**模拟 Matrix 这条规则**(@开头 state_key 写入返 False),`test_plans_checkout_manual_grant`(支付给别人开会员)等用例据此校验。**全量 193 单测过**、ruff、build(`index-CCXR1XCG.js`)。
- 无需数据迁移:之前的 @key 写入全是 403 失败、没落任何脏数据。**需发 dist + 重启 bot。**

## 2026-06-22 — 模块4 修复：manual 回调缺 CORS 头导致前端 Failed to fetch
- 现场实测「模拟支付成功」报 `Failed to fetch`。根因:`/cosmac/pay/callback/<provider>` 的响应**漏了 CORS 头**(给 plans/checkout/me 都加了、唯独漏这个)。manual 测试通道是**浏览器**调的,响应无 `Access-Control-Allow-Origin` → 浏览器直接拦下、连状态码都读不到。
- 修:回调所有响应加 `cors=True`(真实渠道是服务端调用、带了也无害)。HTTP 集成测试补断言"回调响应带 CORS"防回归。
- 验证:`test_pay_http` 5 例过、ruff 过。**后端 only → 只重启 bot,不发 dist**。
- (注:修完后若点「模拟支付」显示"测试支付通道未开启",是 manual 默认禁用,需 `COSMAC_PAY_ALLOW_MANUAL=1`,与本 bug 无关。)

## 2026-06-22 — 模块4 P2b+：会员状态展示 + 端到端 HTTP 模拟测试（⚠️真实付款未测）
- 负责人定：暂不接 Stripe（账号未开），**先用 mock(manual)通道**跑通业务、继续开发，并**明确记录真实付款尚未测试**。
- **端到端 HTTP 模拟测试**（`test_pay_http.py`）：起真实 bot HTTP server，用 requests 打 `/cosmac/pay/*`，验证路由 / CORS 预检 / Authorization 头 / body 解析 / manual 回调分发全对。**证明 mock 链路 HTTP 层端到端跑通**。
- **会员状态展示**：新增 `GET /cosmac/pay/me`（带本人 token→当前生效等级+到期）；升级弹窗顶部显示"你当前是付费会员·到期X"，按钮按是否已会员显示「续费/升级」或「立即开通」，开通后刷新状态。
- 验证：**全量 193 单测过**（含 5 个 HTTP 集成）、ruff、build(`index-bt-Ew52q.js`)。需发 dist + 重启 bot。
- ⚠️ **真实付款测试状态（重要·待办）**：**从未做过任何真实支付渠道(Stripe/PayPal/USDT/支付宝/微信)的端到端测试**。当前唯一可用的"支付"是 manual 测试通道(HMAC 验签、不收款，默认禁用、需 `COSMAC_PAY_ALLOW_MANUAL=1` 才生效)。业务链(下单/幂等开通/续费顺延/到期)已单测+HTTP集成测试覆盖，但**钱真正怎么进来 = 未验证**。开通真实渠道后必须：① 实现对应 adapter 的 `create_checkout`/`parse_callback`(验签)；② test mode 端到端走一遍(下单→真支付→webhook→开会员)；③ 上线前关掉 manual 通道。

## 2026-06-22 — 模块4 P2b：用户侧「升级会员」打通(bot 支付端点 + 前端弹窗 + manual 端到端)
- 让顶栏「✦ 升级会员」真正能用。前端够不到 cosmac DB,所以走 bot 的 HTTP 端点:
- **bot 支付端点**(`appservice_bot.py`):`GET /cosmac/pay/plans`(公开读上架套餐)、`POST /cosmac/pay/checkout`(带用户 access token,bot `whoami` 验明身份→建订单→返回支付方式)、`POST /cosmac/pay/callback/<provider>`(平台验签→幂等开会员)。加 **CORS**(app.cosmac.cc→hs.cosmac.cc 跨源,含 OPTIONS 预检);复用既有 body 限长/超时/有界连接防护。
- **身份校验**:`matrix_client.whoami(token)` 用用户自己的 token 调 Synapse whoami 拿 user_id,只校验不存储。
- **安全闸**:manual(测试/线下确认)渠道**默认禁用**——回调返回 403,防任何人自助白嫖会员;测试整条链时临时设 `COSMAC_PAY_ALLOW_MANUAL=1`,**上线前务必关掉、改用真实渠道**。
- **前端**:`MembershipModal.vue`(套餐卡片+货币切换+下单+测试通道模拟支付+开通提示);`client.ts` 加 `payGetPlans/payCheckout/payManualConfirm`(fetch bot 端点、带 access token);顶栏「升级会员」从弹 toast 改成开这个弹窗。
- 验证:`test_members.py` 加 PayEndpoint 用例(公开读套餐/下单 whoami 校验/manual 默认403→开关后开通);**全量 188 单测过**、ruff、build(前端)通过。**后端+前端都改,需发 dist + 重启 bot**。
- **遗留/下一步**:① 要在后台先配至少一个套餐;② 测试 manual 通道要设 `COSMAC_PAY_ALLOW_MANUAL=1`;③ 确认 nginx 把 **`/cosmac/`(整段)** 代理给 bot(不只 `/cosmac/wf/`),否则 `/cosmac/pay/` 404;④ P2c 接 Stripe(test mode)替掉 manual。

## 2026-06-22 — 模块4 P2a：后台「会员套餐」配置页(写 cosmac.plans)
- 负责人指出"升级会员"该和支付一起做(对)。P2 拆三块,先做 P2a：管理员能配套餐(否则没东西可买)。
- **后台「会员套餐」页**(`AdminView.vue` 新 tab,💳)：套餐 CRUD——slug/名称/等级(付费/创作者)/有效期(天)/各币种价格/上下架。价格编辑用「元」、保存 ×100 转「分」存,展示再 /100。写控制室 `cosmac.plans` state event(bot 端 P1 的 `OrderService.list_plans` 已能读)。
- **数据层** `client.ts`：`getPlans/setPlans` + `PlanDef` + `PLAN_CURRENCIES`(USD/CNY/USDT)。getPlans **读失败抛异常**(404→[])、后台加载失败禁用新建/不渲染可编辑区,杜绝空列表覆盖真实套餐(同 gating 保护)。
- 架构说明(写进回复):前端是 Matrix 客户端、够不到 cosmac DB,所以购买流程(下单/支付)要走 bot 的 HTTP 端点——P2b 做(套餐列表公开读 + 下单 Matrix 鉴权 + 支付 webhook + 前端「升级会员」面板 + manual 渠道端到端),P2c 接 Stripe。
- 验证:client build 通过(`index-BlTrGUgp.js`);纯前端(后端 P1 已能读 plans)。**需发 dist**。

## 2026-06-22 — 模块4(交易系统·会员订阅)开工：P1 地基(支付抽象+订单+会员到期)
- 负责人拍板:主线=**会员订阅/充值**,多渠道(Stripe/PayPal/USDT/支付宝/微信)按 IP 地理路由,范围"较完整"。先落**与支付商无关的地基**(纯业务逻辑、mock 支付、单测验证,不需商户密钥):
- **套餐定义**:控制室 `cosmac.plans` state event(后台配,同 workflows/gating 套路);`trading/plans.py` 强校验解析(免费等级/无价/非正时长/重复 slug 全丢)。价格用最小货币单位整数(分)。
- **订单**:DB `cosmac_order`(`db/models.py` + `db/order_repo.py`);`mark_paid` 用原子 CAS(created→paid)做**恰好一次**闸,重复 webhook 不重复开通;开通失败可 `revert_to_created` 待重试,避免收钱没开会员。
- **支付抽象**:`trading/base.py` 的 `PaymentProvider`(create_checkout/parse_callback),像多模型 AI 那样可插拔各渠道;**密钥只进服务端 env**。P1 实现 `trading/manual.py`(HMAC 验签的手动/测试确认渠道)。
- **订单服务** `trading/service.py`:下单(校验套餐/货币/渠道→建单→出支付方式)+ 支付成功(幂等置 paid→开/续会员)。**续费从原到期日顺延**(还在有效期内续费不亏天数)。
- **会员到期**:扩 `members.py`——`grant` 带 `expires_ts`(0=永久)、新增 `active_tier`(到期回落免费)/`get_record`(续费取当前到期日);`get_tier`/`get_all` 全部到期感知。
- 验证:新增 `test_trading.py` 9 例(套餐解析/算价建单/开通到期/**幂等不重复续期**/**续费顺延**/手动验签);**全量 186 单测过**、ruff 通过。**纯后端地基、未接入 bot/HTTP 运行路径**,不改现网行为,无需部署(bot 下次重启 create_all 自动建 `cosmac_order` 表)。
- **下一步(P2)**:Stripe adapter(test mode)+ 公开 webhook 端点(验签→`on_payment_success`)+ 前端套餐页/下单/支付方式选择。需要负责人提供 Stripe 测试密钥。

## 2026-06-21 — 权限与工作流可靠性复查修复
- **门控 fail-closed + 退避**：控制室首次读取失败时临时收紧为仅管理员；已有成功缓存继续沿用。失败后短暂退避，避免 Synapse 故障时每条消息重复请求。
- **会员按用户拆分 state**：新写入改用 `cosmac.member`，以 user_id 为 state_key；旧 `cosmac.members` 聚合事件只读兼容，free tombstone 可覆盖旧记录。消除并发整表覆盖和单事件容量上限。
- **前端严格区分错误**：控制室别名只有 `M_NOT_FOUND` 才视为不存在；网络/权限错误向上抛。后台会员读取失败不再伪装成“全员免费”。
- **工作流可靠状态**：采用 `queued -> pending -> processing`。只安全回收未开始外呼的 queued；网络超时/5xx 保留 pending/token，避免平台已接单后诱导重试。pending 默认 7 天超时（`COSMAC_WF_CALLBACK_TIMEOUT` 可调），到期提示先核对外部平台。
- 验证：`ruff` 通过；CosMac 后端 **177 单测全过**；client build 通过（JS hash `index-BXhjDtJk.js`）。本次前后端均有改动，需部署 dist 并重启 `guduu-bot`。

## 2026-06-21 — 修复：管理后台「工作流」平台下拉框文字被竖直裁切
- 现象：工作流连接器表单里 `平台/请求方法/Dify应用类型` 等 select，选中项文字下半截被切掉。
- 根因：两套样式叠加打架——全局 `.cam-select` 给了**固定 `height:34px`**，而 `AdminView` 的 `.adm-form .adm-field select`(优先级更高)又把 `padding` 设成 `9px 11px`+`line-height:1.5`。34px 固定高 − 上下 18px 内边距 = 仅 16px 容文字 < 行高 ~21px → 裁切。
- 修法：给 `.adm-form .adm-field select` 加 `height:auto`(scoped 选择器优先级更高，覆盖固定高)，按内容自适应。只影响本表单，其它地方的 `.cam-select` 不动。**需部署前端 dist**（纯前端、无需重启 bot）。

## 2026-06-21 — 账号权限分层：功能门控（按会员等级限制能力，后台可配）
- 接上一条会员等级地基，做**功能门控**。负责人定调：后台加一个设置页，把现有功能都列进去**逐项人工配置**所需会员等级；以后新增功能也在后台目录里加。
- 机制（沿用全项目套路）：控制室 **state event `cosmac.gating`** 存「能力→最低门槛」，bot **服务端强制**（客户端只配置、挡不住绕过）。门槛 4 级阶梯 **免费 < 付费 < 创作者 < 仅平台管理员**；**平台管理员永远不受会员等级门控**（staff 用一切，免得给自己开会员），`仅平台管理员`门槛用于高危/共享付费凭据能力。
- 能力目录（`cosmac/members.py` GATE_CATALOG，前后端各一份）：`ai_chat` 基础AI对话、`knowledge` 知识库(RAG+命令)、`create_room` 建群/开专班、`workflow_run` 跑工作流。**默认**前三项免费(不限制)、`workflow_run`=仅管理员(**维持原行为、零回归**)。
- 强制点（bot）：① `ai_chat` 在对话回复入口(命令如 会员/技能/知识/工作流不受影响、保证随时能查/升级)；② `knowledge` 在知识命令 + RAG 注入；③ `create_room` 在「建专班」命令 + create_room 工具；④ `workflow_run` 在「工作流 跑」命令 + run_workflow 工具。**工具层也堵**：Toolbox 加 `gate_check` 钩子，防「让 AI 帮我建群/跑工作流」绕过命令门控。
- 后台 UI：AdminView 新增「🔐 会员权限」tab，一张表逐项下拉选门槛，写 `cosmac.gating`。
- 验证：`test_members.py` 增门控测试(阶梯/解析/Store/裁决/工具映射/命令门控)，全模块 170 例过、ruff 干净；前端 `vue-tsc` 严格类型检查 + build 通过、preview 加载无 console 错误（后台交互需登录态 Synapse，未现场点测）。**需部署前端 dist**。

## 2026-06-21 — 账号权限分层：会员等级（免费/付费/创作者）地基
- 需求：在「服务器管理员」之外，给普通用户叠一层**会员身份**：免费 / 付费 / 创作者会员。负责人拍板的关键决策：
  - **靠购买获得**，后台也能**手动调整**；本期先做地基 + 后台调整，**购买预留接口**（真实支付是模块4，未开工，不做假支付）。
  - 存控制室 **state event `cosmac.members`**（与 `cosmac.ctrl.admins` 等同套路：管理员浏览器写、bot 读；权威数据、用户不可自改，付费门槛才靠得住）。
  - **管理员身份独立于会员等级**（正交）——管理员仍走 Synapse admin 标志，会员等级是另一维。
- 实现：
  - 后端：新建 `cosmac/members.py`（等级枚举/标签/校验 + `MembersStore` 读写控制室 + `grant` 预留授予入口）；`config.py` 加 `MEMBERS_EVENT_TYPE`；`matrix_client.py` 加通用 `set_state_event`；`appservice_bot.py` 加「会员」命令（人人可查自己 `会员`/`我的会员`；平台管理员可 `会员 列表/设置/撤销`）+ `grant_member_tier`（**预留给模块4支付**，source=purchase）。
  - 前端：`client.ts` 加 `MEMBER_TIERS/getMembers/setMemberTier/memberTierLabel`；`AdminView.vue` 用户表加「会员等级」列（行内下拉即时调整，乐观更新+失败回滚，付费/创作者带强调色）。
- **已知边界**：appservice 命名空间是 `@guduu.*`，bot 无法代写普通用户 account data，故普通用户查自己等级走「DM 问 bot」而非个人主页徽章（个人主页徽章需另建读路径，按需再补）。门控（不同等级能用哪些功能）本期不做。
- 验证：新增 `test_members.py` 15 例全过；后端全量 160 例过、ruff 干净；前端 `vue-tsc` 严格类型检查 + build 通过，preview 加载无 console 错误（管理后台交互需登录态 Synapse，未现场点测）。**需部署前端 dist**。

## 2026-06-21 — 会员/门控 收口（评审5项）：读失败不清空/门控不失效开放/启动不误杀/文档同步
- 评审命中模块4预热(会员/门控)的几处真 bug，修掉 4 项真·廉价正确的，第 5 项(单 state event)记为模块4正式开工时做的架构边界：
- **#2【P1 读失败清空其他会员】**：`grant()` 用会吞异常的 `get_all()` 读当前 map，瞬时读失败→空表→写回**清空所有其他会员**。修：新增 `_read_all_strict`(404→空合法、瞬时错→抛)，grant **读失败即放弃写入**。前端 `setMemberTier` 同理：区分 `M_NOT_FOUND`(从空开始) vs 瞬时失败(抛错中止)。
- **#3【P1 门控首读失败失效开放】**：bot 无缓存时读失败→回落默认(AI/知识库/建群默认免费)→管理员配的付费门控被绕过。修：读失败**不刷新 cache_ts**(下次立即重试，不把失败缓存一个 TTL) + 启动 `gating.warm()` 预热把窗口压到极小。前端 `getGating` 读失败**抛异常**(不再伪装默认)，后台加载失败则**禁用保存 + 显示错误态**，杜绝"默认值覆盖真实策略"。
- **#1【P1 启动恢复误杀在跑的异步任务】**：`reclaim_orphans` 无条件把全部 pending 标 error+清 token，但 webhook 可能已提交成功、外部仍在跑会回调→误杀+用户重试双扣费。修：加**1h 宽限期**，只回收久未更新的遗孤，新近 pending 留着等回调正常完成。
- **#5【P2 AGENTS.md 未同步】**：同步 AGENTS.md+CLAUDE.md 路线图——模块3 标 ✅、模块4 标「⬜ 预热」(会员/门控地基已立，本体未做)。
- **#4【P2 全部会员存单个 state event】**：读改写后写覆盖前写、量大碰事件大小上限。**#2 的 abort-on-read-failure 已堵住数据丢失**；并发/容量属架构层，**记为模块4正式开工时迁「每用户独立 state key 或 DB」**(已写进路线图「已知边界」)。
- 验证：加 读失败不覆盖/门控重试/warm/启动宽限期 等用例；**175 单测全过**、ruff、build(`index-CFHDiDiH.js`)通过。**需部署 dist + restart guduu-bot**。

## 2026-06-21 — 品牌化清理（R·彻底清除 demo 人设"筱雨" + Matrix/Synapse 复查）
- 负责人改定：**全删 筱雨 demo**。把全客户端 ~60 处硬编码"筱雨"统一脚本重命名为真实租户 **安其/安其影视工作室**（保留 demo 结构、避免删数组破坏 fallback 渲染；真实后端下这些 mock 本就不显示）：
  - `筱雨中枢 AI→安其中枢 AI`、`筱雨工作室→安其影视工作室`、`筱雨-MBP→安其-MBP`、人名 `筱雨→安其`、头像 `雨→安`。
  - 覆盖 `useAiAgent`(演示团队/派单/卡片)、`data/messages/*`(模拟聊天)、`data/channels|todos|dashboards|pluginStore`、`useCli|useCardAction|useDashboardDetail|useChannelAdmin`、`SystemAiModal|AiChatPanel`、注释与 CSS。grep 复核 **0 处筱雨残留**。
- **Matrix/Synapse 复查**：客户端 70 处命中，分类后——**55 处是协议/SDK/内部标识**(`matrix-js-sdk`/`/_matrix`/`/_synapse`/`m.room.*`/`MatrixClient`/`.well-known`，① 协议层+③ 内部，**绝不能改**)，**15 处是开发者代码注释**(准确描述"接 Matrix/Synapse 真后端"，非用户可见、§7 ② 不含注释)。**用户可见层 0 处 Matrix/Synapse 泄漏**（已在上一刀清掉）。结论：保留这两类是对的，强行改注释/SDK 反而错。
- 验证：client build 通过（新 hash `index-CZ4rOlxp.js`）；纯字符串重命名。**需部署前端 dist**。

## 2026-06-21 — 品牌化清理（R·demo 人设"筱雨"残留→tenant 配置，只修常显文案）
- 发现 demo 人设"筱雨工作室"半迁移：`tenant.ts` 已配真实租户**安其影视工作室**（且其 docstring 明令"不可在源码写死主理人标识"），但 ~20 处仍写死"筱雨"。负责人拍板**只修常显文案**（任何后端下都显示的地方），demo/mock 数据保留作示意。
- 改（路由到 tenant 配置，符合换皮设计）：
  - `useCustomAssets.ts`：建 Agent/工作流的**表单占位符** + 默认种子资产"你是筱雨工作室的…"→`${tenant.name}`、"通知筱雨确认"→`${tenant.shortName}`（导入 tenant）。
  - `useSystemAi.ts`：中枢 AI 默认名"筱雨中枢 AI"→`${tenant.shortName}中枢 AI`；默认 prompt"经筱雨确认"→`${tenant.shortName}`。
  - `useChannelAdmin.ts`：频道默认 AI prompt"经筱雨确认"→`${tenant.shortName}`。
  - `AiChatPanel.vue`：AI 头像 `alt="筱雨工作室"`→`中枢 AI`。
- **保留**（demo/mock 示意数据，真实后端下不显示）：`useAiAgent` 演示团队(老周/阿杰/小鹿/筱雨)与派单消息、`useCli` 筱雨-MBP、`data/messages/*` 模拟聊天、mock 成员/卡片/待办。
- 验证：client build 通过（新 hash `index-BLY_ujTj.js`）；纯静态配置/文案改动。**需部署前端 dist**。

## 2026-06-21 — 品牌化清理（R·呈现层去 Matrix/Synapse 字样）
- 按 §7 三层红线，**只改 ② 呈现层**（用户/管理员可见字样），不碰 ① 协议层、③ 内部标识符：
- 核对后发现主品牌面**已全是 CosMac Star**（登录页/顶栏/中枢AI/页面标题），唯一残留 `guduu` 是 `BOT_LOCALPART='guduu'`（bot 账号身份，负责人已决定不迁移）→ 保留。
- 清掉**面向用户的技术品牌词**：频道成员帮助文案去掉"来自 Matrix/标准 Matrix 邀请/kick"→中性表达；成员管理提示"Synapse Admin API 不对外开放"→"后端管理接口"；数据概览"数据来自 Synapse Admin API"→"服务器管理接口"；恢复账号密码提示"Synapse 要求"→"服务器要求"；AI/工作流密钥说明里"Matrix 事件无法加密/不进网页Matrix"→"平台事件/聊天数据"。
- **刻意保留**：`/_synapse/admin`、`/_matrix/...` 等**字面协议路径**（① 不改，且管理员配 nginx CORS 时真要用到）；开发者代码注释里准确描述 Matrix/Synapse 技术栈的字样（非用户可见，不属 ②）。
- 验证：client build 通过（新 hash `index-DnhZRWB9.js`）；纯静态文案改动、无逻辑。**需部署前端 dist**。

## 2026-06-21 — 模块3（工作流引擎）收尾打 ✅
- 核对全链路后确认**模块3已功能完整**，最后一块"后台编排 UI"其实早在前几轮就建好了：
- **后台编排 UI**（`AdminView.vue` 工作流面板）：4 平台（webhook/Dify/Coze/ComfyUI）连接器的列表/新建/编辑/启停/删除；平台相关字段按需显隐（webhook 的 method+async / Dify 的 mode / Coze 的 ref_id / ComfyUI 的 graph）；凭据**只填名**（真值在服务端 env `COSMAC_WF_<CRED>`，不进网页/Matrix）；保存写控制室 `cosmac.workflows` state event。
- **全链路自洽**：UI→`setWorkflows`→控制室 state event→bot 读(`appservice_bot.py` get_state_event)→`run_connector` 按平台分发（wf.py 消费 mode/input_key/ref_id/graph，键名与 `WorkflowDef` 完全对齐）。
- 至此模块3全件齐活：引擎(4平台)+聊天命令+`run_workflow`工具+异步回调+运行记录+后台UI+安全(够用即止)。durable队列/fencing/精确一次=已知边界本期不做。
- 验证：代码层核对全链路键名一致 + client build 通过；UI 是前几轮已提交进 dist 的产物，本次**无代码改动**（仅文档），**无需部署**。增强项(更多适配器/graph 上传)按需再补。

## 2026-06-19 — 工作流安全（收口·只做零downside的对的修法 + 架构边界说清楚）
- 评审又报 5 项。其中 3 项是真·廉价正确修法，已做；另 2 项（durable队列/多实例fencing）是**架构级**、单实例下属过度设计，已在回复里和负责人确认停止线，不再无限打补丁：
- **#1【P1 内存LRU提前标完成】**：`_remember_txn` 原在处理**前**写入→处理途中重试命中内存快路回200，原处理若崩 DB 的 processing 再没机会重抢→永久丢。修：移到 `_finish_txn` **之后**，内存只记真正处理完的。
- **#2【P1 后台任务不抗重启】**：进程内线程池不跨重启，async 运行会永久停在 pending。修（可见性，非恢复执行）：启动时 `reclaim_orphans` 把遗留 pending/processing 结清为 error 并通知群"因重启中断、请重试"。真正的不丢任务需 durable 队列（见架构说明，本期不做）。
- **#3【P1 无并发连接上限】**：ThreadingHTTPServer 每连接一线程，洪泛仍能堆线程。修：`_BoundedThreadingHTTPServer` 用 BoundedSemaphore(128) 卡并发连接，超限直接关连接不开线程。
- **#4（多实例 fencing）/#5（单事件异常整批仍done）**：单实例部署下 #4 的"另一实例重抢"不会发生；#5 的"重试整批"会重新触发已成功的付费工作流，真正修需 per-event 幂等键——两者都属 durable/exactly-once 架构，单bot小规模属过度设计，**记为已知边界**。
- 验证：加 启动结清中断运行 用例；**145 单测全过**、ruff 通过。纯后端，仅 `restart guduu-bot`。

## 2026-06-19 — 工作流安全（四收口·这次动真格的并发/时限语义）：绝对时限 / 原子抢占 / 崩溃不丢 / 回调400 / 三池
- 上一轮的修法被指出**仍可绕过**，这次从语义层重做：
- **#1【P1 Slowloris 仍可绕过】**：`socket timeout` 只约束单次 recv，攻击者每 19s 挤一字节即不断重置 20s 计时器，请求行/头/体都能被无限拖住。修：新增 `_DeadlineSocket` 包住读端 socket，把**整次请求的绝对时限下沉到每次 recv**（每次读前把超时设为"距 deadline 的剩余时间"，随墙钟单调缩到 0，与对端是否还发字节无关）；在 `setup()` 装一处即覆盖请求行+头+体。
- **#2【P1 持久去重非原子】**：先 `txn_seen()` 再 `mark_txn()`，并发同 txn 都查不到→各自处理→双触发付费。修：`claim_txn` 改**一次原子写决定归属**——新事务原子 INSERT(主键冲突即让位)、processing 残留用带条件 UPDATE+rowcount 抢占。
- **#3【P1 先标记后处理永久丢】**：标记 done 后、处理前崩溃 → 重试被当已完成跳过 → 整批永久丢。修：两阶段 `processing→done`，崩在中途留 processing，过期(`_STALE_SECONDS`)后可被重新抢占(at-least-once)；do_PUT 对 INFLIGHT 回 **503 让 Synapse 重试**，不再无条件 200。
- **#4【P2 非法回调 JSON 当成功】**：JSON 解析失败用 `{}` → 发"无内容"并结清 → 平台收 200 无法重投。修：解析失败/非对象 → 回 **400 且不动 pending**。
- **#5【P2 异步提交与快任务共池】**：提交仍排在 webhook/Dify/Coze 后。修：拆 **submit/fast/slow 三池**，异步"提交"独占 submit 池绝不被堵。
- 附：`cosmac_seen_txn` 加 `done`/`claimed_at` 列；无 alembic，新增 `_heal_ephemeral_schema` 对这张**7天TTL缓存表**做自愈(老库缺列→DROP重建，仅限缓存表)，prod 重启即生效。
- 验证：加 原子抢占/过期重抢/跨重启识别/schema自愈/async非webhook/提交异常结清 等用例；**144 单测全过**、ruff、build 通过。
- 部署：**纯后端**(无前端改动，dist 不变) → 仅 `restart guduu-bot`，无需发 dist。

## 2026-06-19 — 工作流安全（再再收口）：Slowloris / 事务去重持久化 / 异步只限webhook / 提交异常结清 / 双池
- **#1【P1 Slowloris 打满线程】**：ThreadingHTTPServer 每请求开线程，回调按 Content-Length 阻塞读、无 socket/read deadline——攻击者慢发/不发正文即占住线程，512KB 上限无效。修：Handler 设 `timeout=20`（socket 级超时）+ 新增 `_read_body` **按总时限分块读**（慢速 drip 也被 deadline 卡死），回调和事务端点都用，超时回 408。
- **#2【P1 事务去重只在内存】**：`_seen_txns` 重启即丢→Synapse 重放可再触发付费工作流，且无限增长。修：内存改**有界 LRU**(4096)；新增 `cosmac_seen_txn` 表 + `db/dedup.py`，**先记后处理**（at-most-once）持久化去重，重启后识别重放；DB 不可用则退回内存（不阻断收消息）。
- **#3【P2 非 webhook 被存为异步】**：切到 Dify/Coze/ComfyUI 时 async 复选框隐藏但值没清→后端挂永远等不到回调的 pending。修：前端保存时 `platform!=webhook` 强制 `async=false`；后端 `supports_async_callback` 双保险（只 webhook 走回调，其余即便 async=true 也按后台跑）。
- **#4【P2 异步提交异常留永久 pending】**：`_submit` 捕获异常只记日志，不结清/通知。修：异常也 `complete_run(error)` + 通知群。
- **#5【P2 单池队头阻塞】**：4 个长 ComfyUI 占满 worker，异步 webhook 的"提交"只能排队。修：拆 **fast/slow 两个池**——ComfyUI 走 slow，提交/快连接器走 fast，互不堵。
- 验证：加 持久化去重/LRU上界/async非webhook不挂pending/提交异常结清 等用例；cosmac **141 单测全过**、ruff、build 通过。
- 部署：改了 `cosmac/`+前端 → 发 dist + `restart guduu-bot`。⚠️ 建议 nginx 给回调端点也加 `limit_req`/`limit_conn`（应用层挡住单连接慢占线程，海量连接仍靠网关限流）。

## 2026-06-19 — 工作流模块**彻底自审**（主动一次挖完，不再被动挤牙膏）
- 不再等审查工具一批批喂：把整个工作流链路（HTTP 入口 + 鉴权 + 回调 + 后台池 + 4 连接器 + 凭据 + DB）系统性对抗性过了一遍。结论 + 这次主动补的：
- **自审确认无问题的**：① 全工作流外呼**只此 `wf.py` 一处**（grep 确认无散落的 requests 调用），SSRF/凭据绑定/响应限流覆盖完整；② 无死代码（`_sender_can_run_workflow` 已清）；③ gzip 解压炸弹被 `_fetch` 的**累计字节封顶**接住（cap 在解压后字节上）；④ 凭据/密钥无日志泄露；⑤ ComfyUI 图注入已 json 转义、图数/单图都限。
- **主动补的 2 处**：
  - **`_check_auth` 改常数时间比较**（`hmac.compare_digest`）：原 `==` 比 hs_token 有时序侧信道，可被逐字节猜。
  - **事务端点 `do_PUT` 也限请求体**（≤8MB、拒负数/非法 Content-Length）：和回调端点对齐，纵深防御 + 防 `int()` 崩。
- **一个明确的已知残留（暂不修，记着）**：SSRF 的 **DNS-rebinding** 窗口——`getaddrinfo` 校验与 `requests` 实连各解析一次。彻底修需把校验过的 IP 钉死再连（涉及 TLS SNI/证书，改动大、边界多）。实际利用门槛高（需控 DNS + 卡请求窗口重绑），当前挡住所有直球 SSRF。
- 验证：cosmac **137 单测全过**、ruff、build 通过。纯后端 → `restart guduu-bot`。

## 2026-06-19 — 工作流安全（封口）：AI工具异步协议 / 内网开关收紧 / 提交全后台 / 回调幂等txn / 消息截断
- 又 5 个边界，修完：
- **#1【P1 AI 工具不支持异步协议】**：工具把所有连接器当普通后台任务，async=true 也不生成 callback——自然语言触发的异步工作流收不到回调。Toolbox 加 `dispatch_async` 钩子（bot 注入 `_dispatch_async`），async 连接器经工具也走"登记 pending+回调地址"。
- **#2【P1 内网开关放公网明文】**：`COSMAC_WF_ALLOW_INTERNAL=1` 后只校验域名匹配，公网 HTTP 也能带 Bearer。改成：开关放行 HTTP 还要**解析 IP 确属私网/环回**(`_host_is_internal`)，公网即使开开关也强制 HTTPS。
- **#3【P2 异步提交仍阻塞事务】**：`_dispatch_async` 同步调 webhook 提交(可能 30s)。改成登记 pending 后**提交也进后台池**、立即返回；提交失败后台结清 + 通知群。
- **#4【P2 崩溃恢复重复发】**：Matrix 消息发出后、complete_run 前崩溃，5 分钟后重发——`send_text` 每次新 txn id、Matrix 去不了重。改成回调消息用**固定 txn id `cosmac-wf-<run_id>`**，Synapse 据此去重。
- **#5【P2 大结果无限重试】**：回调体 512KB 但消息正文没截断，超 Matrix 事件大小→send 持续失败→无限回 pending。消息正文按 4000 字截断（完整结果在 DB run 记录）。
- 验证：加 AI工具异步分派 / 公网HTTP拒绝 / 环回放行 等用例；cosmac **137 单测全过**、ruff、build 通过。纯后端 → `restart guduu-bot`。

## 2026-06-19 — 工作流安全（再收口）：AI工具全后台 / processing不卡死 / 凭据强制HTTPS / 整体deadline / 轮询异常接住
- 又一轮复查的 5 个异常路径，全修 + 补测试：
- **#1【P1 AI 工具未全后台】**：`run_workflow` 工具之前只后台化 ComfyUI，webhook/dify/coze 仍同步阻塞 Agent+事务。改成**所有连接器都进有界后台池**、立即返回"已开始"、跑完发回群。
- **#2【P1 回调永久卡 processing】**：抢占成 processing 后若 `send_text` 抛异常/DB 失败/进程重启，只回 500、不恢复 pending，重试得 404、结果永久丢。修：① `send_text` 包 try/except，失败（抛或假值）都回滚 pending；② `claim_pending` 支持**重抢卡死(processing 超 5 分钟)的运行**（崩溃恢复），并显式刷新 updated_at 防刚抢的被立刻重抢；③ 已 ok/error 的回调幂等返回 200。
- **#3【P1 凭据走明文 HTTP】**：`credential_for` 只校验了域名、没要求 HTTPS——Bearer 可能被网络窃听。改成**带密钥必须 HTTPS**，内网 HTTP 须显式 `COSMAC_WF_ALLOW_INTERNAL=1`。
- **#4【P2 流式无整体时限】**：`requests timeout` 只管单次读；慢速持续小块发送能长期占住 worker。`_fetch` 加**整体 deadline**（总读时长 ≤ timeout），超了掐断回收。
- **#5【P2 ComfyUI 轮询静默失败】**：`_comfy_poll` 只接 `RequestException`，`_fetch` 抛的 `_TooBig` 会冒泡成静默失败。改成一并接住、当一次失败轮询、优雅超时。
- 验证：加 凭据明文HTTP拒绝 / 卡死可重抢 / 重放幂等 / AI工具全后台 等用例；cosmac **135 单测全过**、ruff、build 通过。纯后端 → `restart guduu-bot`。

## 2026-06-19 — 工作流安全（深修·收口）：凭据域名绑定 + token 离开 URL + 原子回调 + 全后台 + 响应限流
- 再一轮复查抓出的 5 个更深残留，一次修到底：
- **#1【P1 凭据可被导出】**：管理员能把任意 cred 绑到自己控制的公网 URL，SSRF 只挡内网、不挡公网，服务端就把 Bearer 密钥发过去了。新增 `credential_for(cred,url)`：密钥的**允许域名也由服务端 env 固定**(`COSMAC_WF_<CRED>_HOST`)——未绑定或 URL 主机不匹配则**拒绝外发密钥**。webhook/dify/coze/comfyui 四连接器都走它。
- **#2【P2 token 仍在 URL】**：路径段也进 nginx 日志。改成回调 URL **完全不含 token**；token 放进我们 POST 给平台的 payload(`callback_token`)，平台回传 `X-Cosmac-Token` 头鉴权——token 不进任何 URL。DB 仍只存哈希、单次用完即废。
- **#3【P2 并发回调重复发】**：两个回调能同时读到 pending 各发一遍。`wf_repo.claim_pending` 用 `UPDATE...WHERE status='pending'` **原子 CAS** 抢占成 processing，只有一个成功，其余幂等返回 200。
- **#4【P2 同步连接器阻塞事务】**：上次只把 ComfyUI 放后台。改成**所有同步连接器**(webhook/dify/coze≤30s 也算)都进有界后台池，立即返回"已开始"、跑完发回群。
- **#5【P2 响应无大小限制】**：新增 `_fetch`(`stream=True` + 累计字节封顶 + 看 Content-Length)，普通响应 ≤2MB、ComfyUI 单图 ≤16MB，超限拒绝。四连接器全部响应读取都过它。
- 验证：`test_wf` 加凭据未绑定/域名不匹配用例、`test_wf_cmd` 加原子抢占/后台结果/token 离开 URL 用例；cosmac **133 单测全过**、ruff、build 通过。
- 部署：纯后端 → `restart guduu-bot`。⚠️ **破坏性**：带凭据的连接器现在**必须**在服务端配 `COSMAC_WF_<CRED>_HOST=<允许域名>`，否则拒绝外发密钥（安全要求）。

## 2026-06-19 — 工作流安全（补漏）：复查抓出的 6 个绕过/残留全修
- 上一轮修复有真实漏洞，逐个补：
- **#1【P1 DM 绕过越权】**：上次"群里要管理员、DM 放行"——任何人和 bot 开个两人 DM 就能跑全部共享凭据/付费工作流。改成**只许平台管理员**(控制室 power≥50)触发，**不分 DM/群**（新增 `_is_platform_admin`，聊天命令 + AI 工具两路都换）。
- **#2【P1 ComfyUI 重定向绕 SSRF】**：上次只给 webhook/dify/coze 加了 `allow_redirects=False`，ComfyUI 的提交/轮询/下载三处漏了——补齐。
- **#3【P1 回调 DoS 负数绕过】**：`Content-Length:-1` 不命中上限、`read(-1)` 读到 EOF（无界），非整数还抛 ValueError。改成 `0≤length≤512KB`、解析异常一律拒。
- **#4【P2 token 仍进 URL】**：生成的回调地址从 `?token=` 查询参数改成**路径段** `/callback/<id>/<token>`（能配头的平台改发 `X-Cosmac-Token`、token 完全不进 URL）；DB 仍只存哈希。
- **#5【P2 后台无并发限制】**：每次 ComfyUI 都新建 daemon 线程→可无限堆。改用 `wf.submit_background` 的**有界线程池**(4 并发/12 在途上限)，满了拒绝并提示"系统繁忙"。
- **#6【P2 回调先结清后发消息】**：发消息失败时 run 已完成、token 已清，平台重试得 404、结果永久丢。改成**先发、确认发出去了再结清**；发失败回 500、保持 pending 等重试。
- 验证：`test_wf_cmd` 加越权(不分 DM)/token 路径/回调发失败保持 pending 用例；cosmac **130 单测全过**、ruff 通过。纯后端 → `restart guduu-bot`。

## 2026-06-19 — 工作流安全（下）：越权/DoS/回调token/同步阻塞
- **#2【P1 越权】普通群成员能跑所有工作流**（触发付费生成/外部写、用服务端共享凭据）：聊天命令 `工作流 跑` 与 AI 工具 `run_workflow` 都加权限闸——群里要求发送者是房间管理员(power≥50)，普通成员只能「列表」；DM(1:1) 放行。
- **#3【P1 DoS】公开回调端点无认证读全 body**：验证 run_id/token 前就按 `Content-Length` 把请求体读进内存。改成先按上限(512KB)挡，超了直接 413、不读 body。
- **#4【P2 回调 token】**：① token 改优先从请求头 `X-Cosmac-Token` 取（不进 URL/日志），兼容老 `?token=`；② DB **只存 token 哈希**(sha256)、不存明文，比对用 `hmac.compare_digest` 防时序侧信道。
- **#5【P2 同步阻塞】ComfyUI 等到 120s 卡住 appservice 事务**：把 ComfyUI（慢）放**后台线程**跑、立即返回"已开始"，它自己把图发回群；webhook/dify/coze(≤30s) 仍同步。聊天命令和 AI 工具两条路径都改。
- 验证：`test_wf_cmd` 加越权闸 + token 哈希用例；cosmac **129 单测全过**、ruff、client build 通过。纯后端 → 部署 `restart guduu-bot`。

## 2026-06-19 — 工作流安全（上）：SSRF 防护 + AGENTS.md 状态同步
- **#1【P1 SSRF/凭据外泄】**：管理员可在连接器填任意 URL，服务端带 `COSMAC_WF_*` Bearer 去打它——能借此打内网/`localhost`/云元数据 `169.254.169.254`。新增 `wf.check_outbound_url`：只允许 http/https；把主机名解析成 IP，链路本地/保留/组播**永远拒绝**，私网/环回默认拒绝（自建内网可设 `COSMAC_WF_ALLOW_INTERNAL=1`）。webhook/dify/coze/comfyui 四个连接器外呼前都校验，并 `allow_redirects=False` 防重定向绕过。
- **#6【P2 规范】**：AGENTS.md 路线图同步 CLAUDE.md（模块2 ✅ / 模块3 🟡，原来停在模块2 进行中）。
- 验证：`test_wf` 加 SSRF 用例（环回/元数据/私网/非 http/公网放行/内网开关），22 例全过、ruff 通过。
- 余下工作流安全项（普通成员越权执行 / 回调端点 DoS / 回调 token 进 URL / 同步调用阻塞事务）下一条处理。

## 2026-06-19 — 知识库(RAG)健壮性修复（向量空间隔离 + 复用查询向量 + key 兜底）
- **#1【P1 安全】方舟 key 误发 OpenAI**：`get_embedder` 主路径已由并行会话改掉（不再自动挪用 `ARK_API_KEY`）。再补一道兜底：若有人把 `ark-…` key 配进 `COSMAC_EMBED_API_KEY` 却没给 `base_url`，强制指向方舟端点——绝不让 ark key 默认连 `api.openai.com`。
- **#2【P1 正确性】换 embedder 后旧向量污染检索**：`KnowledgeChunk` 只存了向量、没存"用哪个 embedder/维度"。从哈希兜底切到真嵌入后，新查询向量与旧哈希向量在不同空间里算余弦 = 乱序/失真。修：embedder 加 `tag`（如 `hash:256`/`oai:openai:text-embedding-3-small`），分块新增 `embed_tag` 列入库记下，`search` **只比同 tag** 的分块。旧数据需重新入库才会被检索。
- **#3【P2 性能/费用】一次回复 embed 两遍 query**：bot 的 `_kb_context` 分别搜群库/个人库，各 `embed_one(query)` 一次。修：查询向量**只算一次**，`search` 加 `qvec` 入参，群库/个人库共用，省一半嵌入请求。（pgvector 近邻索引仍是后续：v1 全量扫描是 §3 既定的，规模化再换，接口不变。）
- 验证：`test_kb` 加 3 例（embed_tag 入库 / 跨 embedder 不混 / qvec 复用）；cosmac **123 单测全过**、ruff 通过。
- 部署：改了 `cosmac/` → `restart guduu-bot`。⚠️ **新增 DB 列 `embed_tag`**：知识库表是新建的、create_all 不会给已存在的表加列——若服务器已建过 `cosmac_kb_chunk`，需 **drop 重建知识库表**（数据本就要按 #2 重新入库）；本地删 `run/cosmac.db` 即可。

## 2026-06-19 — 模块3 P4：工作流异步回调(长任务跑完反向通知回群)
- 长任务(ComfyUI 出视频、n8n 长流程)同步等不现实——加异步回调:提交后即返回,平台跑完反向 POST 回 bot,再把结果发回原群。
- **链路**:`WorkflowRun` 加 `token`(一次性)+ status `pending`;`wf_repo` 加 create_pending/get_run/complete_run;config 加 `public_url`。连接器(webhook)勾 `async` → bot `_dispatch_async` 建 pending+token、拼回调 URL `{public_url}/cosmac/wf/callback/<id>?token=` 塞进 webhook payload、提交即回"⏳ 已提交"。
- **入站端点**:`_Handler.do_POST` 处理 `/cosmac/wf/callback/<id>`(**不**用 hs_token,用每次运行的 token 校验)→ `handle_wf_callback` 验 token+pending → 把 `{output|error}` 发回原群 → complete_run 清 token(防重放,重复回调→404)。
- 后台:连接器加「异步(长任务)」开关(webhook);WorkflowDef 加 `async`。
- 验证:`test_wf_cmd` 加 4 例(异步提交建 pending+带回调URL / 回调发结果并结清+重放404 / 错token 403 / 未知run 404);cosmac **120 单测全过、ruff 通过**、client build 通过;preview 确认异步开关渲染、无报错。
- 部署:发 dist + restart guduu-bot + **配 `COSMAC_PUBLIC_URL`** + **nginx 放行 `/cosmac/` → bot:9000**(见 DEPLOY.md);否则异步连接器不启用、退回提示。
- 待续:定时触发(cron)、插件市场接真。

## 2026-06-19 — 模块3 P3：ComfyUI 适配器(图/视频:提交→轮询→回传媒体)
- 把外部平台连接器最后一档 ComfyUI 接上(影视场景):提交工作流图 → 轮询完成 → 把产出的图回传到触发的群。
- **matrix_client** 加 `upload_media`(POST /_matrix/media/v3/upload→mxc)+ `send_image`(发 m.image 消息)。
- **wf.py `run_comfyui`**:连接器存"API 格式工作流图模板",用 `{{input}}` 占位、安全注入用户输入 → `POST /prompt` → `_comfy_poll` 轮询 `/history/{id}`(上限 120s)→ `_comfy_download` 从 `/view` 取图 → upload_media + send_image 发回群。需在群里触发(要 client+room_id)。`run_connector` 加 client/room_id 参数,bot 命令路径与 run_workflow 工具路径都传入。
- **后台**:平台加 ComfyUI 选项 + 工作流图 textarea(`graph`);WorkflowDef 加 `graph` 字段。
- 说明:轮询是同步阻塞(MVP),超长生成需异步回调(后续);本机无真 ComfyUI,靠单测覆盖。
- 验证:`test_wf` 加 3 例(完整流程 mock HTTP+假client、缺房间、坏图 JSON);cosmac **116 单测全过、ruff 通过**、client build 通过(修了模板里 `{{input}}` 嵌套 mustache 解析报错→ `v-pre`);preview 直连生产:ComfyUI 连接器 graph 字段渲染 + round-trip + 清理,无报错。
- 部署:发 dist + restart guduu-bot。至此工作流连接器支持 **webhook/dify/coze/comfyui** 四档。
- 待续:异步回调入站端点(长任务)、定时触发、插件市场接真。

## 2026-06-19 — 模块3 P2：Dify / Coze 专用适配器
- 在通用 webhook 之上加两个平台适配器(REST+key):
  - **Dify**:`run_dify`——mode=workflow 走 `/v1/workflows/run`(inputs[input_key]=用户输入)、mode=chat 走 `/v1/chat-messages`(query);抽 `data.outputs` 或 `answer`。
  - **Coze**:`run_coze`——`/v1/workflow/run`(workflow_id=ref_id, parameters[input_key]=输入);认业务码 code==0,取 data。
  - `run_connector` 按 platform 分派 webhook/dify/coze;缺凭据/缺 workflow_id 友好报错。密钥仍只走服务端 env `COSMAC_WF_<CRED>`。
- 连接器定义加可选字段 `mode`/`ref_id`/`input_key`;后台「工作流」表单按平台条件显示(Dify→应用类型+输入变量名;Coze→workflow_id+输入变量名;webhook→请求方法)。
- 验证:`test_wf` 加 6 例(Dify workflow/chat/缺凭据、Coze 成功/缺id/业务错);cosmac **113 单测全过、ruff 通过**、client build 通过;preview 直连生产:Dify 连接器条件字段渲染 + round-trip + 清理,无残留无报错。
- 部署:发 dist + restart guduu-bot。用 Dify/Coze 时在服务端配 `COSMAC_WF_<CRED>`=该平台 key。
- 待续:ComfyUI(图/视频:提交→轮询→回传媒体)、异步回调入站端点、定时触发。

## 2026-06-19 — 模块3 P1 闭环：工作流后台 UI + 主 AI 工具 run_workflow
- 把 P1 闭环补齐:① 后台能配连接器;② 主 AI 能自然语言触发。
- **主 AI 工具 `run_workflow`**:`Toolbox` 加该工具(读控制室连接器定义→跑→尽力入库),`Toolbox(client, control_room_alias=...)` 注入控制室别名;bot 构造时传入。不带 slug 调用→返回可用列表。也加进 `AI_TOOL_CATALOG`(后台工具开关可控)。
- **后台「工作流」tab**:`client.ts` 加 `getWorkflows/setWorkflows` + `WorkflowDef` 类型;`AdminView` 加 CRUD(slug/名称/平台/URL/方法/凭据名/输入提示/启用)。凭据名旁明示"真密钥在服务端 env `COSMAC_WF_<CRED>`、不进网页"。
- 验证:`test_wf_cmd` 加 run_workflow 工具例;`test_runtime_config` 工具数 4→5;cosmac **107 单测全过、ruff 通过**、client build 通过;**preview 直连生产**:工作流连接器 round-trip + 清理,生产无残留、无控制台报错。
- 部署:**发 dist + restart guduu-bot**(前端加 tab、后端加工具)。端到端:后台配 n8n/Make webhook → 群里 `工作流 跑 <slug>` 或让主 AI 触发 → 结果回群。平台需鉴权时在服务端配 `COSMAC_WF_<CRED>`。
- 待续:Dify/Coze/ComfyUI 专用适配器、异步回调入站端点、定时触发。

## 2026-06-19 — 模块3 开工：外部工作流连接器(P1 通用 webhook 引擎 + 命令)
- **定调(负责人拍板)**:模块3 不自建工作流引擎,而是**对接 n8n/Make/Coze/ComfyUI/Dify** 等现成平台;P1 先做**通用 webhook 连接器**(覆盖 n8n/Make/任意自建端点),配置式后台编排,同步执行。
- **架构**:连接器**定义**走控制室 state event `cosmac.workflows`(浏览器够不到 DB,同 Skill/Agent);**密钥绝不进 Matrix**——定义里只放凭据名 `cred`,真值在服务端 env `COSMAC_WF_<CRED>`(同 LLM key 策略);**运行记录**进 cosmac DB。
- 本次实现(纯后端):
  - `cosmac/wf.py`:`run_connector/run_webhook`——同步 POST `{input,source}`、规范化结果(命中常见输出字段)、Bearer 鉴权(env)、全程兜异常不抛;平台分派(目前 webhook,Dify/Coze/ComfyUI 留后)。
  - `cosmac/db/models.py` 加 `WorkflowRun` + `cosmac/db/wf_repo.py`(record_run/recent_runs)。
  - `appservice_bot`:`工作流 列表/跑 <slug> <输入>` 命令(读控制室定义→跑→结果发频道→尽力入库),全程懒导入+兜异常。
- 验证:新增 `test_wf.py`(8 例:输出抽取/Bearer/非2xx/网络错/缺URL/非JSON/未知平台)+ `test_wf_cmd.py`(6 例:检测/列表/跑成功入库/失败记error/未知slug/空)。cosmac **106 单测全过、ruff 通过**。
- 部署:**仅 `restart guduu-bot`**(纯后端;新表 cosmac_workflow_run 由 create_all 自动建)。要真跑还需在「管理后台→工作流」配连接器(UI 下一轮)+ 服务端配 `COSMAC_WF_<CRED>`(如平台需鉴权)。
- 待续:① 后台工作流编排 UI;② 注册主 AI 工具 `run_workflow`(自然语言触发);③ Dify/Coze/ComfyUI 适配器 + 异步回调。

## 2026-06-19 — 模块2：模型按群覆盖（Agent.model 接活，智能体功能补齐）
- 补上 Agent 最后没接的点:智能体定义里的 `model` 字段(UI 早能填、bot 一直忽略)现在生效——某群绑定的智能体若指定模型,主 AI 在该群就用那个模型回话。
- **顺手做了读优化**:把"本群人设/绑定技能/模型"收敛成 `_group_context(room_id)` **一次读**(原 `_group_persona` 拆成它),`_handle_event` 读一次、传给 addendum 复用,少几次 Synapse state 读。
- **按群模型**:`_agent_for_model(model)` 同 provider 换 model 构建 Agent 并缓存(`_model_agents`);全局配置(provider/人设)变更时清缓存。没覆盖/与当前一致→用默认 Agent;构建失败→回退默认,绝不阻断回复。人设仍走 addendum、不在此设。
- 验证:`test_group_agent` 加模型覆盖例(取到 model、拿到不同且被缓存的 Agent、无覆盖用默认);cosmac **92 单测全过、ruff 通过**。
- 部署:**仅 `restart guduu-bot`**(纯后端、无前端)。

## 2026-06-19 — 模块2：主 AI 短期记忆（带最近对话上文，治"失忆")
- **修缺口**:此前 `agent.run` 每条消息只喂 `[system, 当前用户话]`,主 AI 记不住同群/私聊里刚说过什么(连 DM 都没上下文)。
- **做法(贴 §3:聊天记录在 Synapse、不重存)**:bot 回话前用 `client.get_messages` **实时读本房间最近 N 条**,映射成对话历史(bot 自己发的→assistant,其它人→user),喂给模型;**不进 cosmac DB**。
- `agent.run` 加 `history` 参数:消息序列变 `system → 最近历史 → 当前 user`。bot 加 `_recent_history`(窗口 12 条、单条截断 600 字、排除当前触发消息、全程兜异常)。
- 长期记忆(超窗口的滚动摘要)留作后续 DB 派生数据。
- 验证:`test_agent_tools` 加 history 顺序例 + `test_group_agent` 加 _recent_history 角色映射/排除当前例;cosmac **91 单测全过、ruff 通过**。
- 部署:**仅 `restart guduu-bot`**(纯后端、无前端改动,不必发 dist)。

## 2026-06-19 — 模块2：Rule 规则引擎（平台级硬约束，全局注入、优先级最高）
- 模块2「记忆/知识库/Rule/Skill」补上最后一块 **Rule**:平台级硬约束(如"对外报价/发布须经确认""不得编造数据"),无论群里用哪个智能体都注入,且**放 addendum 最前、优先级最高**。
- 沿用已验证套路(同技能/智能体):全局规则存控制室 state event `cosmac.rules`,浏览器(管理后台)写、bot 读。
- 后端:`config.py` 加 `RULES_EVENT_TYPE`;`appservice_bot._global_rules_text` 读规则渲染成「必须严格遵守」块,拼进 `_skill_addendum`(规则→人设→技能→知识库)。
- 前端:`client.ts` 加 `getGlobalRules/setGlobalRules` + `GlobalRule` 类型;`AdminView` 加「规则」tab(行内编辑列表:勾选启用/文本/删除/加一条/保存)。
- 验证:`test_group_agent` 加规则注入例(启用过滤 + 排在最前);cosmac **89 单测全过、ruff 通过**、client build 通过;**preview 直连生产**:规则新建→重新加载读回(round-trip)→清理,生产无残留、无控制台报错。
- 部署:发 dist + `restart guduu-bot`(bot 改了注入)。

## 2026-06-19 — 模块2 上线：cosmac DB 接生产 Postgres + 修嵌入挪用 ARK key 的坑
- **DB 上线**:服务器给 cosmac 单开 Postgres 库(cosmac_user/cosmac),`COSMAC_DATABASE_URL` 写进 guduu-bot.service,重启后 bot 连上并建好四表(cosmac_skill/agent/kb_doc/kb_chunk)。至此命令建技能、知识库、RAG 在生产真正可用(此前只有 state event 的全局技能/智能体能用)。具体连接信息进本机 DEPLOY.md。
- **修坑(P1)**:`get_embedder()` 原把 `ARK_API_KEY` 也当嵌入 key→去调 `text-embedding-3-small`,但方舟没这模型、会报错拖垮知识库入库/检索。改为**只认显式 `COSMAC_EMBED_API_KEY`/`OPENAI_API_KEY`**,不挪用 ARK;没配就用哈希词袋(词法检索)。要在方舟做嵌入需显式配 COSMAC_EMBED_API_KEY+BASE_URL+MODEL。
- 验证:cosmac 88 单测全过、ruff 通过。服务器侧:`init_engine` 列出四表通过。
- 部署:`restart guduu-bot`(已含连接串);本次嵌入修复需再 `git pull` + restart。无前端改动。

## 2026-06-19 — 模块2：知识库接活（bot RAG 注入 + 入库聊天命令）
- 把上一步的知识库引擎接进主 AI，端到端闭环：群里加文档 → 主 AI 据此回答。
- **入库命令** `cosmac/db/kb_cmd.py`（同 skill_cmd 套路）：`知识 列表/添加/删除/搜`；`添加 <标题> ｜ <正文>`。作用域:群=本群库 / 私聊=个人库;写操作群里需管理员;容量护栏(单篇≤20000字、每作用域≤200篇);删除只能删本作用域、按编号。
- **bot RAG**：`_skill_addendum` 现按用户这句话检索本群+个人知识库 top-K 片段(余弦、min_score 过滤)，作为「参考资料」块注入(人设→技能→知识库)。bot 加 `_is_kb_command`/`_run_kb_command`(懒导入+兜异常+管理员闸,同技能命令)。
- 验证：新增 `test_kb_cmd.py`(7 例)+ `test_group_agent` 加 RAG 注入例;cosmac **88 单测全过、ruff 通过**。修了一个测试隔离坑:KB 测试会因机器上真有 OPENAI/ARK key 而走真实网络——setUp 里清掉 embedding key、强制哈希兜底。
- 部署：发 dist 不需要(无前端改动);**要 `restart guduu-bot`**(bot 改了命令分发+注入)。**前提**:服务器装 SQLAlchemy + 配 cosmac DB,知识库命令/RAG 才真正生效(否则优雅降级);要好的语义检索还需配 embedding key(OPENAI_API_KEY/方舟),否则用哈希词袋(仅词法相似)。
- 待续:① 后台/上传式入库(大文档);② pgvector 提速;③ 模型按群覆盖;④ Rule。

## 2026-06-19 — 模块2：知识库引擎(嵌入抽象 + 入库/检索, 本地可验、零基建)
- 开工知识库(模块2 最重一块)。**关键取舍**:检索 v1 用 **Python 余弦相似度**(在该作用域分块上排序),SQLite/PG 都能跑、本地可验,**绕开 pgvector 依赖**;pgvector 留作规模化优化。嵌入走多模型抽象:有 OpenAI 兼容 key 用真嵌入(默认 text-embedding-3-small),无 key 自动降级**哈希词袋向量**(确定性、给词法相似度)。
- 新增:`cosmac/ai/embeddings.py`(Embedder 抽象 + HashingEmbedder 兜底 + OpenAICompatEmbedder + get_embedder 按 env 选 + cosine);`cosmac/db/models.py` 加 **KnowledgeDoc / KnowledgeChunk**(embedding 存 JSON 浮点数组、跨后端通用;删文档级联删分块);`cosmac/db/kb.py`(chunk_text 带重叠切块 + ingest_document 切块·嵌入·落库 + search 余弦 top-K + list/delete)。作用域沿用 room/user/global。
- 验证:新增 `test_kb.py` 8 例(切块/嵌入自相似/入库/检索排序/作用域隔离/删除级联);cosmac **80 单测全过、ruff 通过**。本地 e2e 冒烟(无 key→哈希):"商单怎么报价"→《商单报价》、"什么时候发布最好"→《发布排期》,路由正确。
- **本次无需部署**:纯后端引擎、bot 还没用它(下一步接 RAG 注入 + 入库入口)。
- 待续:① bot RAG——回话前检索本群知识库、把 top-K 片段注入上下文;② 入库入口(聊天命令 `知识 添加` / 后台上传);③ 规模化上 pgvector;④ 真嵌入 key(服务器配 OPENAI_API_KEY/方舟)。

## 2026-06-19 — 模块2：群绑定智能体 + bot 应用（人设+技能；智能体真正"活"起来）
- 让 Agent 真正生效:某群在「频道管理 → 角色」选一个**本群智能体**,主 AI 在该群就以它的人设回应、并自动启用它绑定的技能。
- **前端**:`useChannelAdmin` 的 `ChannelPersona` 加 `agentSlug`(随既有 persona 自动存进频道 state event `cosmac.channel_config`,零新机制);`ChannelAdminModal` 角色 tab 加「本群智能体」下拉(选项来自 `getGlobalAgents`)。
- **后端**:`config.py` 加 `CHANNEL_CONFIG_EVENT_TYPE`;`appservice_bot._skill_addendum` 扩展——读本群频道配置:① 绑了智能体→注入它的人设 + 绑定技能;② 否则用自定义人设 `persona.prompt`。技能按 slug **去重**(全局已注入的不重复)。模型覆盖(agent.model)本期先不做,留待下一步。全程兜异常,任何读取失败都只是少注入、不阻断回复。
- 验证:新增 `test_group_agent.py` 5 例(绑定注入人设+技能 / 停用回退 / 自定义人设 / 无配置空 / 无绑定时全局技能照常);cosmac **72 单测全过**、ruff 通过、client build 通过;preview:频道管理→角色 tab 出现「本群智能体」下拉、无控制台报错。
- 部署:发 dist + `restart guduu-bot`(bot 改了注入逻辑)。
- 待续:① 模型按群覆盖(agent.model→per-room llm);② 知识库(pgvector·RAG)。

## 2026-06-19 — 模块2：管理后台「智能体」UI + §3 架构定调
- 继「技能库」之后,管理后台加 **智能体** tab:定义可复用 AI 角色(人设 + 模型覆盖 + 绑定技能集),全局 Agent 同样存控制室 state event `cosmac.agents`。CRUD/启停齐活,绑定技能用技能库里的勾选列表。
- **§3 架构定调(负责人拍板,解决上一条 DEVLOG 里 #3 待定项)**:全局 Skill/Agent 定义**走 Matrix state event**(浏览器够不到 DB),与「全局 AI 配置」同套路;DB 留给知识库(pgvector)/记忆/聊天命令建的群级·个人技能。已更新 CLAUDE.md §3 数据分层表。
- 后端:`config.py` 加 `AGENTS_EVENT_TYPE`(bot 暂未消费——下一步做"群绑定 Agent + bot 应用其人设/模型/技能")。前端:`client.ts` 加 `getGlobalAgents/setGlobalAgents` + `GlobalAgent` 类型;`AdminView.vue` 加智能体 tab。
- 验证:client build 通过;**preview 直连生产**:智能体新建写控制室→重新加载读回(round-trip)→删除清理,生产无残留、无控制台报错。
- 部署:**仅发 dist**(后端只加了个常量、bot 还没用 Agent → 无需 restart)。
- 待续:① 群绑定 Agent + bot 应用;② 知识库(pgvector·RAG)。

## 2026-06-19 — 全局技能健壮性修复（脏数据不致哑 + 首条也限长 + 写校验）
- **#1【P1】坏技能能让 bot 不回话**：`skills_text.render_skills` 假设字段是字符串、直接 `.strip()`，`name:123` → AttributeError；且 bot 的 `_skill_addendum` 兜了两个数据源、却**没兜最后的 render 调用**，于是整条消息收不到回复（与 docstring 承诺相反）。修：render 里字段一律 `str()` 安全转换 + 非 dict 跳过；bot 把 `render_skills` 也包进 try/except。
- **#2【P2】6000 字上限被第一条绕过**：`used>0` 判断让首条技能永不截断，单条 12000 字直接全量注入。修：改成"预算用尽即停 + 单条超长就**截断这一条**（含第一条）"，总长度恒 ≤ 上限。`db/service.render_skill_prompt` 改为**委托** `render_skills`（两份渲染合一，不再各踩各的坑；`MAX_TOTAL_PROMPT_CHARS` 单一来源）。前端 `setGlobalSkills` 加**写校验+规范化**：数量 ≤50、正文 ≤2000、字段强制转字符串——脏数据从源头就写不进去。
- 验证：新增 `test_skills_text.py`（脏类型不崩 / 首条超长被截 / 多条总预算）；cosmac **64 单测全过**、ruff 通过、client build 通过。
- 部署：改了 `cosmac/`+前端 → 发 dist + `restart guduu-bot`。
- **#3【P1 架构】待负责人定**：全局技能/Agent 现存控制室 **state event**（`cosmac.skills`/`cosmac.agents`），与 §3「Skill/Agent 定义存 CosMac DB」冲突。并行会话选 state event 是因"浏览器够不到 DB"。两条路：(a) 保留 state event 并把 §3 加一条例外（像 AI 配置那样）；(b) 移到 DB + bot 开一个鉴权 REST 端点给浏览器 CRUD。见下方讨论，未动。

## 2026-06-19 — 模块2：管理后台「技能库」UI（全局技能，走控制室 state event）
- 让技能"可视":管理后台加 **技能库** tab,增删改/启停全局技能,**主 AI 在所有群回话时注入**。
- **架构定调（负责人选 Matrix state event 方案）**:浏览器够不到 cosmac 的 DB(bot 进程私有、没开 API),所以全局技能跟「AI 配置」同套路——存控制室 state event `cosmac.skills`,浏览器写、bot 读。零新基建、立刻可视。群级/个人技能仍走聊天命令存 DB,bot 注入时两边合并。
- 后端:`config.py` 加 `SKILLS_EVENT_TYPE`;新增 `cosmac/skills_text.py`(纯渲染、**不依赖 DB/SQLAlchemy**,带总长上限);`appservice_bot._skill_addendum` 重写为 **全局(控制室 state event) + 群/个人(DB) 合并渲染**,两来源各自兜异常、互不拖累——全局技能纯 Matrix 读,服务器没装 SQLAlchemy 也能用。
- 前端:`client.ts` 加 `getGlobalSkills/setGlobalSkills`(读写控制室 state event,同 getAiConfig 套路)+ `GlobalSkill` 类型;`AdminView.vue` 加技能库 tab(表格 + 新建/编辑表单 + 启停/删除)。
- 验证:cosmac **63 单测全过、ruff 通过**;client build 通过;**preview 直连生产**:技能库渲染→新建写入控制室→重新加载读回(round-trip)→删除清理,生产无残留、无控制台报错。
- 部署:**前端发 dist + 后端 restart guduu-bot**(bot 改了注入逻辑;全局技能只读 state event、不需要 SQLAlchemy)。

## 2026-06-19 — 品牌清理 GuDuu→CosMac（stage1：环境变量 + 注释/文档，零停机）
- 背景：负责人指出项目叫 CosMac，但服务器/运维层到处是 GuDuu（env 变量名、bot 账号、service 名）。当初 guduu→cosmac 改名没做干净。决定**彻底**改，但分两阶段保证不挂线上 bot。
- **stage1（本次，代码层零停机）**：
  - **环境变量 `GUDUU_*`→`COSMAC_*`**：`config.py` 加 `_env()`（先查 `COSMAC_` 再回退 `GUDUU_`），`from_env` 全改走它；`db/engine.py` 的 `database_url()` 同样支持两前缀。**向后兼容**——生产 systemd 里现有的 `GUDUU_*` 仍生效，可从容迁移。
  - **注释/文档/README**：`GuDuu`/`guduu` 品牌字样、stale 模块路径（`guduu.bots`/`guduu.ai`/`guduu.tests`/`本包（guduu）`）、txn id 前缀、CLAUDE.md/AGENTS.md 的 env 示例、`client/package.json` 的 name/description（`gudu-workbench`/`GuDuu·…`→`cosmac-workbench`/`CosMac·…`，含 package-lock 同步）→ 全改 CosMac/`COSMAC_*`。（全仓库复扫确认：剩余 `guduu` 仅 = 故意保留的 stage2 标识符 + DEVLOG 历史流水，不再有漏网的品牌字样。）
  - **刻意保留**（属 stage2，和**线上 bot 账号强耦合**，改了会找不到账号）：bot id `@guduu`、本地域名 `guduu.local`、注册文件名 `guduu-bot.yaml`、前端 `BOT_LOCALPART='guduu'`、localStorage key。已在 config.py 加注释标明。
- **stage2（待负责人择期，服务器侧迁移）**：把线上 bot `@guduu`→`@cosmac`（重注册 appservice + 重邀进所有房间）+ 改 systemd 用 `COSMAC_*` + 同步翻 `BOT_LOCALPART`。给 runbook。
- 验证：cosmac 63 单测全过、ruff 通过；`from_env` 本地仍从 yaml 读到 token（不回归）。纯后端+文档，**无需发 dist**；prod 行为不变（GUDUU_* 仍认），重启可选。

## 2026-06-19 — 模块2 技能：加群级写权限闸 + 容量上限（防 prompt 注入/上下文炸）
- **#1【P1】群内任何成员都能改群级技能**：群级技能会作为 system prompt 注入**所有群成员**的 AI 请求 → 等于持久化 prompt injection。`handle_skill_command` 加 `can_write`：群级写操作（添加/删除/停用/启用）要求发送者是房间管理员（bot 端 `_is_room_admin` 读 power_levels，power≥50），普通成员只能「技能 列表」；个人技能（私聊/USER 作用域）不受限。
- **#2【P2】技能数量/正文无限制**：`skill_cmd` 加上限——单作用域 ≤50 个、正文 ≤2000 字、标识 ≤64、名称 ≤80；`service.render_skill_prompt` 再兜一层**总注入长度 ≤6000 字**，超了停止注入剩余并提示，避免技能一多撑爆模型上下文/费用。
- **#3【P1 迁移风险】遗留 power=100 管理员**：已是“告警不移除”（Matrix 约束，bot=100 动不了≥100 的人）。**操作建议**：部署前审计控制室 `m.room.power_levels`，确认 ≥100 的只有 owner(@admin)+bot；线上当前单管理员、无此类遗留。
- 验证：`test_skill_cmd`/`test_skill_service` 加权限闸 + 容量 + 总长度截断用例；cosmac **63 单测全过**、ruff 通过。纯后端（cosmac/），**部署只需 `restart guduu-bot`，无需发 dist**。

## 2026-06-19 — 路线图：模块1（主 AI 控制层）收尾标 ✅，专注模块2
- 负责人决定：模块1 地基已齐（消息感知/自动进群/回复、多模型可配、AI 工具调用、控制室热下发 + 管理员↔成员联动），标 **✅ 完成**；模块2（群级 记忆/知识库/Rule/Skill）保持 🟡。
- 解除上一条 DEVLOG 里提的「模块1+2 都进行中」与「一次只推进一个模块」铁律的冲突——现在只有模块2 在推。CLAUDE.md / AGENTS.md 路线图同步更新。后续主 AI 的增量工具按需补，不再算"开工中"。纯文档改动，无需部署。

## 2026-06-19 — 控制室对账复查再修 3 项（失败不再谎报成功 / 遗留 100 告警 / AGENTS.md 同步）
- **#1【P1】历史遗留 power=100 管理员永不被撤权**：bot(=100) 在 Matrix 里无法降权/踢出 ≥ 自己等级的人，旧 bug 曾把管理员设成 100 才会出现。无法自动修——`_reconcile_control_members` 现对「≥100 且已非管理员」的成员单独 **warning**（提示需重建控制室），不再静默当 owner 跳过。（注：going-forward 已不会再产生——新管理员只给 50；真实不变式下 owner 是服务器管理员、在期望集里、不会误报。）
- **#2【P1】降权/踢出失败仍报成功**：`_reconcile_control_members` 之前忽略 `set_power_levels`/`kick` 的布尔返回、无条件 log「已移除」。改成**检查结果**：失败报 `error`（被撤销者仍能写配置是安全问题），只对真正踢成功的报成功。前端 `setUserAdmin` 改成返回「控制室是否同步成功」，`AdminView` 撤管理员时同步失败则 **warn 提示重试**，不再静默报全成。
- **#3【P1 项目规范】AGENTS.md 未跟 CLAUDE.md**：模块2 开工后只更新了 CLAUDE.md（§3 数据存储分层 + 路线图 module2🟡）。把这两块同步进 `AGENTS.md`，两份「宪法」一致。
- 验证：`test_control_members.py` +2 例（踢出失败报 error / 遗留 100 告警）；cosmac 50 单测全过、ruff 通过、client build 通过。
- 部署：改了 `cosmac/` → `restart guduu-bot`；改了前端 → 发 dist。
- ⚠️ **留给负责人决策**：CLAUDE.md/AGENTS.md 现在模块1 与模块2 都标 🟡进行中，与「一次只推进一个模块」铁律冲突。要么把模块1 收尾标 ✅、要么暂停模块2——这是产品节奏决定，按 §6.6 该由你定。

## 2026-06-19 — 模块2：技能聊天命令（建/列/删/启停），闭环打通
- 给 Skill 加「创建/管理入口」——按负责人选择：**先做聊天命令（后端，不碰客户端、不与并行会话撞车）**。
- 新增 `cosmac/db/skill_cmd.py`（纯逻辑、吃 session、返回回复文本，好测）：`技能 列表/添加/删除/停用/启用`；`添加 <slug> ｜ <名称> ｜ <正文>`（分隔符兼容半/全角，更新时不空串覆盖未传字段）。`looks_like_skill_command` 做不连 DB 的前缀闸（中文直接前缀、英文要词边界）。
- **作用域**：私聊 bot（≤2 人）建的是**个人技能**(user)，群里建的是**本群技能**(room)——直觉对齐"每账号 / 群级"。
- `appservice_bot` 接入：`_try_handle_command` 命中技能前缀就执行；`_is_skill_command` 纯字符串判断、`_run_skill_command` 懒导入 cosmac.db + 全程兜异常（服务器没装 SQLAlchemy → 回"功能暂不可用"，不崩不哑）。
- 验证：新增 `test_skill_cmd.py` 8 例（检测/帮助/增改不覆盖/启停删/DM作用域/缺slug/未知子命令）；cosmac **58 单测全过、ruff 通过**。本地端到端冒烟：`技能 添加` → `effective_skill_prompt` 真注入、别的群隔离为空。
- 部署（可选，要让线上生效才做）：`git pull` → `pip install -r cosmac/requirements.txt`（装 SQLAlchemy）→ `restart guduu-bot`。默认用 SQLite `run/cosmac.db`；要用 Postgres 则在 systemd 配 `GUDUU_DATABASE_URL`。不部署则零回归（懒导入失败即降级）。

## 2026-06-19 — 模块2：Skill 接进主 AI（按 房间+发起人 注入技能提示，零回归）
- 把上一步建好的数据层用起来：主 AI 每处理一条消息，按 (本群, 发起人) 算出**当前生效的启用技能**，作为 system addendum 临时注入这一轮——不污染常驻人设。
- 新增 `cosmac/db/service.py`（纯函数胶水层）：`effective_skills(room_id,user_id)` 按 **global→room→user** 顺序汇总启用技能；`render_skill_prompt` 渲染成提示文本；`effective_skill_prompt` 便捷组合。
- `Agent.run` 加 `extra_system` 参数：与常驻人设**合并成单条 system 消息**（兼容 Claude 等只认一个 system 的 provider）。
- `appservice_bot._skill_addendum`：取技能拼 addendum。**全程 try/except + cosmac.db 懒导入**——生产服务器还没装 SQLAlchemy 时 import 失败也只是退化成「无技能」，bot 照常回话，零回归。没技能时 addendum 为空、行为与现状完全一致。
- 验证：新增 `test_skill_service.py`(4 例：作用域顺序/过滤/渲染/空) + `test_agent_tools` 加 1 例(extra_system 合并进单条 system)；cosmac 48 单测全过、ruff 通过。
- 部署：**暂不需要**——纯后端、且当前无任何技能数据→零可见变化。等下一步加了「建技能」的入口（后台 UI 或命令）并在服务器 `pip install -r cosmac/requirements.txt` 后，再 `restart guduu-bot` 才会真正生效。
- 待续：还**没有创建技能的入口**（UI/命令/seed），端到端闭环留作下一步。

## 2026-06-19 — 模块2 开工：cosmac 数据层骨架（Skill/Agent，PG/本地 SQLite 双跑）
- **背景**：讨论"每账号配置/Skill/Agent/知识库/聊天记录要不要数据库"。结论先写进 CLAUDE.md 新增「数据存储分层」：**Synapse 已存的（聊天记录/成员/房间状态）绝不重存**；AI 层自己的结构化/派生数据（Skill/Agent/知识库/记忆/工作流…）才进 cosmac 自己的 DB。全局 AI 配置仍走控制室 state event，每账号轻量配置优先用 Matrix account data。
- **基建决策**：复用生产现成 PostgreSQL，给 cosmac 单开 database/schema，知识库按需装 pgvector。走 §2 第 3 条路径，不碰 Synapse 核心。
- **本次实现**（`cosmac/db/`，纯新增、未接进 bot 运行路径，零行为变化）：SQLAlchemy **同步**（bot 是同步的）。`engine.py` 连接由 `GUDUU_DATABASE_URL` 决定，生产指向 Postgres、本地默认回退 SQLite `run/cosmac.db`（含内存库 StaticPool 处理）；`models.py` 两张表 **Skill / Agent**，带 **scope/scope_id/slug** 作用域三元组（user/room/global，同时覆盖"每账号"和"群级"），Agent 用 JSON 存 skill_slugs 暂不建多对多；`repo.py` upsert(部分更新+字段白名单)/get/list(作用域+启用过滤)/delete。
- **决策**：第一批只做 Skill/Agent（纯关系型、立刻有用）；知识库(pgvector·RAG)、群级记忆、Rule 是后续切片；建表暂用 create_all，以后上 alembic 迁移。
- 验证：新增 `test_db.py` 6 例（内存 SQLite，建/改/查/删/作用域隔离/字段护栏）全过；cosmac 43 单测全过、ruff 通过。`SQLAlchemy>=2.0` 进 requirements（生产另需 `psycopg`）。
- 部署：**本次无需部署**——纯后端新增、bot 还没用它。等接进 bot 时再 `pip install -r cosmac/requirements.txt` + `restart guduu-bot`。

## 2026-06-19 — 控制室成员对齐改由主 AI(power 100)执行（撤销管理员真正失权）
- **问题(P1)**：普通管理员都是 power 50，A(50) 撤销 B(50) 时 Matrix 不允许同级降权/踢出，前端 `removeFromControlRoom` 两个操作都静默失败，UI 却报成功——B 撤销后仍能写 AI 配置。只有唯一的 100 所有者撤权才真生效。
- **修法（按 reviewer 方向：让 power 100 的 bot 执行成员同步，浏览器只提交期望）**：
  - 新增 state event `cosmac.ctrl.admins`（前端写「期望服务器管理员集」，管理员 50 够写）。`setUserAdmin` 改成 `syncControlRoomAdmins()`：ensureControlRoom 尽力即时邀请/提权 + 写期望集。删掉做不可靠的 `removeFromControlRoom`。
  - **bot 端 `_reconcile_control_members`**：收到控制室的 `cosmac.ctrl.admins` 事件即对齐——把 power<100、不在期望集里的成员降权(从 power_levels.users 删)+ 踢出。bot=100 能踢同级 50，绕过前端做不到的约束。
  - **安全护栏**：① 只在 room_id == 别名解析出的控制室才动手（防有人塞事件借 bot 踢人）；② 绝不动 owner(100) 和 bot 自己；③ 任何异常只记日志不抛。`matrix_client` 加 `set_power_levels`/`kick`。
  - UI 文案改诚实：撤管理员提示「控制室写权限将由主 AI 同步移除」，不再静默报全成。
- 验证：新增 `test_control_members.py`（撤销者被移除 / owner·bot 永不被动 / 非控制室不动手 / 无需移除则不写）；cosmac 37 单测全过、ruff 通过、client build 通过。
- **补**：老控制室（早先建的）里 bot 可能还是默认 power 0，那样它没法执行降权/踢出。`reconcileControlRoomAdmins` 改成顺手把 bot 提到 100（由所有者执行；下次 @admin 存 AI 配置或改管理员时即补上），并去掉「无其他管理员就 return」的早退，确保单管理员场景也能补 bot 权限。
- 部署：改了 `cosmac/` → 要 `restart guduu-bot`；改了前端 → 发 dist。

## 2026-06-19 — 主 AI：右侧中枢 AI 面板加「放大」按钮 → Cowork 式全屏弹窗
- **需求**：右侧主 AI 顶栏加放大按钮，点开后是一个和 Claude Cowork 一致的弹窗。
- **关键定位**：真正渲染的右侧主 AI 是**写死在 `LiveView.vue` 里的内联 `aside.ai-panel`**（`aiOpen` 控制），不是 `components/layout/AiChatPanel.vue`（那套连同 App.vue 是未挂载的演示稿，main.ts 只挂 LiveView）。一开始误改了 AiChatPanel，已回滚，改在 LiveView 内联面板上做。
- **做法**：新增 `aiMax` 态 + 顶栏「放大/还原」图标按钮；放大态下 `.ai-panel.maximized` 脱离 dock、近全屏居中（inset 2.5vh/2.5vw）+ 半透明遮罩（点空白还原）。面板主体重构成 `ai-main`（默认单列 / 放大态三栏）：左栏**完整还原 Cowork 左导航**（对话·协作·代码 分段 → ＋新任务 → 项目/产物/定时任务/派发·Beta → 最近列表 → 底部用户），中栏复用原对话+输入，右栏 Progress 清单 + 项目文件。全部 scoped 在 LiveView，未碰未挂载的 AiChatPanel/ai-panel.css。
- **决策**：线上面板原本只有关闭按钮，这次只加「放大↔还原」一个新态，最简且贴合需求；演示稿里的展开/浮窗多态不照搬。左栏导航项为演示态（toast 占位），「新任务」清空当前对话。
- 验证：preview 直连，放大→三栏弹窗布局正确、还原回 360px dock、遮罩开合正常、无控制台报错。

## 2026-06-19 — 再复查修 3 项（token 进 URL / 新管理员卡住 / 文档过时）
- **#1【P1 安全】as_token 拼进每个 URL 查询参数**：`matrix_client._url` 把高权限 as_token 放进 `?access_token=…`，会进 nginx/代理/错误日志。改用 `requests.Session` + `Authorization: Bearer <token>` 头，URL 里只留 `user_id`（身份标识、非密钥）；11 处请求调用全改走 session。新增 `test_matrix_client.py` 守这条红线。
- **#2【P2】已有控制室的权限修复无法由受影响的新管理员触发**：reconcile 只有「已在房、有 power 的人」能跑，新管理员自己进不去也修不了。改法：在 `setUserAdmin(uid, true)`（把人提成管理员）成功后，趁**当前操作者**（已在控制室、power 100）在线，顺手 `ensureControlRoom()` 幂等对账，把新管理员邀进去并提权。尽力而为、失败不回滚提权。（残留极端态：控制室里有权限的人全不可用时仍需 Synapse 侧手工介入，可接受。）
- **#3【P3】文档与实际安全策略冲突**：`ai/__init__.py`、`ark.py`、`claude.py`、`openai_compat.py` 的注释仍称「管理后台可下发 key」，但 bot 已明确忽略控制室 key。注释统一改成「key 只走服务端环境变量/Secret Manager，后台只选 provider/模型」。
- 验证：MatrixClient 冒烟（token 不在 URL、Bearer 头就位）、cosmac 单测全过（含新增 2 条）、ruff 通过、client build 通过。
- 部署：#1 改了 `cosmac/` → 要 `restart guduu-bot`；#2 改了前端 → 发 dist。（dist 顺带并行会话的 `useAiPanel.ts` 改动。）

## 2026-06-19 — 复查修 1 个真 bug：控制室对账会自我锁权
- 对「多模型 + 后台 provider + 控制室」一轮复查，发现并修掉一个潜伏 bug。
- **bug**：`reconcileControlRoomAdmins`（#2 给已有控制室补管理员权限那段）在控制室**没同步进本地**时，`pl` 退化成 `{}`，而传入的管理员列表不含创建者，于是 `sendStateEvent('m.room.power_levels', { users })` 会**抹掉 events_default/state_default 等全部字段、并丢掉创建者自己的 100 权限 → 自我锁权**。
- **修法**：只有**真正读到** power_levels（房间已同步、事件存在）才提权；读不到就跳过，绝不用空对象覆盖。邀请那步不受影响。
- 触发面：当前仅 1 个管理员 → `others` 为空、reconcile 直接 return，故线上未触发；加第二个管理员前修掉。
- 复查同时确认多模型四家代码（build_provider/openai_compat/claude/ark）无问题。client build 通过、preview 无报错。
- （本次 dist 还顺带带上并行会话给 `onUpdate` 加的 80ms 防抖：初始同步的历史消息整批一次渲染、不再逐条蹦。）

## 2026-06-19 — 多模型四家 + 后台可选 provider/模型（密钥仍走服务端，安全加固）
- 多模型扩成四家：新增通用 `cosmac/ai/openai_compat.py`（OpenAI 兼容，参数化 api_key/base_url/model，含工具调用）；`ark.py` 改薄成它的子类；`claude.py` 加 api_key 参数。`ai/__init__.py` 加 **build_provider**（claude / openai / deepseek·ark / **gemini**，key 缺则降级 echo，gemini 走 Google 的 OpenAI 兼容端点）。
- 管理后台「AI 配置」加 **模型后端下拉**（默认/DeepSeek/Claude/ChatGPT/Gemini）+ 模型 id；bot 从控制室读 `provider/model` 热切（按签名重建）。
- **关键安全决策（推翻"密钥填后台"的初版）**：API Key **绝不进 Matrix**。state event 无法加密、会明文进 DB/历史/同步给全员，所以密钥只走**服务端环境变量/Secret Manager**；后台只选 provider+模型，UI 明示"切到服务器没配 key 的后端 AI 将无法回话"。`appservice_bot._read_overrides` 不读 api_key、`build_provider(api_key="")` 让各 SDK 自己读环境变量。
- 验证：新增 `test_build_provider.py`（4 家分派 + base_url + 缺 key 降级 + 未知报错）；cosmac 31 单测全过、ruff 通过、client build 通过；preview 直连生产验证后台选 DeepSeek+模型写读 round-trip、provider 热切（测试数据已清回默认）。
- 启用某后端：仍在服务器 systemd 配该家的 key 环境变量（ARK_API_KEY / ANTHROPIC_API_KEY / OPENAI_API_KEY / GEMINI_API_KEY），后台只管"用哪家+哪个模型"。

## 2026-06-19 — 多模型新增 DeepSeek（走火山引擎方舟，OpenAI 兼容）
- 接入 DeepSeek：方舟 Chat Completions 与 OpenAI 完全兼容，所以新增 `cosmac/ai/ark.py`（`ArkProvider`），复用 `openai` SDK，只把 base_url 指向方舟、key 用 `ARK_API_KEY`。实现 `complete` + `complete_with_tools`（OpenAI 工具格式：tools/tool_calls/tool 角色），所以 DeepSeek 也能用主 AI 的工具调用。
- `get_provider` 注册 `deepseek` / `ark` 两个名（deepseek 是 ark 别名）；无 `ARK_API_KEY` 自动降级 echo。模型 id 用 `GUDUU_LLM_MODEL` 填方舟的 Model ID 或 Endpoint ID(ep-...)，默认 `deepseek-v3.2`；可选 `ARK_BASE_URL` 换区域。
- system 提示去重：`_build_messages` 仅在历史无 system 消息时才用构造人设兜底，避免和 Agent 传入的 system 重复。
- 验证：新增 `test_ark_provider.py`（选 provider 回退 + 消息/工具翻译，构造 client 不联网）；cosmac 21 单测全过、ruff 通过。`openai>=1.50` 已在 requirements。CLAUDE.md/AGENTS.md §9 补 DeepSeek 启用说明。
- 启用：服务器 `Environment=GUDUU_LLM_PROVIDER=deepseek` + `Environment=ARK_API_KEY=...` + `Environment=GUDUU_LLM_MODEL=<方舟模型id>`，daemon-reload+restart。

## 2026-06-19 — 代码审查修复（6 项：安全/正确性/工具友好性）
- 对一轮代码审查发现的 6 个问题逐条核实后全部修复。
- **#1【P1 安全】appservice 密钥硬编码进 git**：`config.py` 的 `as_token`/`hs_token` 默认值改空串；`from_env` 按「环境变量 → 注册文件 `run/synapse/guduu-bot.yaml`(已 gitignore)」优先级注入；新增 `require_tokens()` 启动校验，缺失即报错，不再静默用泄露的旧 key。⚠️ **旧 token 仍在 git 历史，必须在服务器侧轮换**。
- **#2【P1】`BOT_ID` 写死 `cosmac.cc`**：本地 `guduu.local` 下会邀请不存在的账号。改为函数 `botId()`=`@guduu:${serverName()}`，按当前登录服务器动态拼（登录后求值，避开模块加载期 mx 未就绪）。
- **#3【P1】控制室只有创建者可访问**：`ensureControlRoom` 现邀请**全部服务器管理员**并把他们的房间权限提到 100（否则受 state_default=50 限制，写不了 `cosmac.ai.config`）。
- **#4【P1】配置读失败"失效开放"**：`get_state_event`/`resolve_alias` 现在区分 404(确实没有→None) 与 403/网络错(抛异常)；`_read_overrides` 仅在读成功时更新缓存，读失败保留上次成功配置——一次抖动不再把管理员设的工具限制清空。
- **#5【P2】控制室 room_id 永久缓存**：别名改为每轮（20s 缓存窗口）重解析，控制室重建/重指向后能跟上。
- **#6【P3】Vue 源混入 4 个 NUL 字节**：`LiveView.vue` 的 markdown 占位哨兵由字面 NUL 字节改为转义序列 `\x00`（运行时等价），文件恢复为纯文本，`rg`/`file`/diff 不再当二进制。
- 验证：`test_runtime_config.py` 加 2 个回归测试（抖动不失效开放 / 缺密钥报错），cosmac 单测全过、ruff 通过、client `npm run build` 通过；`from_env` 本地能从 yaml 读到密钥（本地开发不回归）。

## 2026-06-19 — 管理后台入口改回「仅管理员可见」
- 之前为破 CORS 鸡生蛋把入口改成常显；现 CORS 已通、`isServerAdmin()` 探测正常，按用户要求改回：登录后探测是服务器管理员才显示「管理后台」入口，普通用户菜单里看不到（手敲 /#/admin 仍被 AdminView "无权限"闸 + Admin API 403 双重挡回）。
- LiveView：恢复 isAdmin ref + afterLogin 里 isServerAdmin 探测 + 入口 v-if=isAdmin。preview 验证 @admin 登录可见入口、isAdmin=true。

## 2026-06-19 — 管理后台④：AI 配置（人设/模型/工具开关，控制室热下发）
- 管理后台最后一块**AI 配置**：网页改主 AI 的人设(system prompt)/模型 id/工具开关，保存后 ~20s 内**热生效、无需重启 bot**。管理后台四块(用户/频道/数据/AI)全齐。
- 架构(守 CLAUDE.md：Matrix 原生、不另起服务、不动 nginx)：配置存进一个**控制室**(别名 `#cosmac-ctrl:<server>`)的 state event `cosmac.ai.config`。前端(管理员=房间创建者，有权写 state)写、bot 运行时读。
- **零回归设计**：bot 读配置全程 try/except + 20s 缓存 + 按 (provider,model,system_prompt) 签名才热重建 llm/agent；控制室不存在/未加入/读失败 → 完全回退启动时的环境变量配置。provider 本期前端**只读不可改**(避免切到没 key 的后端→静默降级 echo)。工具开关：Toolbox 加 `set_enabled`，specs/execute 都按启用集过滤。
- 后端：`config.py` 加 control_room_alias + AI_CONFIG_EVENT_TYPE；`matrix_client` 加 resolve_alias/get_state_event；`appservice_bot` 加 _read_overrides/_apply_runtime_config。前端：`client.ts` 加 ensureControlRoom/getAiConfig/setAiConfig；AdminView 加 ai tab。
- 验证：新增 `test_runtime_config.py`(假 client 验证人设热应用/工具过滤/缓存/读失败回退)，cosmac 14 单测全过、ruff 通过。前端**直连生产**验证：保存自动建控制室 `!sQjaKThqehKUaCojUV`、写读 `cosmac.ai.config` round-trip(st 200)。⚠️ bot 端读取本机无法验，需上线点验。

## 2026-06-19 — 管理后台③：数据概览（KPI + 最活跃频道）
- 管理后台第三块**数据概览**：AdminView 加 `overview` tab。4 张 KPI 卡(账号总数/管理员/停用、频道总数/公开/加密、成员人次合计/平均、活跃频道≥2 人) + 服务端版本 + 最活跃频道 Top 8。
- 低风险：基本是**复用**已有 `listUsers`+`listAdminRooms` 前端聚合，仅 client.ts 新增轻量 `getServerVersion()`。
- 踩坑：Synapse Admin rooms API 的 `order_by=joined_members&dir=b` 在本版(1.153.0)**没按预期降序**(返回升序)，所以"最活跃 Top"改为**客户端按成员数降序**，不依赖接口排序。
- preview 直连生产验证：1 账号 / 38 频道 / 54 成员人次(均1.4) / 18 活跃 / 服务端 1.153.0；Top 8 按成员降序正确。build 通过。管理后台四块只剩 AI 配置(后端重活)未做。

## 2026-06-18 — 个人主页接入 URL（/me）；其余覆盖层确认保持弹窗
- 路由覆盖审计：主导航(board/tasks/频道/admin)已全覆盖；临时态(菜单/各设置弹窗/侧栏折叠/AI侧栏/专注模式)按惯例不接。剩 5 个页面级覆盖层(个人主页/市场/插件商城/资产/CLI)原本无地址。
- 按负责人选择：只给**个人主页**接 `/me`(它最像页面、该能刷新留存/分享)；市场/商城/资产/CLI 保持弹窗(刷新落在工具弹窗里体验怪)。
- 实现：`useProfileHome().visible` 接进集中同步——`computePath` 加 `/me` 分支、`applyFromRoute` 把 admin/profile 两个全屏覆盖层按地址互斥开关、watch 数组加 `profileVisible`；router 补 `/me`→Blank。
- preview 验证：开个人主页→`#/me`、后退→关闭回 board、**刷新 `/me`→直达个人主页**。build 通过。

## 2026-06-18 — 工作台接入 URL 路由（每个视图有独立地址 + 后退/刷新/深链）
- 问题：整个 app 是单个 `LiveView` 根组件、用内部状态切视图，点来点去 **URL 从不变**——刷新回默认页、不能分享链接、浏览器后退无效。
- 方案：**集中式双向 URL 同步**，不动任何点击 handler（导航本就收敛在 `selectSpace/openBoard/openTasks/openRoom + adminOpen`）。状态变→`router.push` 写地址；地址变(后退/前进/手改/深链)→还原状态；首屏按地址恢复一次(深链到频道要等房间加载)。用 hash history(已有)，无需改 nginx。
- 地址方案：`/admin`、`/s/:space/board`、`/s/:space/tasks`、`/s/:space/c/:roomId`。`router/index.ts` 补这些路由(指向空 `Blank` 组件——LiveView 不走 `<router-view>`，路由仅为让 hash 合法、不被 catch-all 重定向回 /)。
- preview 直连生产验证全过：登录自动 `/s/x/board`、看板/任务切换、频道 `/c/room`、后退前进、**频道深链刷新直达**、切工作区更新地址、`/admin` 开关。build(vue-tsc) 通过。

## 2026-06-18 — 管理后台②：频道/群管理 + admin 接口 CORS 打通
- 管理后台第二块**频道管理**：AdminView 加 tab 切换（用户管理/频道管理）；频道面板列出**全服所有房间**（不同于侧栏只列"我加入的"）：名/别名、成员数(总/本服)、类型(公开/私有 + 加密锁)、操作(查看成员弹窗 / 删除)。删除带二次确认 + 是否封禁(block，禁止重建)。
- client.ts 补 admin 房间接口：`listAdminRooms`(v1 /rooms 自动翻页,按成员数倒序) / `getRoomMembers` / `deleteRoom(block,purge)`。沿用 `adminFetch` 那套。
- 本地 preview 直连生产验证：拉到 36 个真实房间(GuDuu测试群/《银河谣》制作专班/明星·粉丝…)、查看成员弹窗正常(GuDuu测试群→@guduu)。删除是破坏性操作,未拿真房间测(逻辑已接)。小修:标题栏右边距避让关闭✕。
- **关键卡点(服务器侧,无需改代码)**：admin 接口浏览器调用一直 `Failed to fetch`。根因有三层——① hs 的 nginx 转发正则 `^(/_matrix|/_synapse/client)` **漏了 `/_synapse/admin`**,请求落到兜底 200 文本;② 自己加 CORS 头与 Synapse 自带的 `ACAO:*` **重复**(浏览器拒绝双 ACAO);③ OPTIONS 预检 Synapse 对 admin 接不住。**最终方案**:nginx 只拦 `/_synapse/admin` 的 OPTIONS 预检(回 204),其余转发给 Synapse、用它单个 ACAO,不再自加头。（详见 DEPLOY.md 待补的踩坑条）

## 2026-06-18 — 管理后台①：用户管理（MVP，覆盖层集成进 LiveView）
- 新模块：平台管理后台。按"一次只推一个"先做**用户管理**：列表 / 新建 / 停用 / 恢复 / 重置密码 / 设撤管理员。
- 关键架构发现：真实 app 的根组件是 `views/LiveView.vue`（`main.ts` 挂它），**不是** App.vue —— `<router-view>` 不渲染，所以加 `/admin` 路由没用。改成把 `AdminView.vue` 作为**全屏覆盖层**集成进 LiveView：用户菜单加「管理后台」入口（仅管理员 `isServerAdmin()` 探测为真才显示），点开覆盖层、× 关闭。（已存 memory: client-root-is-liveview）
- 后端复用 Synapse Admin API（`/_synapse/admin/...`），用登录管理员 token：`client.ts` 补 `isServerAdmin/listUsers/deactivateUser/reactivateUser/resetPassword/setUserAdmin` + `adminFetch` 封装。
- **本地验证发现真问题**：浏览器从 app 源直连 hs 的 `/_synapse/admin/*` 被 **CORS 拦**（`/_matrix/*` 200、admin 路径 Failed to fetch）—— Synapse 只给 `/_matrix` 发跨域头。即原有 `createUser` 跨域下也不通。解决要在 hs 的 nginx 给 `/_synapse/admin/` 放开 CORS（限 app 源 + 允许 Authorization + 处理 OPTIONS 预检）。否则连真 @admin 也进不去（已把权限闸文案改成同时提示这两种原因）。
- 已验证：AdminView 覆盖层 + 左侧菜单（用户管理 active，频道/AI/数据「敬请期待」占位）+ 权限闸渲染正常；build/类型通过。happy path（列表/操作）待 nginx 放 CORS 后线上点验。
- 仅做只读验证（未对生产执行任何停用/改密/建号）。

## 2026-06-18 — 主 AI 控制层②：LLM 工具调用（AI 真能动手了）
- 模块 1 后半段落地：主 AI 从「只会聊天」升级到「会调用 IM 能力动手」。整条链路：用户自然语言 → 模型决定调工具 → 真执行（建群/发消息/查成员/读记录）→ 结果回灌 → 给最终回复。
- 关键设计（守 CLAUDE.md：厂商差异只锁在抽象层）：
  - `ai/base.py` 新增厂商中立的 `ToolSpec/ToolCall/TurnResult`，`Message` 扩展 tool_calls/tool_call_id；`LLMProvider.complete_with_tools` 默认退回 `complete`（echo/openai 不支持工具也照常跑）。
  - `ai/claude.py` 实现工具调用：中立结构 ↔ anthropic `tool_use`/`tool_result` 互转，所有 anthropic 专有格式只此一处。
  - 新增 `ai/tools.py` 工具箱：`create_room`/`send_message_to_room`/`list_room_members`/`get_recent_messages`，转发到 `MatrixClient`；用 `ToolContext` 注入「当前房间/发起人」，建群默认拉发起人进群。`matrix_client.py` 补 `get_members`/`get_messages`（读聊天记录的"眼睛"）。
  - 新增 `ai/agent.py` ReAct 循环（max_steps=5 防死循环）；`appservice_bot.py` 把纯 `complete` 路径换成 `agent.run`。旧「专班」关键词快路保留做富卡派单演示。
- 验证：新增 `tests/test_agent_tools.py`（假大脑+假client 端到端验证「决定调工具→真执行→回灌→最终回复」、建群自动邀请发起人、max_steps 兜底），9 个单测全过；ruff（行宽88）通过；bot 构造冒烟通过（4 工具就位，echo 退化为纯文本不报错）。
- 待办：线上配 `GUDUU_LLM_PROVIDER=claude`+`ANTHROPIC_API_KEY` 后做真·Element 自然语言建群点验；前端 AI 面板接到真 bot（下一步把"演示"打通成"产品"）。

## 2026-06-18 — 修复数据看板「横向拖移」BUG
- 现象：数据看板画布在窗口偏窄时可被横向拖动/平移，标题被推出左缘（用户反馈）。
- 根因：`.board-scroll` 与 `.canvas` 都只写了 `overflow-y: auto`；按 CSS 规范，另一轴若仍是 visible 会被隐式算成 `auto`，于是内容略宽时整块就能横向滚动/拖移。
- 改法：两处显式补 `overflow-x: hidden`（LiveView.vue 的 .board-scroll + styles/canvas.css 的 .canvas），只保留纵向滚动，彻底禁掉横向拖动。本地 preview 1440/1180 宽验证：ofx=hidden、无横向滚动、看板渲染正常、无报错。

## 2026-06-18 — 任务行可点开看详情（负责人/进度/做到什么程度/子步骤）
- 每条任务补字段 progress + detail + steps[]（子步骤 checklist）；任务行加 clickable + 悬停箭头。
- 新增任务详情弹窗(.td-*)：状态点 + 标题 + 状态/负责人/截止 chips + 进度条% + 当前进展说明 + 子步骤勾选。
- taskDetail 弹窗状态 + openTaskDetail。本地验证：点「主角配音+配乐」→ 负责配音Agent/65%/4 子步骤(2✓2○)；无报错。

## 2026-06-18 — 制作流水线改为 AI 影视 7 阶段
- 用户校正流程：AI 影视不是传统拍摄。阶段定为 **剧本 / 服化道 / 分镜 / AI生成 / 配音配乐 / 剪辑 / 成片**（7 步）。
- PROD_STAGES 改 7 项；各集 current 重映射(夜航星第6集→配音配乐4、银河谣第12集→分镜2、墨白MV→剪辑5)；甘特条改 ganttBarStyle(i) 按阶段数均分(不再写死 18%/22%，7 阶段不溢出)。
- 本地验证：卡内 7 步流水线 + 甘特 7 行(剧本✓…AI生成✓→配音配乐●→剪辑/成片)排布正常；无报错。

## 2026-06-18 — 每集卡下面跟「这一集的任务」，逐集排列
- 用户要：每集卡下面是这一集的任务，然后才是下一集（卡+任务）。改成：每集 = .ep-block（流水线卡 + 该集任务时间线），逐集往下堆。
- 数据：每个 episode 加 tasks[]（自带任务，按集分）；新增 epTasks(ep) 排序、activeTaskTotal、showCount 改为按集任务数求和。Tab 角标=该剧所有在制集任务数(夜航星6/银河谣3/墨白6)。
- 移除原来跨集的单条时间线 + 旧 todos 过滤(taskItems/taskCols/showTimeline)。整部进度仍在顶部、点卡仍开甘特。
- 本地验证：夜航星 第6集(4任务)+第7集(2任务) 各自归位；无报错。

## 2026-06-18 — 多集同时在制 + 点开看甘特弹窗；去掉看板
- 升级：一部剧支持**多集同时在制**——每集一张流水线卡（可多张，flex-wrap）；**点单集卡 → 弹甘特图**（该集 5 阶段在日期轴上的排期，done绿/current橙/todo灰 + 图例）。
- 按用户决定**去掉最下面的看板**；保留 整部进度 + 多集卡 + 时间线。show-band 改为可滚动。
- 数据：productionTabs 每剧 episodes[] 多集（夜航星 第6集/第7集、墨白 MV/专辑企划…）；新增 ganttEp 弹窗状态 + GANTT_DATES + mkStages 复用。
- 本地验证：夜航星 2 张在制卡、点开第6集甘特(剧本✓分镜✓配音●剪辑成片)、看板已移除、时间线仍在；无报错。

## 2026-06-18 — 剧集顶部再加「整部进度」（分段条：每段一集）
- 用户指出现有流水线卡是"单集"进度，上面还应有"整部剧"进度。加一条**分段式整部进度条**(每段=一集：已完成绿/当前集橙/未做灰) + "已完成 M/N 集 · X%"，放在本集流水线卡上方。
- productionTabs 每剧补 series{done,total,unit,pct}；.series-bar/.series-seg 样式。夜航星 5/12集48%、银河谣 11/12集95%、墨白 4/8首58%。
- 本地验证：切 Tab 整部进度+本集卡同步；无报错。

## 2026-06-18 — 剧集 Tab 点开后：制作流水线卡 + 时间线 + 看板（顶部换成流水线卡）
- 顶部从"朴素进度条"换成用户要的**制作流水线卡**：剧本→分镜→配音→剪辑→成片(✓完成/●当前发光/数字未到，连接线 done 段绿) + 进度条 + 页脚(负责人头像 + 排期 + 还剩N天)。下面接 时间线 + 待办/进行中/已完成 看板。
- productionTabs 每部剧补流水线 demo 数据(project/current/percent/assignee/排期)；activeProd 渲染流水线卡；恢复 PROD_STAGES/mkStages 与 .prod-* 卡样式(改为整宽单卡)。
- 本地验证：墨白卡=剪辑阶段/55%/剪辑Agent·6/16→6/24·还剩4天，与用户给的样图一致；时间线4行+看板4卡；切 Tab 同步；无报错。

## 2026-06-18 — 剧集 Tab 点开后(旧)：进度条 + 时间线 + 看板
- (此版顶部为朴素进度条，已被上一条的"制作流水线卡"替代)

## 2026-06-18 — 任务看板加「剧集 Tab」：3 部剧切换，各看各的任务
- 需求几轮对齐后定稿：任务看板标题栏加 **3 个剧集 Tab**（夜航星/银河谣/墨白），点哪个看板就只显示那部剧的 待办/进行中/已完成。
- todos.ts：TodoItem 加 `show` 字段，把 11 个 demo 任务按剧集打标（夜航星3/银河谣4/墨白4）。
- LiveView：productionTabs + activeShow + showCount(角标) + taskItems 按 activeShow 过滤；header 加 .prod-tab 胶囊(头像+名+数量，选中橙边)；board-sub 改显当前剧任务数。
- （撤掉了上一版误做的"剧集制作卡大卡片+流水线"，那不是用户要的。）
- 本地验证：3 Tab 计数正确(3/4/4)，点银河谣→看板只剩银河谣 4 条；无报错。

## 2026-06-18 — 数据源改为单按钮 → 右侧面板；去掉看板头 ℹ(中枢AI开关)
- 用户要：数据源按钮移到 ℹ 的位置(最右)；ℹ 图标+功能整个去掉；点数据源 → 右侧出现面板。
- 数据看板头现在只剩一个「数据源」按钮(圆柱图标+数量角标)，点开右侧 `BoardSourcePanel`(复用 .right 样式)：展示数据源列表 + 内联增删 + 自动保存。下拉小卡片和铅笔编辑弹窗合并进这个右面板，删掉 BoardSourceModal。
- 去掉数据看板头的 ℹ(中枢 AI 开关)——中枢 AI 仍可从插件竖栏「智」/顶栏开。
- 三个右面板互斥扩展：关于此频道 / 中枢 AI / 数据源 同时只开一个。
- 任务看板头同样：board-sub + 单个数据源按钮。
- useBoardSources 加 panelOpen/panelBoard/toggleSourcePanel/closeSourcePanel。本地验证：点数据源→右面板出现、中枢AI收起；加「抖音创作者后台」保存→删除复位，无脏数据；无报错。

## 2026-06-18 — 数据源控件从侧栏挪到看板头（用户要放标题栏）
- 用户要把数据源「展示+编辑」放到 数据看板/任务看板 的**标题栏**(ℹ 左边)，不是侧边栏。
- 侧栏两行恢复成原来的纯图标+文字；看板头 ch-actions 加：①数据源按钮(圆柱图标+数量角标)→点开下拉列表(展示当前源 + 「编辑数据源」入口)；②铅笔「编辑数据源」→开 BoardSourceModal。两个看板头都加。
- 下拉用绝对定位 .bs-pop；点外面关闭(接进 onDocClick，识别 .bs-hdr)。数据/持久化逻辑不变(useBoardSources)。
- 本地 preview 验证：数据看板/任务看板头显示 数据源(N)+编辑+ℹ，下拉正常，无报错。

## 2026-06-18 — 修：数据源「编辑」铅笔图标改常显
- 上一版铅笔图标 opacity:0 只在 hover 行时显示，用户反馈"没看到按键"。改为常显(opacity .65，hover 升到 1)，两个看板行的"编辑数据源"图标一眼可见。

## 2026-06-18 — 数据看板/任务看板：数据源「展示 + 编辑」+ 持久化
- 需求：两个看板行的图标改成「数据源展示」，再加一个「数据源编辑」图标。数据源先当配置占位、做 UI + 持久化。
- 左侧图标改为数据源图标：点击展开该看板的数据源列表（cs-src-list，显示 类型+名称，空则提示点 ✎ 添加）。
- 行右侧加铅笔「编辑数据源」图标(hover 显示)：开 `BoardSourceModal` 弹窗增删数据源(名称/类型[频道聚合/外部平台/API接口/手动录入]/备注)。
- 持久化：按当前工作区(Space)存一条 `cosmac.board_sources` state event(内容 {dashboard:[],tasks:[]})。matrix/client.ts 加 get/setBoardSources；新建 useBoardSources composable(防抖自动保存) + BoardSourceModal(复用 .cam-* 样式)。
- 坑：activeSpace 变化时 Space 房间 state 可能还没 sync → 首次读为空。修复：openEditor/togglePopover 时再 load() 一遍(同 liveMembers 的 refresh-on-open)。
- 验证(连生产 hs)：制作工作区加「抖音创作者后台」数据源 → 刷新仍在 → 删除复位，未留脏数据。数据源真实取数留待后续(配置占位)。

## 2026-06-18 — 右侧「关于此频道」与「中枢 AI」面板互斥
- 需求：开「关于此频道」就收起中枢 AI，开中枢 AI 就收起「关于此频道」（右侧同时只留一个）。
- 实现：LiveView 加两个 watcher —— `watch(rightPanelVisible→aiOpen=false)` / `watch(aiOpen→hideRightPanel())`。用 watcher 而非改每个按钮，自动覆盖所有入口(ℹ/顶栏/插件栏/输入条)。
- 验证：点 ℹ 开关于面板→AI 收起；点插件栏「智」开 AI→关于面板收起。无报错。

## 2026-06-18 — 频道头 ℹ 按钮 → 复刻 DEMO「关于此频道」右面板（真实数据）
- 频道头 ℹ(info) 按钮原本是「开关中枢 AI」；改为**复刻 DEMO**：开/关右侧「关于此频道」信息面板（RightPanel）。中枢 AI 仍可从顶栏/插件竖栏/输入条 AI 键开。
- RightPanel 做成**真实**：人员用真实 Matrix 成员(liveMembers，映射成面板形状，群主/管理员/成员/待接受)；技能/知识库/规则沿用已真实持久化的频道配置(空就空)；PINNED 块真实频道改为中性总览文案(去掉抖音/小红书等假平台claim)。
- RightPanel 自带 `import '@/styles/right.css'`(同 admin-modal：main.ts 不加载整包 index.css，组件自包含样式)。
- LiveView：导入 RightPanel + useRightPanel；onMounted hideRightPanel 默认收起；`<RightPanel v-if="rightPanelVisible && currentRoom && !focused">` 作为中枢 AI 面板左侧的信息列。
- 本地 preview 验证：夜航星点 ℹ → 弹出「关于此频道」(300px 列)，人员显示真实 2 人(admin 群主/guduu 成员)，与「频道管理」同源数据；无 console 报错。

## 2026-06-18 — 频道管理「技能/知识库/规则/数据权限」4 个列表标签 → 真实持久化（配置全标签页完成）
- 把最后 4 个列表型标签接通持久化，至此**频道管理 8 个标签全部去 mock**（人员真实成员 + 7 个配置标签真持久化）。
- 策略：**手动维护 + 自动保存**。真实频道**从空开始**（loadConfigFromRoom 把列表一律以"已存为准、没存就空"，清掉 seedConfig 的 demo mock）；用户在面板加/删/改，深度 watch 防抖整列表写回 cosmac.channel_config。
- 各列表加空状态提示 + 保存状态提示。标签数字用真实列表长度。
- 本地 preview 验证（连生产 hs）：夜航星技能从 0 → 加「生成分镜脚本」→ 刷新仍在；银河谣技能仍 0（隔离成立）；测试技能已删除复位，未留生产脏数据。
- **频道管理面板真实化全部完成。** 余下大头是任务#3：让中枢 AI bot 真按这些配置（人设/模型/规则）回复（动 cosmac/ 后端）。

## 2026-06-18 — 频道管理「模型 + 记忆审计」标签 → 真实持久化
- 复用上一条建好的 state event 机制，把**模型**(模型/Token预算/速率限制)和**记忆审计**(长期记忆/上下文范围/留存天数/审计日志)也接通自动保存。
- `useChannelAdmin`：loadConfigFromRoom 增读 model/memory；新增两个深度 watch → 改动防抖写回 cosmac.channel_config。`ChannelAdminModal` 模型页、记忆页加保存状态提示。
- 本地 preview 验证（连生产 hs）：夜航星改 Token 预算 507 + 关长期记忆 → 刷新后仍在；测试值已复位(预算500/长期记忆开)，未留生产脏数据。
- TODO：模型档位 MODEL_OPTIONS 仍是品牌占位名(CosMac Star-Pro/Lite)，要让 bot 真按它跑(任务#3)需映射到真实 provider/model。
- 已真实持久化的标签页：角色 / 模型 / 记忆审计。余下 技能/知识库/规则/数据权限(列表型，待确认真实内容来源)。

## 2026-06-18 — 频道管理「角色(人设)」标签 → 真实持久化（配置存进房间 state event）
- 建好配置持久化地基并接通**角色标签**：人设（AI 名称/语气/System Prompt）改一下就自动存进频道。
- `matrix/client.ts`：新增 `getChannelConfig`/`setChannelConfig`，存成每频道一条自定义 state event `cosmac.channel_config`（与 cosmac.workspace 同命名）。选 state event 而非 account data：群级共享、多端一致、留在房间、不改 Synapse 核心。写需房间发状态事件权限（一般管理员）。
- `useChannelAdmin`：`setCurrent(name, roomId)` 时从房间读已存配置 merge 进内存；深度 watch 人设 → 防抖 700ms 自动 `setChannelConfig`；`saveState`(idle/saving/saved/error) 给 UI 提示；加载期 suppress 防回声；demo 无 roomId 不写。
- `ChannelAdminModal` 角色页加保存状态提示「✓ 已保存到本频道 · 多端同步 / 保存失败(无权限)」。
- 本地 preview 验证（dev 客户端连的是**生产** hs.cosmac.cc）：夜航星改 AI 名 → 刷新后仍在（真存进 state event）；银河谣仍是默认「CosMac Star」→ **每频道隔离**成立。测试marker已清回默认，未留生产脏数据。
- 余下 model/memory/skills/knowledge/rules/dataScopes 标签页沿用同一持久化机制，按用户逐个确认再接。

## 2026-06-18 — 频道管理「人员」标签 → 真实 Matrix 成员（去 mock 第一步）
- 开始把「频道管理」面板从 DEMO mock 改成真实数据（路线图 #2 群级智能）。本轮先做**人员标签**。
- `matrix/client.ts`：新增 `listChannelMembers(roomId)` 返回真实成员（真名/头像 mxc→http/角色按 m.room.power_levels 推 群主≥100·管理员≥50·成员/join+invite 状态）；新增 `kickFromRoom`（真移除）。没设昵称的成员退回显示 id 的 localpart（如 bot 显 "guduu"）。
- `useChannelAdmin`：跟当前频道 roomId（`setCurrent(name, roomId)` / `open(name, roomId)`），暴露 `isLive`/`liveMembers`/真 `inviteLiveMember`/`removeLiveMember`；有 roomId 走真后端，无则回退 demo mock。
- `ChannelAdminModal` 人员标签：`isLive` 时渲染真实成员（头像/角色标签/APP 标/待接受标）+ 真邀请框 + 真移除；标签数字 `人员 N` 用真实人数；打开弹窗 watch 刷新防 sync 漂移。
- LiveView 传 `currentRoom`(真实 room id) 给面板。本地 preview 验证：夜航星频道显示真实 2 人（@admin 群主、@guduu 中枢AI APP·成员），与频道头 "A 智 2" 一致。
- **待补真实数据（已记 TODO）**：成员「可调取数据」无来源已移除；bot 没设 displayname/头像 → 退回 localpart+首字母；真人头像待用户上传后自动显示。
- **决策**：配置存哪？定为 **Matrix 自定义 state event**（不改 Synapse 核心、原生、多端同步），下一轮（人设等）落地。

## 2026-06-18 — 客户端：频道头「成员」按钮接 DEMO 的「频道管理」富面板
- 真实客户端（LiveView）频道头成员堆叠按钮原本只开简单「邀请成员」弹窗；改为**复刻 DEMO 逻辑**：点了打开 DEMO 同款 `ChannelAdminModal`「频道管理」富面板（角色/人员/技能/知识库/数据权限/规则/模型/记忆审计 多标签页，群级 AI 隔离配置）。
- 按既有「常驻挂载 + composable.open()」模式接入：导入 `ChannelAdminModal` 常驻挂载、按钮调 `useChannelAdmin().open(currentName)`；并 `watch(currentName)` → `setCurrent`，让面板跟着当前频道切到对应群配置（每群一份、互不影响）。
- 真实「邀请已有用户」入口保留在左侧频道栏「邀请成员」项，未丢功能。
- **关键修复**：`main.ts` 故意不加载整包 `styles/index.css`（防 DEMO CSS 串扰），导致 `.cam-*` 弹窗样式缺失、面板裸奔。让 `ChannelAdminModal.vue` 自带 `import '@/styles/admin-modal.css'`，组件自包含样式，DEMO/真实端两边都成型。本地 preview 已验证：居中卡片 720×660、遮罩、各标签页、成员头像齐全，无 console 报错。

## 2026-06-18 — 客户端：回复连接线竖线不连头像、留空隙
- 连接线 ::before bottom -13→-2px，竖线停在头像上方留空隙，不再连到头像。

## 2026-06-18 — 客户端：回复连接线弯角上移对齐文字
- 连接线弯角 ::before top 11→4px，弯角与回复文字对齐、竖线落到头像，更顺。

## 2026-06-18 — 客户端：回复预览往上提、与消息拉开间距
- 回复行与下方头像几乎贴着 → margin-bottom 2→7px，连接线 bottom 拉长到头像，回复行到头像顶约 7px 间距，更分明。

## 2026-06-18 — 客户端：回复预览补被引用人小头像（Discord 三行结构）
- 回复预览第一行补上**被引用人的小圆头像**（+ bot 显 APP 标），结构=被引用人头像/名字/预览 → 自己名字/时间 → 内容。
- `client.ts` LiveMsg 加 `replyToSender`，listMessages 带出被回复发送者 id（判断 bot + 取头像）。

## 2026-06-18 — 客户端：回复预览只留一个连接线 + 消息上方留空行
- 之前同时有「↩ 图标」和「弯角连接线」两个箭头 → 去掉 ↩ 图标，只留连接线。
- 每条消息上方加空行（`.msg:not(.grouped)` margin-top 8→18px；有回复的 22px），给连接线腾空间、不再贴着上一条、对齐。

## 2026-06-18 — 客户端：修回复预览错位（整行浮头像上方）
- 之前回复放在头像右侧同行 → 连接线对不上(错位)。改成 Discord 结构：`.msg` 改 column，回复预览**整行浮在头像上方**，下面 `.msg-main` 才是 头像+内容。
- 连接线 ::before 重新定位：从回复行中部**下探到下方头像**、顶部弧向右接到回复文字。加 **↩ 小箭头**图标。

## 2026-06-18 — 客户端：回复预览对齐 Discord（连接线 + 着重/配色）
- "↳" 箭头 → 改成 Discord 风**弯角连接线**（CSS ::before：border-left+border-top+圆角，从头像处弧连到回复预览）。
- 回复预览文字：对方名 **@xxx 上色加重**（nameColor），正文用**淡灰色**(text-3)区分。
- 修双 @ bug（bot 名本身以 @ 开头，渲染前 strip 一个 @）。

## 2026-06-18 — 客户端：聊天再对齐 Discord 观感（4 项）
- **消息行样式**：头像方块→正圆(40px)；去掉每条"成员/AI"小标签 → 名字按发送者确定性上色 + bot 才显"APP"标。
- **日期分隔线**：按天分组，中间横线显"今天/昨天/X 年 X 月 X 日"。
- **emoji 选择器面板**：点工具条表情/反应＋弹出 32 个常用 emoji 网格，点选即反应、点外面关。
- **悬停工具条扩展**：表情(开选择器)/回复/编辑(仅自己,非卡片)/复制。
- **编辑消息**：编辑自己的消息(m.replace)，输入框上方"编辑中"横幅、Esc 取消；消息显示"已编辑"。`client.ts` 加 `editMessage`。
- 说明：只采用通用聊天约定、不克隆 Discord 私有设计/图标。端到端验证(圆头像/日期线/APP/emoji面板32格/编辑载入)，未产生测试数据。

## 2026-06-18 — 客户端：聊天 Discord 化（分组/反应/回复/提及/编辑）
- **消息分组**：同发送者、5 分钟内、非回复 → 折叠头像/名字（左槽分组内悬停显时间）。
- **悬停工具条**：消息右上角悬停出现 👍/❤️/😂/回复。
- **表情回应**：真实 `m.reaction`，反应条显示 emoji+计数，点击切换（我的高亮），＋ 快捷加。`client.ts` 加 `listReactions/react/unreact`。
- **回复引用**：悬停"回复"→ composer 上方回复横幅 → 发送带 `m.in_reply_to`；消息上方显示"↳ 对方名 + 正文预览"。`client.ts` 加 `sendReply`，`listMessages` 解析 in_reply_to + 去 fallback。
- **@提及高亮**（renderMd 里 @用户 加底色）+ **编辑标记**（读 `replacingEvent` 显示"已编辑"，取最新内容）。
- 全部是 Matrix 原生能力、不依赖后台。端到端验证(墨白后援会)：反应👍1、回复预览、提及高亮、markdown 都正常 → 已撤回 6 条测试消息+1 反应清理干净。

## 2026-06-18 — 客户端：消息渲染 Markdown（输入/发送本就是真的）
- 澄清：输入框+发送一直是**真实**的（`send`→`sendTextMessage`→Synapse，持久化、bot 真回）。半 DEMO 的是 Markdown 工具条只插符号、消息却原样显示。
- 接通：消息流 + AI 面板的正文改用 `renderMd()` 渲染 Markdown（加粗/斜体/删除线/行内码/代码块/链接），工具条终于有效果。
- **安全**：先 HTML 转义再替换（`<script>` 变纯文本、防 XSS）；链接仅放行 http/https/mailto；代码内容用 \x00 占位隔离、不与"第 12 集"这类文本撞。已验证渲染+XSS。
- 顺带：`listMessages` 过滤掉**已撤回(redacted)/空 content** 的事件 → 不再显示空气泡。
- 附件/表情：按负责人意见，**等后台管理做好再接**（附件需上传媒体+渲染图片消息）。

## 2026-06-18 — 客户端：清掉工作区/频道剩余 DEMO + ★收藏接真
- 删掉已死的 DEMO 弹窗：`DepartmentCreateModal`(被真实新建工作区表单取代)、`ChannelAdminModal`(被真实成员弹窗取代) + 连带 import/composable/死函数(onAddWorkspace 等) + admin-modal.css。
- **★收藏接真**：原来只本地切换、且所有频道共用一个状态(bug) → 改成 Matrix 标准 `m.favourite` 标签，**按频道独立、跨设备同步**。`client.ts` 加 `isFavourite`/`setFavourite`。
- **频道筛选漏斗**去占位：点击从弹 toast → 聚焦"查找频道"输入框。
- 验证：收藏夜航星→银河谣不受影响→切回仍收藏→取消还原；漏斗聚焦输入框。
- 仍是占位（DEMO 本身也是、需较大改动，留着）：Composer 的**附件/表情**(要真做=上传媒体+渲染图片消息)。其余商城/CLI/插件等是"工具"不属工作区/频道范围。

## 2026-06-18 — 客户端：频道头真实成员 + 删除频道 + 清理
- **频道头真实成员**：成员数/头像堆叠改为读真实成员（`listRoomMembers` = `room.getJoinedMembers()`），不再硬编码"2"。
- **成员弹窗接真**：频道头"成员"按钮 → 真实成员弹窗（列出当前真实成员 + 邀请已有用户）；不再开 DEMO 的假管理面板（ChannelAdminModal 仍挂载、留作将来技能/知识库）。
- **删除频道**：频道设置加"删除频道"按钮（二次确认，leave+forget）——和工作区对称。
- 清理死代码 `onAddChannel`/`onInvite`/`onMembers`（已被 openNewChannel/openMembers 取代）。
- `client.ts` 加 `listRoomMembers`。
- ⚠️ 测试事故：自动化测删除频道时脚本没建出临时频道、误删了真实《银河谣》制作专班 → 已用应用"添加频道"在制作中心重建(同名+同简介+开场消息)，room_id 变。教训：测删除务必先确认目标是临时频道。

## 2026-06-18 — 客户端：新建工作区弹窗重排版
- 简称/可见性 从挤在一起的两列 → 改为**竖向全宽**字段（类型→名称→简称→可见性→预览），不再换行/拥挤。
- 简称标签精简成一行：「简称 + 淡色内联提示(左栏图标·最多2字·可留空)」。可见性两个按钮等宽。

## 2026-06-18 — 客户端：工作区简称统一限 2 个字符（多语言）
- 简称（新建工作区 + 工作区设置 两处）统一限制 **2 个字符**，按**码点**算 → 中/英/日/韩/混排/emoji 都是上限 2（emoji 代理对正确算 1 个）。
- 实现：去掉 HTML `maxlength`（按 UTF-16 单位、对 emoji 不准），改用 `watch` + `clamp2`(=`[...s].slice(0,2)`) 截断；label 文案改"最多 2 字"。
- 验证：制作中心→制作 / ABCD→AB / あいうえ→あい / 가나다→가나 / 😀😀😀→😀😀。

## 2026-06-18 — 修复：改工作区名后会跳到最后（排序 bug）
- 根因：之前用「按固定名字 WS_ORDER 排序」，靠名字匹配 → 一改名就掉出固定顺序排到末尾。
- 改为**和名字无关的稳定排序**：`cosmac.workspace.order` 显式序号，`listSpaces` 按 order 排（无 order 排后）。改名只动名字、不动 order → 位置不变。
- `updateSpace` 支持 order 并与 label **合并写**（不互相覆盖）；`createSpace` 新工作区 order=现有最大+1（排末尾）；移除 LiveView 里的 WS_ORDER。
- 回填：4 个基础工作区 order=制作0/运营1/明星2/外部3（用浏览器 admin 客户端写；CLI query-param 写 state 报 403，客户端 sendStateEvent 正常）。
- 端到端验证：排序仍为制作/运营/明星/外部；改名后位置不动；改回正常。

## 2026-06-18 — 客户端：工作区图标支持上传图片 + 简称限 2 字
- 工作区设置：简称 maxlength 3→**2**；简称下方加**上传图片**做工作区图标（上传/更换/移除），有图用图、无图回退简称文字。
- 头像走 Matrix 标准：`uploadContent` → mxc → 存 `m.room.avatar`；显示用 `mxcUrlToHttp`(走 /_matrix/media，已代理)。左栏图标、设置弹窗预览都识别。
- `client.ts` 加 `uploadMedia` / `mxcToHttp` / `spaceAvatar`，`updateSpace` 支持 avatar(undefined不动/''清空/mxc设置)，`LiveSpace.avatarUrl`。
- 端到端验证：上传测试图→左栏图标变图片→移除→回退文字，无残留。

## 2026-06-18 — 客户端：工作区"删除"改成按钮（UI 细节）
- 「删除工作区」从上方红色小字 → 改为底部页脚**左侧的红框按钮**（取消/保存在右侧）；点一下变「确认删除（含 N 频道）」+「×」二次确认。更符合"按钮"直觉。

## 2026-06-18 — 客户端：登录页去技术提示 + 工作区可删除
- 登录页删掉「连接后端 https://hs.cosmac.cc」这行（开发期提示，对用户太技术化、且暴露后端地址）。
- 工作区设置加「删除工作区」：二次确认（提示连同 N 个频道一起删、不可撤销）→ 退出该 Space 下所有频道 + 退出 Space 本身，自动切回数据看板。
- `client.ts` 加 `leaveAndForget(roomId)`。
- 端到端验证：建临时工作区→删除→工作区+其频道消失、切回制作中心、无残留。
- **决策**：客户端"删除"= leave+forget（admin 退出）；真正 purge 房间需 Admin API（后端）。

## 2026-06-18 — 客户端：频道设置（点频道头标题可编辑）
- 点频道头标题（带 ⌄）→ 打开「频道设置」弹窗，改**名称**和**简介**，实时写进 Matrix 房间（`m.room.name` + `m.room.topic`）。工作区可编辑的频道版。
- `client.ts` 加 `updateRoom(roomId,{name,topic})`。
- 端到端验证：改《银河谣》制作专班简介→频道头实时更新→改回，round-trip 正常、无残留。

## 2026-06-18 — 客户端：工作区设置（点工作区名可编辑）
- 点侧栏工作区名（"制作中心 ⌄"）→ 打开「工作区设置」弹窗，可改**名称**和**左栏简称**，实时写进 Matrix Space（名称→`m.room.name`，简称→`cosmac.workspace`）。
- `client.ts` 加 `updateSpace(spaceId,{name,label})`。
- 端到端验证：改简称→左栏图标实时更新→改回，round-trip 正常、无残留。

## 2026-06-18 — 客户端：成员管理（邀请已有用户）+ 一个重要发现
- 「邀请成员」接真：弹窗输入用户名 → 把已有用户邀请进当前频道/工作区（标准 Matrix invite，走 `/_matrix`，已验证：邀请 bot 进它已在的群返回正确的 `403 already in room`，证明链路通）。
- **关键发现/决策**：**「新建账号」从客户端做不了**——hs.cosmac.cc 的 nginx 只代理 `/_matrix/`，`/_synapse/admin/*` 返回静态页（不可达）；且本就不该把 admin token 暴露到浏览器。故账号创建 / 邀请链接**留给后端（业务后台）**，弹窗里已注明。这印证了「成员体系需要后端」。
- `client.ts` 加 `inviteToRoom` / `normalizeUserId` / `serverName`；`createUser`(Admin API) 先留作将来后端代理用。
- 未产生测试数据（建账号失败=没建出用户，已确认 404；邀请是对已在群的 bot 的 no-op）。

## 2026-06-18 — 客户端：频道彩色图标（产品形态）
- 频道列表 + 频道头用「彩色头像方块（代表字）」取代统一地球图标，明星/剧集频道一眼可辨。
- 颜色按频道名确定性哈希取自 8 色调色板；代表字优先「·」后一段 / 《》内首字。
- **决策**：颜色纯客户端计算、不写后端 → 所有现有频道立即生效、零成本；将来要自定义颜色再存 `cosmac.channel` 状态覆盖。

## 2026-06-18 — 客户端：频道简介（模块 R/产品形态）
- 「新建频道」加「简介」字段 → 存为 Matrix `m.room.topic`；频道头标题右侧展示简介（带分隔线）。
- `client.ts`：`LiveRoom` 加 `topic`、`listRooms` 读 topic、`createChannelInSpace` 支持 topic 入参。
- **决策**：用 Matrix 原生 `m.room.topic` 存简介（标准字段、Element 等也能读），不自造状态事件。
- 端到端验证：建了带简介的测试频道→频道头正确显示→清理掉。颜色/图标(封面)留作后续。

## 2026-06-18 — 客户端：工作区 / 频道创建链路接真（产品形态）
- 工作区固定顺序 制作/运营/明星/外部，默认落制作中心。
- 「新建工作区」完整版：类型(制作/运营/明星·粉丝/外部)+名称+简称(存 `cosmac.workspace` 状态)+可见性(公开/私密)+按类型自动建默认频道（明星类建 `虚拟明星·X`+`X后援会` 等）。
- 「添加频道」接真：在当前工作区(Space)下真建房间+拉主 AI+挂接，自动打开。
- 后端整理：真建 6 个影视主题频道(剧集/虚拟明星/粉丝)，清理 9 个旧创作者频道+无名残留，只留营销 5 个。
- 看板：加「数据看板」(制作驾驶舱) +「任务看板」(待办/进行中/已完成三列)，数据全换安其影视主题；登录后第一屏=数据看板。
- 品牌：`tenant` 改安其影视工作室；顶栏/侧栏统一。
- **决策**：工作区=Matrix Space，频道=挂 Space 下的房间(m.space.child)；简称/类型这类业务属性存自定义状态事件 `cosmac.*`，不碰协议层。

## 2026-06-18 — 客户端：界面对齐演示版 + DEMO 按键真功能（产品形态）
- LiveView 1:1 对齐筱雨演示版布局/尺寸/按键（顶栏/工作区栏/频道栏/频道头/Composer/插件栏/AI面板），暖色皮肤。
- 复刻 DEMO 弹窗真功能：商城/插件商城/资产/用户设置/个人主页/新建工作区/CLI/频道管理，按键接 composable。
- **决策**：`main.ts` 只载 tokens+reset 隔离演示组件全局 CSS（避免和 LiveView scoped 同名类撞、旧蓝色泄漏）；装 router 让 DepartmentCreateModal 的 useRouter 可用。

## 2026-06-18 — 宪法整理（CLAUDE.md / AGENTS.md）
- 修 `AGENTS.md` 被「Claude→Codex」盲替换搞坏的技术标识符：provider 值改回 `claude`、模型名改回 `claude-opus-4-8`、模型后端列表改回 Claude（这几处是会让人照抄后跑不起来的真 bug）。
- 品牌对齐：`AGENTS.md` 正文从旧品牌 **GuDuu** 同步到 **CosMac OS / CosMac Star**，错路径 `guduu/` 全部改为真实路径 `cosmac/`。
- **决策**：`CLAUDE.md`（给 Claude）与 `AGENTS.md`（给 Codex）双份同源——正文必须完全一致，**唯一允许的差异**是「AI 助手名字」（Claude vs Codex）和 §6.5 自引用指向各自文件名。注意区分：作为「AI 助手名」的 Claude 可换 Codex，作为「模型/provider」的 `claude` 绝不能换。
- 新增本 `DEVLOG.md`，并在两份宪法 §6.7 加规则：提交前更新本日志。
