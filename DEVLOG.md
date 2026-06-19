# CosMac OS — 开发日志 (Dev Log)

> 按时间倒序的开发流水：**每次 commit 前**在顶部加一条。
> 记「哪天 / 哪个模块 / 做了什么 / 关键决策与为什么」，不记文件级细节（那是 git log 的活），
> 也**不记敏感信息**（key/口令/线上 IP 进本机已 gitignore 的 `DEPLOY.md`）。
> 长期有用的事实进 memory；这里只是流水账。

---

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
