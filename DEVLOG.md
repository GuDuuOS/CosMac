# CosMac OS — 开发日志 (Dev Log)

> 按时间倒序的开发流水：**每次 commit 前**在顶部加一条。
> 记「哪天 / 哪个模块 / 做了什么 / 关键决策与为什么」，不记文件级细节（那是 git log 的活），
> 也**不记敏感信息**（key/口令/线上 IP 进本机已 gitignore 的 `DEPLOY.md`）。
> 长期有用的事实进 memory；这里只是流水账。

---

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
