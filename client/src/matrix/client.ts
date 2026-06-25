// CosMac 客户端的 Matrix 适配层：用 matrix-js-sdk 连 Synapse 后端。
// 能力：登录（带会话记忆，刷新不用重登）→ 同步 → 列频道 → 读消息（含 cosmac.card 富卡）→ 发消息。

// matrix-js-sdk 里有些代码引用了 node 风格的 global，浏览器里先补个垫片。
;(globalThis as any).global ||= globalThis

import { createClient, type MatrixClient } from 'matrix-js-sdk'

/** 给 UI 用的精简频道结构 */
export interface LiveRoom {
  id: string
  name: string
  /** 频道简介（Matrix m.room.topic），频道头展示用 */
  topic?: string
}

/** 给 UI 用的精简消息结构；card 为 cosmac.card 自定义富卡（可能没有） */
export interface LiveMsg {
  id: string
  sender: string
  senderName: string
  body: string
  ts: number
  card?: any
  /** 是否被编辑过（m.replace），显示"已编辑" */
  edited?: boolean
  /** 回复的目标消息（m.in_reply_to）：对方 id/名 + 正文预览 */
  replyToId?: string
  replyToSender?: string
  replyToName?: string
  replyToBody?: string
}

/** 一条消息上某个 emoji 的聚合反应 */
export interface ReactionAgg {
  key: string
  count: number
  mine: boolean
  myId?: string // 我那条 reaction 的 eventId（取消时 redact 用）
}

const SESSION_KEY = 'cosmac.session'
const SYNC_PREPARED_TIMEOUT_MS = 15000

// 单例：整个前端共用一个登录后的 Matrix client
let mx: MatrixClient | null = null

export function getClient(): MatrixClient | null {
  return mx
}

function saveSession(baseUrl: string, res: any): void {
  localStorage.setItem(
    SESSION_KEY,
    JSON.stringify({
      baseUrl,
      accessToken: res.access_token,
      userId: res.user_id,
      deviceId: res.device_id,
    }),
  )
}

async function startFrom(opts: {
  baseUrl: string
  accessToken: string
  userId: string
  deviceId?: string
}): Promise<string> {
  mx = createClient({
    baseUrl: opts.baseUrl,
    accessToken: opts.accessToken,
    userId: opts.userId,
    deviceId: opts.deviceId,
  })
  await mx.startClient({ initialSyncLimit: 30 })
  // 等首次同步完成（房间列表加载好）再返回，避免后续逻辑在空列表上重复建房间
  try {
    await new Promise<void>((resolve, reject) => {
      const client = mx as any
      let timer: number | null = null
      const cleanup = () => {
        if (timer !== null) window.clearTimeout(timer)
        client.off?.('sync', handler)
      }
      const fail = (reason: string) => {
        cleanup()
        reject(new Error(reason))
      }
      const handler = (state: string, _prev?: string, data?: any) => {
        if (state === 'PREPARED') {
          cleanup()
          resolve()
          return
        }
        if (state === 'ERROR' || state === 'STOPPED') {
          fail(data?.error?.message || `Matrix sync ${state}`)
        }
      }
      const currentState = client.getSyncState?.()
      if (currentState === 'PREPARED') {
        cleanup()
        resolve()
      }
      else if (currentState === 'ERROR' || currentState === 'STOPPED') {
        fail(`Matrix sync ${currentState}`)
      }
      else {
        timer = window.setTimeout(() => fail('Matrix sync timeout'), SYNC_PREPARED_TIMEOUT_MS)
        client.on('sync', handler)
      }
    })
  } catch (e) {
    try { mx?.stopClient() } catch { /* ignore */ }
    mx = null
    throw e
  }
  return opts.userId
}

/** 用用户名+密码登录，成功后记住会话。返回完整用户 id。 */
export async function login(
  baseUrl: string,
  user: string,
  password: string,
): Promise<string> {
  const tmp = createClient({ baseUrl })
  const res: any = await tmp.login('m.login.password', {
    identifier: { type: 'm.id.user', user },
    password,
    initial_device_display_name: 'CosMac Web',
  })
  saveSession(baseUrl, res)
  return startFrom({
    baseUrl,
    accessToken: res.access_token,
    userId: res.user_id,
    deviceId: res.device_id,
  })
}

/**
 * 注册新账号（用户名+密码），成功后直接登录并记住会话。返回完整用户 id。
 *
 * 走 Matrix 标准注册 + UIA（user-interactive auth）：
 *  1) 先不带 auth 发一次 → 服务器返回 401 + flows + session（这是 UIA 协议，不是失败）。
 *  2) 若服务器开放注册、流程只需 `m.login.dummy`（无邮箱/验证码）→ 带 dummy 再发一次完成注册。
 *  3) 若服务器要求邮箱/验证码/注册令牌等额外步骤 → 这里给不出，抛友好错误（让用户走管理员开号）。
 *
 * 前提：服务器需 `enable_registration: true`（且未强制额外验证）。否则会收到 M_FORBIDDEN。
 */
export async function register(
  baseUrl: string,
  user: string,
  password: string,
): Promise<string> {
  const tmp = createClient({ baseUrl })
  const doReq = (auth?: any) =>
    (tmp as any).registerRequest({
      username: user,
      password,
      auth,
      initial_device_display_name: 'CosMac Web',
    })

  let res: any
  try {
    // 第一次通常会 401（UIA 要 session）；若服务器允许无 UIA 注册则可能直接成功
    res = await doReq()
  } catch (e: any) {
    const data = e?.data
    if (e?.httpStatus === 401 && data?.session) {
      const flows: any[] = Array.isArray(data.flows) ? data.flows : []
      // 只接受「只需 dummy」的开放注册；要邮箱/验证码/令牌的流程不在此处理
      const dummyOk = flows.some((f) => Array.isArray(f.stages) && f.stages.includes('m.login.dummy'))
      if (dummyOk) {
        res = await doReq({ type: 'm.login.dummy', session: data.session })
      } else {
        throw new Error('该服务器的注册需要额外验证（邮箱/验证码/邀请码），暂无法在此直接注册')
      }
    } else if (e?.errcode === 'M_USER_IN_USE') {
      throw new Error('该用户名已被占用，请换一个')
    } else if (e?.errcode === 'M_FORBIDDEN') {
      throw new Error('服务器未开放注册，请联系管理员开通账号')
    } else {
      throw e
    }
  }

  saveSession(baseUrl, res)
  return startFrom({
    baseUrl,
    accessToken: res.access_token,
    userId: res.user_id,
    deviceId: res.device_id,
  })
}

/** 尝试用上次记住的会话恢复登录；没有/失效返回 null。 */
export async function restoreSession(): Promise<string | null> {
  const raw = localStorage.getItem(SESSION_KEY)
  if (!raw) return null
  try {
    const s = JSON.parse(raw)
    return await startFrom(s)
  } catch {
    localStorage.removeItem(SESSION_KEY)
    return null
  }
}

/** 退出登录、清掉记住的会话，并尽力撤销服务端 access token。 */
export async function logout(): Promise<void> {
  const cur = mx
  try {
    await (cur as any)?.logout?.()
  } catch {
    /* ignore */
  } finally {
    localStorage.removeItem(SESSION_KEY)
    try {
      cur?.stopClient()
    } catch {
      /* ignore */
    }
    if (mx === cur) mx = null
  }
}

/** 注册"有更新就回调"——同步完成或来新消息时触发，UI 据此刷新。
 *
 * 关键：登录/重连的**初始同步**会把一批历史消息逐条灌进时间线，`Room.timeline`
 * 因此密集触发；若每条都立刻 refresh，历史消息就会"一条一条蹦出来"。这里做个
 * 80ms 短防抖：把这一**批**密集事件合并成**一次**渲染——历史整批瞬间出现；
 * 而真正的新消息（彼此间隔远大于 80ms）仍各自触发一次，逐条自然出现。 */
export function onUpdate(cb: () => void): void {
  if (!mx) return
  let timer: number | null = null
  const fire = () => {
    if (timer !== null) clearTimeout(timer)
    timer = window.setTimeout(() => { timer = null; cb() }, 80)
  }
  ;(mx as any).on('sync', (state: string) => {
    if (state === 'PREPARED' || state === 'SYNCING') fire()
  })
  ;(mx as any).on('Room.timeline', () => fire())
}

/** 列出我加入的群频道（排除 Space 空间本身、"中枢 AI"私聊和无名 DM；按名称排序）。 */
/** 读房间简介（m.room.topic 状态事件 → topic）。 */
function roomTopic(room: any): string | undefined {
  const ev = room?.currentState?.getStateEvents?.('m.room.topic', '')
  return ev?.getContent?.()?.topic || undefined
}

export function listRooms(): LiveRoom[] {
  if (!mx) return []
  return mx
    .getRooms()
    // Space（工作区）本身不是频道，不进频道列表
    .filter((r) => !(r as any).isSpaceRoom?.())
    .map((r) => ({ id: r.roomId, name: r.name || r.roomId, topic: roomTopic(r) }))
    // 中枢 AI 在右侧单独显示；无名 DM 的 name 会回退成对方 mxid（以 @ 开头），都不进频道列表
    .filter((r) => r.name !== '中枢 AI' && !r.name.startsWith('@'))
    .sort((a, b) => a.name.localeCompare(b.name, 'zh'))
}

/** 给 UI 用的工作区（Matrix Space）结构 */
export interface LiveSpace {
  id: string
  name: string
  /** 左栏图标的自定义简称（存在 cosmac.workspace 状态事件里；没有就由 UI 取名字前 2 字） */
  label?: string
  /** 工作区头像（m.room.avatar）转好的 http 地址；有图就用图、没图用简称文字 */
  avatarUrl?: string
  /** 排序序号（存在 cosmac.workspace.order；和名字无关，改名不影响顺序） */
  order?: number
}

/** 读某个 Space 的 cosmac.workspace 元数据（简称 label + 排序 order）。 */
function spaceMeta(room: any): { label?: string; order?: number } {
  const c = room?.currentState?.getStateEvents?.('cosmac.workspace', '')?.getContent?.() || {}
  return {
    label: c.label || undefined,
    order: typeof c.order === 'number' ? c.order : undefined,
  }
}

/** mxc:// 转成可显示的 http 地址（走 /_matrix/media，已被 nginx 代理）。 */
export function mxcToHttp(mxc: string, size = 64): string {
  if (!mx || !mxc) return ''
  return (mx as any).mxcUrlToHttp?.(mxc, size, size, 'crop') || ''
}

/** 读某个 Space 的头像（m.room.avatar → mxc → http）。 */
function spaceAvatar(room: any): string | undefined {
  const ev = room?.currentState?.getStateEvents?.('m.room.avatar', '')
  const url = ev?.getContent?.()?.url
  return url ? mxcToHttp(url, 48) : undefined
}

/** 上传一张图片到 Matrix 媒体库，返回 mxc:// 地址。 */
export async function uploadMedia(file: File): Promise<string> {
  if (!mx) throw new Error('未登录')
  const res: any = await (mx as any).uploadContent(file, { type: file.type })
  return res?.content_uri || res?.contentUri || ''
}

/** 列出我加入的工作区（Space），按名称排序。 */
export function listSpaces(): LiveSpace[] {
  if (!mx) return []
  return mx
    .getRooms()
    .filter((r) => (r as any).isSpaceRoom?.())
    .map((r) => {
      const m = spaceMeta(r)
      return { id: r.roomId, name: r.name || r.roomId, label: m.label, order: m.order, avatarUrl: spaceAvatar(r) }
    })
    // 稳定排序：先按 order（没有的排后面），同 order 再按名字。改名不影响顺序。
    .sort((a, b) => (a.order ?? 1e9) - (b.order ?? 1e9) || a.name.localeCompare(b.name, 'zh'))
}

/** 取某个工作区(Space)下挂的频道 roomId 集合（读 m.space.child 状态事件）。 */
export function roomIdsInSpace(spaceId: string): Set<string> {
  const ids = new Set<string>()
  const space = mx?.getRoom(spaceId)
  if (!space) return ids
  const evs = (space as any).currentState?.getStateEvents?.('m.space.child') || []
  for (const ev of evs) {
    const child = ev.getStateKey?.()
    const via = ev.getContent?.()?.via
    // via 为空 = 该子关系已被撤销
    if (child && via && via.length) ids.add(child)
  }
  return ids
}

/** 真建一个工作区（Matrix Space）。opts.public=公开可加入；opts.label=左栏简称。返回 room_id。 */
export async function createSpace(
  name: string,
  opts: { public?: boolean; label?: string } = {},
): Promise<string> {
  if (!mx) throw new Error('未登录')
  const res: any = await mx.createRoom({
    name,
    preset: (opts.public ? 'public_chat' : 'private_chat') as any,
    creation_content: { type: 'm.space' } as any,
  })
  const sid = res.room_id
  // 简称 + 排序序号存进 cosmac.workspace 状态。order 取现有工作区最大值+1（排到末尾）。
  try {
    const orders = listSpaces().map((s) => s.order).filter((n): n is number => typeof n === 'number')
    const nextOrder = (orders.length ? Math.max(...orders) : -1) + 1
    await (mx as any).sendStateEvent(sid, 'cosmac.workspace', { label: opts.label || '', order: nextOrder }, '')
  } catch { /* 存元数据失败不影响主流程 */ }
  return sid
}

/** 退出并遗忘一个房间/工作区（leave + forget）。用于"删除工作区/频道"（客户端能做的是退出）。 */
export async function leaveAndForget(roomId: string): Promise<void> {
  if (!mx) throw new Error('未登录')
  await mx.leave(roomId)
  try { await (mx as any).forget(roomId) } catch { /* forget 失败不影响已退出 */ }
}

/** 改工作区(Space)的名称 / 简称。name→m.room.name；label→cosmac.workspace 状态。 */
export async function updateSpace(
  spaceId: string,
  opts: { name?: string; label?: string; avatar?: string; order?: number } = {},
): Promise<void> {
  if (!mx) throw new Error('未登录')
  if (opts.name) {
    await (mx as any).sendStateEvent(spaceId, 'm.room.name', { name: opts.name }, '')
  }
  // label / order 合并写进同一个 cosmac.workspace 状态（避免互相覆盖）
  if (opts.label !== undefined || opts.order !== undefined) {
    const cur = mx.getRoom(spaceId)?.currentState?.getStateEvents('cosmac.workspace', '')?.getContent() || {}
    const next: any = { ...cur }
    if (opts.label !== undefined) next.label = opts.label
    if (opts.order !== undefined) next.order = opts.order
    await (mx as any).sendStateEvent(spaceId, 'cosmac.workspace', next, '')
  }
  // avatar：undefined=不动；''=清空头像；mxc://=设置头像
  if (opts.avatar !== undefined) {
    await (mx as any).sendStateEvent(spaceId, 'm.room.avatar', opts.avatar ? { url: opts.avatar } : {}, '')
  }
}

/** 改频道的名称 / 简介。name→m.room.name；topic→m.room.topic。 */
export async function updateRoom(
  roomId: string,
  opts: { name?: string; topic?: string } = {},
): Promise<void> {
  if (!mx) throw new Error('未登录')
  if (opts.name) {
    await (mx as any).sendStateEvent(roomId, 'm.room.name', { name: opts.name }, '')
  }
  if (opts.topic !== undefined) {
    await (mx as any).sendStateEvent(roomId, 'm.room.topic', { topic: opts.topic }, '')
  }
}

/* ===== 频道级 CosMac 配置（频道管理面板：人设/模型/规则等）=====
 * 存成每频道一条自定义 state event `cosmac.channel_config`（与 cosmac.workspace 同套命名）。
 * 选 state event 而非 account data：群级共享（所有成员/多端一致）、留在房间里、不改 Synapse 核心。
 * 写需要发状态事件的权限（房间 state_default，一般管理员），普通成员写会被服务器拒（M_FORBIDDEN）。
 */
const CHANNEL_CONFIG_EVENT = 'cosmac.channel_config'

/** 读某频道的 CosMac 配置内容；无则返回空对象 {}。 */
export function getChannelConfig(roomId: string): Record<string, any> {
  const room = mx?.getRoom(roomId)
  const ev = room?.currentState?.getStateEvents?.(CHANNEL_CONFIG_EVENT, '')
  return ev?.getContent?.() || {}
}

/** 写某频道配置：读旧内容 merge 进 patch 再整体写回（保留其它键，便于逐标签页增量接入）。 */
export async function setChannelConfig(roomId: string, patch: Record<string, any>): Promise<void> {
  if (!mx) throw new Error('未登录')
  const next = { ...getChannelConfig(roomId), ...patch }
  await (mx as any).sendStateEvent(roomId, CHANNEL_CONFIG_EVENT, next, '')
}

/* ===== 看板数据源（数据看板 / 任务看板的数据源配置）=====
 * 按工作区(Space)存一条 state event `cosmac.board_sources`，内容 { dashboard: [...], tasks: [...] }。
 * 数据源目前是配置占位（名称/类型/备注），真实取数以后接。Space 本身也是 Matrix 房间，复用 state event。
 */
const BOARD_SOURCES_EVENT = 'cosmac.board_sources'

/** 读某工作区的看板数据源配置；无则返回空对象 {}。 */
export function getBoardSources(spaceId: string): Record<string, any> {
  const room = mx?.getRoom(spaceId)
  const ev = room?.currentState?.getStateEvents?.(BOARD_SOURCES_EVENT, '')
  return ev?.getContent?.() || {}
}

/** 写某工作区的看板数据源配置（整体覆盖；需该 Space 发状态事件的权限）。 */
export async function setBoardSources(spaceId: string, data: Record<string, any>): Promise<void> {
  if (!mx) throw new Error('未登录')
  await (mx as any).sendStateEvent(spaceId, BOARD_SOURCES_EVENT, data, '')
}

/* ===== 社媒数据源（数据看板真实取数的配置）=====
 * 按工作区(Space)存一条 state event `cosmac.social_sources`，内容 { sources: SocialSource[] }。
 * 设计要点（与模块3 工作流连接器同构）：
 *  · 定义（平台/账号/模式/凭据名/间隔）存这里——浏览器够不到 DB，走 Matrix state event、多端同步。
 *  · 凭据本身（API key/token/cookie）只进**服务端 env** `COSMAC_SOCIAL_<平台>_<字段>`，定义里只放凭据**名**。
 *  · 运行态（lastSync/lastStatus）由后端采集器回写，前端只读。
 * P1 只落「读写配置」；真实取数（采集器/工作流/写 DB）是 P2~P4，见 DEVLOG/CLAUDE.md 路线图。
 */
const SOCIAL_SOURCES_EVENT = 'cosmac.social_sources'

/** 读某工作区的社媒数据源配置；无则返回 { sources: [] }。 */
export function getSocialSources(spaceId: string): Record<string, any> {
  const room = mx?.getRoom(spaceId)
  const ev = room?.currentState?.getStateEvents?.(SOCIAL_SOURCES_EVENT, '')
  return ev?.getContent?.() || {}
}

/** 写某工作区的社媒数据源配置（整体覆盖；需该 Space 发状态事件的权限）。 */
export async function setSocialSources(spaceId: string, data: Record<string, any>): Promise<void> {
  if (!mx) throw new Error('未登录')
  await (mx as any).sendStateEvent(spaceId, SOCIAL_SOURCES_EVENT, data, '')
}

/* ===== 首次引导标记（per-account）=====
 * 存在**每账号 account data** `cosmac.onboarding`，内容 { done: boolean, ts }。
 * 用 account data 而非"有没有工作区"来判首次——更可靠（用户删光工作区也不会被反复引导），
 * 且每账号自动多端同步、零新基建（符合 CLAUDE.md 存储表「每账号轻量配置」走 account data）。
 */
const ONBOARDING_ACCOUNT_DATA = 'cosmac.onboarding'

/** 是否已完成首次引导。读不到（新号/没写过）→ false。 */
export function isOnboarded(): boolean {
  try {
    const c = (mx as any)?.getAccountData?.(ONBOARDING_ACCOUNT_DATA)?.getContent?.() || {}
    return !!c.done
  } catch {
    return false
  }
}

/** 标记首次引导已完成（含跳过）。 */
export async function setOnboarded(done = true): Promise<void> {
  if (!mx) throw new Error('未登录')
  await (mx as any).setAccountData(ONBOARDING_ACCOUNT_DATA, { done, ts: Date.now() })
}

/** 在某工作区(Space)下真建一个频道：建房间 + 邀请主 AI + 挂到 Space 下。返回 room_id。 */
export async function createChannelInSpace(
  spaceId: string,
  name: string,
  opts: { public?: boolean; topic?: string } = {},
): Promise<string> {
  if (!mx) throw new Error('未登录')
  const res: any = await mx.createRoom({
    name,
    topic: opts.topic || undefined, // 频道简介
    preset: (opts.public ? 'public_chat' : 'private_chat') as any,
    invite: [botId()], // 拉主 AI 进群，频道里 AI 能回
  })
  const cid = res.room_id
  // 双向挂接：Space 记子频道，子频道指回父 Space
  try {
    await (mx as any).sendStateEvent(spaceId, 'm.space.child', { via: ['cosmac.cc'] }, cid)
    await (mx as any).sendStateEvent(cid, 'm.space.parent', { via: ['cosmac.cc'], canonical: true }, spaceId)
  } catch { /* 挂接失败也已建好房间 */ }
  return cid
}

/** 本服务器域名（从当前用户 id 取，如 @admin:cosmac.cc → cosmac.cc）。 */
export function serverName(): string {
  return (mx?.getUserId() || '').split(':')[1] || 'cosmac.cc'
}

/** 把"用户名"或"@用户名"规范成完整 Matrix id（@用户名:本服务器）。 */
export function normalizeUserId(input: string): string {
  const s = input.trim()
  if (!s) return ''
  if (s.startsWith('@')) return s
  return `@${s.replace(/^@/, '')}:${serverName()}`
}

/** 这个房间是否被收藏（Matrix 标准 m.favourite 标签）。 */
export function isFavourite(roomId: string): boolean {
  return !!mx?.getRoom(roomId)?.tags?.['m.favourite']
}

/** 设置/取消收藏（写 m.favourite 标签，per-room、跨设备同步）。 */
export async function setFavourite(roomId: string, on: boolean): Promise<void> {
  if (!mx) throw new Error('未登录')
  if (on) await (mx as any).setRoomTag(roomId, 'm.favourite', {})
  else await (mx as any).deleteRoomTag(roomId, 'm.favourite')
}

/** 读某个房间的真实成员（已加入的）。返回 {id, name, isBot}。 */
export function listRoomMembers(roomId: string): { id: string; name: string; isBot: boolean }[] {
  const room = mx?.getRoom(roomId)
  if (!room) return []
  return room.getJoinedMembers().map((m: any) => ({
    id: m.userId,
    name: m.name || m.userId,
    isBot: m.userId === botId(),
  }))
}

/** 频道管理「人员」标签用的成员（含头像/角色/在不在群） */
export interface ChannelMember {
  id: string              // 完整 Matrix 用户 id，如 @alice:cosmac.cc
  name: string            // 显示名（没设昵称就退回用户名段）
  avatar: string          // http 头像地址；没有则空串（UI 退回首字母圆头像）
  isBot: boolean          // 是否中枢 AI（按 botId() 判定，UI 标 APP）
  role: 'owner' | 'admin' | 'member'  // 由 m.room.power_levels 推出：100=owner，≥50=admin，其余 member
  roleLabel: string       // 角色中文标签：群主 / 管理员 / 成员
  power: number           // 原始 power level 数值（移除/降权判断用）
  pending: boolean        // true=已邀请但还没加入（invite 态）
}

/** power level → 角色（与 Matrix 默认 100/50 阈值一致） */
function roleOfPower(power: number): { role: ChannelMember['role']; roleLabel: string } {
  if (power >= 100) return { role: 'owner', roleLabel: '群主' }
  if (power >= 50) return { role: 'admin', roleLabel: '管理员' }
  return { role: 'member', roleLabel: '成员' }
}

/**
 * 读频道真实成员（频道管理「人员」标签用）。
 * 已加入(join) + 已邀请待入(invite) 都返回；invite 的标 pending。
 * 头像取 m.room.member 里的 avatar_url(mxc) 转 http；角色由房间 power_levels 推出。
 * 排序：群主 > 管理员 > 成员，bot 排在同级末尾，便于 UI 展示。
 */
export function listChannelMembers(roomId: string): ChannelMember[] {
  const room = mx?.getRoom(roomId)
  if (!room) return []
  // power_levels 状态事件：users 字典存了每个被显式赋权的用户的 power
  const plContent = room.currentState?.getStateEvents?.('m.room.power_levels', '')?.getContent?.() || {}
  const usersPower: Record<string, number> = plContent.users || {}
  const defaultPower: number = plContent.users_default ?? 0
  // join + invite 两种状态都算"频道成员"
  const raw = room.getMembersWithMembership?.('join') || room.getJoinedMembers() || []
  const invited = room.getMembersWithMembership?.('invite') || []
  const all = [...raw, ...invited]
  const out: ChannelMember[] = all.map((m: any) => {
    const power = usersPower[m.userId] ?? defaultPower
    const { role, roleLabel } = roleOfPower(power)
    const mxc = m.getMxcAvatarUrl?.() || m.events?.member?.getContent?.()?.avatar_url || ''
    // js-sdk 在没设昵称时把 name 填成完整 userId（@guduu:cosmac.cc），显示难看；
    // 这种情况退回用 id 的 localpart（@后、:前那段），仍是真实信息、只是更干净。
    const localpart = m.userId.replace(/^@/, '').split(':')[0]
    const name = (!m.name || m.name === m.userId) ? localpart : m.name
    return {
      id: m.userId,
      name,
      avatar: mxc ? mxcToHttp(mxc, 64) : '',
      isBot: m.userId === botId(),
      role,
      roleLabel,
      power,
      pending: m.membership === 'invite',
    }
  })
  // 排序：power 高在前；同 power 时真人优先于 bot、再按名字
  return out.sort((a, b) => b.power - a.power || Number(a.isBot) - Number(b.isBot) || a.name.localeCompare(b.name))
}

/** 邀请一个已有用户进某频道（标准 Matrix 邀请）。 */
export async function inviteToRoom(roomId: string, userId: string): Promise<void> {
  if (!mx) throw new Error('未登录')
  await mx.invite(roomId, userId)
}

/**
 * 把某用户移出频道（标准 Matrix kick）。需当前登录者 power 足够（一般是管理员）。
 * 注：kick 只是踢出当前房间，不删账号；被踢者可被再次邀请。
 */
export async function kickFromRoom(roomId: string, userId: string, reason?: string): Promise<void> {
  if (!mx) throw new Error('未登录')
  await (mx as any).kick(roomId, userId, reason)
}

/**
 * 用 Synapse Admin API 新建一个账号（需当前登录者是服务器管理员，如 @admin）。
 * 返回完整用户 id。失败抛错（含状态码/原因）。
 */
export async function createUser(
  username: string,
  password: string,
  displayname?: string,
): Promise<string> {
  if (!mx) throw new Error('未登录')
  const uid = normalizeUserId(username)
  const base = (mx as any).baseUrl as string
  const token = (mx as any).getAccessToken?.() as string
  const res = await fetch(`${base}/_synapse/admin/v2/users/${encodeURIComponent(uid)}`, {
    method: 'PUT',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ password, displayname: displayname || username, admin: false }),
  })
  if (!res.ok) {
    let msg = `${res.status}`
    try { msg = (await res.json())?.error || msg } catch { /* ignore */ }
    throw new Error(`建账号失败：${msg}`)
  }
  return uid
}

/* ========================================================================
 *  平台管理后台（/admin）—— 用户管理
 *  全部走 Synapse Admin API（/_synapse/admin/...），用当前登录管理员的 token。
 *  需当前账号是服务器管理员（@admin 之类）；非管理员调用会被 Synapse 拒（403）。
 * ===================================================================== */

/** 统一的 Admin API 请求封装：自动带上 base 地址与管理员 token，出错抛带原因的错误。 */
async function adminFetch(path: string, init: RequestInit = {}): Promise<any> {
  if (!mx) throw new Error('未登录')
  const base = (mx as any).baseUrl as string
  const token = (mx as any).getAccessToken?.() as string
  const res = await fetch(`${base}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
      ...(init.headers || {}),
    },
  })
  if (!res.ok) {
    let msg = `${res.status}`
    try { msg = (await res.json())?.error || msg } catch { /* ignore */ }
    throw new Error(msg)
  }
  // 有些 Admin 端点回空体，容错处理
  try { return await res.json() } catch { return {} }
}

/** 管理后台用的精简用户结构 */
export interface AdminUser {
  id: string            // 完整 id，如 @alice:cosmac.cc
  name: string          // 显示名（没设就退回 localpart）
  admin: boolean        // 是否服务器管理员
  deactivated: boolean  // 是否已停用
  isBot: boolean        // 是否中枢 AI（按 botId() 判定）
}

/**
 * 当前登录者是否服务器管理员。
 * 非管理员访问 /admin 时用它挡回。查询失败（如 403）一律按"不是管理员"处理。
 */
export async function isServerAdmin(): Promise<boolean> {
  try {
    const uid = mx?.getUserId() || ''
    const data = await adminFetch(`/_synapse/admin/v1/users/${encodeURIComponent(uid)}/admin`)
    return !!data.admin
  } catch {
    return false
  }
}

/**
 * 拉全部用户列表（Synapse Admin API v2，自动翻页直到取完）。
 * guests=false 不含访客；deactivated=true 连已停用的也返回（后台要能看到并恢复）。
 */
export async function listUsers(): Promise<AdminUser[]> {
  const out: AdminUser[] = []
  let from = 0
  const limit = 100
  // Synapse 用 next_token 分页；没有 next_token 表示取完了
  for (let guard = 0; guard < 100; guard++) {
    const data = await adminFetch(
      `/_synapse/admin/v2/users?from=${from}&limit=${limit}&guests=false&deactivated=true`,
    )
    for (const u of data.users || []) {
      const localpart = (u.name || '').replace(/^@/, '').split(':')[0]
      out.push({
        id: u.name,
        name: u.displayname || localpart,
        admin: !!u.admin,
        deactivated: !!u.deactivated,
        isBot: u.name === botId(),
      })
    }
    if (data.next_token === undefined || data.next_token === null) break
    from = Number(data.next_token)
  }
  return out
}

/**
 * 停用某账号（POST deactivate）。erase=false 只停用、不抹除内容（可恢复账号本身）。
 * 注意：停用是软删除——账号不能再登录，但 id 仍占用。
 */
export async function deactivateUser(userId: string): Promise<void> {
  await adminFetch(`/_synapse/admin/v1/deactivate/${encodeURIComponent(userId)}`, {
    method: 'POST',
    body: JSON.stringify({ erase: false }),
  })
}

/**
 * 恢复一个已停用的账号：Synapse 要求"恢复"时必须同时设一个新密码。
 * 用 PUT users 把 deactivated 置回 false 并写入新密码。
 */
export async function reactivateUser(userId: string, newPassword: string): Promise<void> {
  await adminFetch(`/_synapse/admin/v2/users/${encodeURIComponent(userId)}`, {
    method: 'PUT',
    body: JSON.stringify({ deactivated: false, password: newPassword }),
  })
}

/** 给某账号重置密码；logout_devices=true 同时把该用户已登录的设备全部踢下线。 */
export async function resetPassword(userId: string, newPassword: string): Promise<void> {
  await adminFetch(`/_synapse/admin/v1/reset_password/${encodeURIComponent(userId)}`, {
    method: 'POST',
    body: JSON.stringify({ new_password: newPassword, logout_devices: true }),
  })
}

/**
 * 设/撤某账号的服务器管理员权限（PUT users 的 admin 字段）。
 * 返回值：控制室「期望管理员集」是否成功同步——false 表示**主 AI 还没收到新期望、
 * 撤销者可能仍有 AI 配置写权限**，调用方应据此告警（绝不静默报全成）。
 */
export async function setUserAdmin(userId: string, admin: boolean): Promise<boolean> {
  await adminFetch(`/_synapse/admin/v2/users/${encodeURIComponent(userId)}`, {
    method: 'PUT',
    body: JSON.stringify({ admin }),
  })
  // 控制室成员随服务器管理员身份联动。关键：**真正的移除交给 power=100 的主 AI**，
  // 浏览器只“提交期望”——因为同级(50)管理员之间互相无法降权/踢出，前端做不到可靠移除。
  // 服务器管理员身份已经改成功（不回滚）；这里只报告控制室同步成没成。
  try {
    await syncControlRoomAdmins()
    return true
  } catch {
    return false // 期望集没写进控制室 → 主 AI 不会对齐，需调用方提示重试
  }
}

/**
 * 把「当前服务器管理员集」写进控制室的 cosmac.ctrl.admins 状态事件，并尽力即时对齐。
 *
 * 设计（守住「撤权后真的失去配置写权限」这条线）：
 *  - 浏览器只**声明期望**（管理员 power=50 足够写这个 state event）；
 *  - 拥有 power=100 的**主 AI(bot)** 读到后强制对齐控制室成员：降权 + 踢出不在期望集里的人。
 *    这绕过了「50 无法移除 50」的 Matrix 约束，撤权后约 1 个事件往返内即生效。
 *  - 同时做一次**前端尽力**：ensureControlRoom 邀请/提权在场管理员（即时可见），但不依赖它。
 */
async function syncControlRoomAdmins(): Promise<void> {
  if (!mx) return
  // 当前服务器管理员集（未停用的）
  const desired = (await listUsers())
    .filter((u) => u.admin && !u.deactivated)
    .map((u) => u.id)
  // 建房（首次）+ 邀请/提权在场管理员（尽力即时生效，bot 随后也会兜底对齐）
  const rid = await ensureControlRoom()
  // 写「期望管理员集」——主 AI 据此踢出被撤销者（前端无权踢同级，这步才是可靠保证）
  await (mx as any).sendStateEvent(rid, CONTROL_ADMINS_EVENT_TYPE, { admins: desired }, '')
}

/* =====================================================================
 *  管理后台 · 频道/群管理（Synapse Admin Rooms API）
 *  和用户管理一样走 /_synapse/admin/...，需服务器管理员 token。
 *  注意：这里列的是「整台服务器上的所有房间」，不同于侧栏只列「我加入的」。
 * ===================================================================== */

/** 管理后台用的精简房间结构 */
export interface AdminRoom {
  id: string                 // room_id，如 !abc:cosmac.cc
  name: string               // 房间名（没设名就退回别名或 room_id）
  alias: string | null       // 规范别名 #xxx:host（可能没有）
  members: number            // 已加入成员数
  localMembers: number       // 本服成员数
  isPublic: boolean          // 是否公开可加入（join_rules=public）
  encrypted: boolean         // 是否端到端加密
  creator: string | null     // 创建者 user_id
}

/**
 * 拉全服房间列表（Admin API v1 /rooms，自动翻页取完）。
 * 默认按成员数倒序，人多的群排前面。
 */
export async function listAdminRooms(): Promise<AdminRoom[]> {
  const out: AdminRoom[] = []
  let from = 0
  const limit = 100
  for (let guard = 0; guard < 100; guard++) {
    const data = await adminFetch(
      `/_synapse/admin/v1/rooms?from=${from}&limit=${limit}&order_by=joined_members&dir=b`,
    )
    for (const r of data.rooms || []) {
      out.push({
        id: r.room_id,
        name: r.name || r.canonical_alias || r.room_id,
        alias: r.canonical_alias || null,
        members: r.joined_members ?? 0,
        localMembers: r.joined_local_members ?? 0,
        // join_rules 为 "public" 即公开；其余（invite/knock…）按私有处理
        isPublic: r.join_rules === 'public',
        encrypted: !!r.encryption,
        creator: r.creator || null,
      })
    }
    // Admin rooms API 用 next_batch 翻页；没有就取完了
    if (data.next_batch === undefined || data.next_batch === null) break
    from = Number(data.next_batch)
  }
  return out
}

/** 查 Synapse 服务端版本（数据概览页展示用）。失败返回空串、不阻断页面。 */
export async function getServerVersion(): Promise<string> {
  try {
    const data = await adminFetch('/_synapse/admin/v1/server_version')
    return data.server_version || ''
  } catch {
    return ''
  }
}

/** 查某房间的已加入成员 id 列表（Admin API）。 */
export async function getRoomMembers(roomId: string): Promise<string[]> {
  const data = await adminFetch(
    `/_synapse/admin/v1/rooms/${encodeURIComponent(roomId)}/members`,
  )
  return (data.members || []) as string[]
}

/**
 * 删除（并清除）一个房间。
 * @param block true=封禁该房间，禁止任何人重新加入/重建（用于违规群）；false=仅删除。
 * Synapse 会把所有本服成员踢出、purge 历史。该操作不可逆，调用前务必确认。
 */
export async function deleteRoom(roomId: string, block = false): Promise<void> {
  await adminFetch(`/_synapse/admin/v1/rooms/${encodeURIComponent(roomId)}`, {
    method: 'DELETE',
    body: JSON.stringify({ block, purge: true }),
  })
}

/* =====================================================================
 *  管理后台 · AI 配置（运行时下发给主 AI bot）
 *  存储：一个"控制室"（别名 #cosmac-ctrl:<server>）里的 state event
 *  `cosmac.ai.config`。管理后台（管理员）写，bot 运行时读并热应用。
 *  走标准 Matrix C-S API（不是 Admin API）：管理员是房间创建者，有权写 state。
 * ===================================================================== */

/** 控制室里 AI 配置 state event 的类型（与 bot 端 AI_CONFIG_EVENT_TYPE 一致）。 */
const AI_CONFIG_EVENT_TYPE = 'cosmac.ai.config'
/** 控制室里「期望服务器管理员集」state event 的类型（与 bot 端 CONTROL_ADMINS_EVENT_TYPE 一致）。
 *  浏览器写期望（管理员 power=50 够写 state），主 AI(power=100) 读到后对齐成员、踢出被撤销者。 */
const CONTROL_ADMINS_EVENT_TYPE = 'cosmac.ctrl.admins'
/** 控制室别名 localpart（#cosmac-ctrl:<server>）。 */
const CONTROL_ROOM_LOCALPART = 'cosmac-ctrl'
/** 控制室里「全局技能」state event 的类型（与 bot 端 SKILLS_EVENT_TYPE 一致）。
 *  管理后台写、主 AI 读；应用于所有群。群级/个人技能走聊天命令存 cosmac DB，不在这。 */
const SKILLS_EVENT_TYPE = 'cosmac.skills'
/** 控制室里「全局智能体(Agent)」state event 的类型（与 bot 端 AGENTS_EVENT_TYPE 一致）。 */
const AGENTS_EVENT_TYPE = 'cosmac.agents'
/** 控制室里「全局规则(Rule)」state event 的类型（与 bot 端 RULES_EVENT_TYPE 一致）。 */
const RULES_EVENT_TYPE = 'cosmac.rules'
/** 控制室里「工作流连接器」state event 的类型（与 bot 端 WORKFLOWS_EVENT_TYPE 一致）。 */
const WORKFLOWS_EVENT_TYPE = 'cosmac.workflows'
/** 旧版会员聚合事件，仅用于读取已有数据。 */
const MEMBERS_EVENT_TYPE = 'cosmac.members'
/** 新版单用户会员事件：state_key=userId，避免并发覆盖和事件容量上限。 */
const MEMBER_EVENT_TYPE = 'cosmac.member'

/** 主 AI 可用工具目录（工具开关 UI 用；name 要与 bot 端 Toolbox 注册的一致）。 */
export const AI_TOOL_CATALOG: { name: string; label: string }[] = [
  { name: 'create_room', label: '建群/开专班' },
  { name: 'send_message_to_room', label: '往房间发消息' },
  { name: 'list_room_members', label: '查看房间成员' },
  { name: 'get_recent_messages', label: '读取聊天记录' },
  { name: 'run_workflow', label: '跑外部工作流(n8n/Make 等)' },
]

/** 可选的模型后端目录（管理后台「AI 配置」的 provider 下拉用）。
 *  value '' = 用服务器环境变量启动配置（不在网页改 provider）。
 *  其余四家：填对应 API Key + 模型 id 即可在网页切换、热生效。 */
export const AI_PROVIDERS: {
  value: string
  label: string
  keyLabel: string
  modelPlaceholder: string
}[] = [
  { value: '', label: '默认（用服务器配置）', keyLabel: '', modelPlaceholder: '留空＝服务器默认' },
  { value: 'deepseek', label: 'DeepSeek（火山方舟）', keyLabel: '方舟 API Key', modelPlaceholder: '如 deepseek-v3.2 或 ep-… 接入点' },
  { value: 'claude', label: 'Claude（Anthropic）', keyLabel: 'Anthropic API Key', modelPlaceholder: '默认 claude-opus-4-8' },
  { value: 'openai', label: 'ChatGPT（OpenAI）', keyLabel: 'OpenAI API Key', modelPlaceholder: '默认 gpt-4o' },
  { value: 'gemini', label: 'Gemini（Google）', keyLabel: 'Google API Key', modelPlaceholder: '默认 gemini-2.0-flash' },
]

/** 管理后台编辑的 AI 配置。provider='' 表示用服务器环境变量；enabled_tools=null=全部启用。
 *  注意：**不含 API Key**——密钥只在服务端配（环境变量/Secret Manager），绝不写进
 *  Matrix 事件（state event 无法加密，会明文进 DB/历史/被全员可读）。 */
export interface AiConfig {
  provider: string
  model: string
  system_prompt: string
  enabled_tools: string[] | null
}

/** 解析控制室别名 → room_id；不存在返回 null。 */
async function resolveControlRoom(): Promise<string | null> {
  if (!mx) return null
  const alias = `#${CONTROL_ROOM_LOCALPART}:${serverName()}`
  try {
    const r = await (mx as any).getRoomIdForAlias(alias)
    return r?.room_id || null
  } catch (e: any) {
    if (e?.errcode === 'M_NOT_FOUND') return null // 明确不存在，才允许后续创建
    throw e // 网络/权限/服务器错误不能伪装成“不存在”
  }
}

// —— 控制室权限模型 ——
// 只保留**一个所有者**（建房者）= 100，独一份；普通服务器管理员 = ADMIN（50）：
// 足够写 AI 配置 state event（state_default=50），又能被所有者降权/踢出。两个 100 的
// 用户在 Matrix 里通常互相无法降权，所以普通管理员不能给 100，否则撤销后降不下来。
// bot 是受信基础设施（只读配置、从不被管理），给 100 无妨。
const CONTROL_OWNER_PL = 100
const CONTROL_ADMIN_PL = 50

/**
 * 确保控制室存在：解析不到就新建（带别名、私有）。返回 room_id。
 *
 * 邀请对象不只是主 AI bot，还包括**所有服务器管理员**——否则只有创建者一人是房间成员，
 * 其他管理员虽能看到 /admin 入口，却读不到/写不了 AI 配置 state event。普通管理员给
 * CONTROL_ADMIN_PL(50)：够写配置，又能被所有者(100)管理（撤销时降权/踢出）。
 */
export async function ensureControlRoom(): Promise<string> {
  if (!mx) throw new Error('未登录')
  const me = mx.getUserId() || ''
  // 拉服务器管理员名单（需管理员 token；能进到这步的本就是管理员）。
  // 失败就退化为"只有创建者"——至少自己能用，不阻塞。
  let admins: string[] = []
  try {
    admins = (await listUsers())
      .filter((u) => u.admin && !u.deactivated)
      .map((u) => u.id)
  } catch {
    /* 拉不到名单：仅创建者可用 */
  }
  // 除创建者外的其他管理员（创建者建房自动入群，无需 invite）
  const others = admins.filter((a) => a && a !== me)

  const existing = await resolveControlRoom()
  if (existing) {
    // #2 修复：已存在的控制室也要补齐管理员的成员与权限——早先（多管理员逻辑之前）
    // 建的房只有创建者一人，后加的服务器管理员既进不来也没权限写 AI 配置。
    await reconcileControlRoomAdmins(existing, others)
    return existing
  }

  // 初始权限：所有者(创建者) + bot = 100；其他管理员 = 50（够写配置、可被所有者管理）
  const users: Record<string, number> = { [me]: CONTROL_OWNER_PL, [botId()]: CONTROL_OWNER_PL }
  for (const a of others) users[a] = CONTROL_ADMIN_PL

  const res: any = await (mx as any).createRoom({
    name: 'CosMac 控制室',
    room_alias_name: CONTROL_ROOM_LOCALPART,
    preset: 'private_chat',
    invite: [botId(), ...others], // 主 AI + 其他管理员
    topic: 'CosMac 管理后台 · 主 AI 运行时配置（请勿删除/退出）',
    power_level_content_override: { users },
  })
  return res.room_id
}

/**
 * 对**已存在**的控制室补齐其他管理员的权限与成员资格（幂等、尽力而为）。
 * ① 把 power < 50 的管理员提到 CONTROL_ADMIN_PL(50)（够写 AI 配置 state event）；
 *    **只升不降**——不动已是 100 的所有者，也不会把谁降下来。
 * ② 邀请还没在房里（join/invite 都不算在）的管理员。
 * 仅当当前用户在该房有改 power_levels 的权限（所有者=100）时才生效；没权限就静默跳过，
 * 绝不阻塞「保存 AI 配置」主流程。
 */
async function reconcileControlRoomAdmins(roomId: string, admins: string[]): Promise<void> {
  if (!mx) return
  const room = mx.getRoom(roomId)
  try {
    // ① 提权：**只有真正读到 power_levels 时才动它**。
    //    若房间没同步进本地（pl 读不到），绝不用空对象去 sendStateEvent——否则会把
    //    events_default/state_default/创建者自己的 100 等全部抹掉，造成自我锁权。
    const pl: any = (room as any)?.currentState
      ?.getStateEvents?.('m.room.power_levels', '')
      ?.getContent?.()
    if (pl && typeof pl === 'object') {
      const users: Record<string, number> = { ...(pl.users || {}) }
      let changed = false
      // 各管理员要到 50（够写配置）；**bot 要到 100**——否则它没法执行成员对齐
      // （降权/踢出被撤销的管理员）。老控制室里 bot 可能还是默认 0，这里由所有者补上。
      const want: Record<string, number> = { [botId()]: CONTROL_OWNER_PL }
      for (const a of admins) want[a] = CONTROL_ADMIN_PL
      for (const [uid, lvl] of Object.entries(want)) {
        if ((users[uid] ?? 0) < lvl) {
          users[uid] = lvl // 只升不降：不动已 ≥ 目标的（含所有者 100）
          changed = true
        }
      }
      if (changed) {
        // 保留原事件全部字段，只覆盖 users
        await (mx as any).sendStateEvent(roomId, 'm.room.power_levels', { ...pl, users }, '')
      }
    }
    // ② 邀请还不在房里的管理员（房间没同步时 present 为空，invite 已在者会被忽略）
    const present = new Set(
      ((room as any)?.getMembers?.() || [])
        .filter((m: any) => m.membership === 'join' || m.membership === 'invite')
        .map((m: any) => m.userId),
    )
    for (const a of admins) {
      if (!present.has(a)) {
        try {
          await mx.invite(roomId, a)
        } catch {
          /* 已在房/无权限：忽略 */
        }
      }
    }
  } catch {
    /* 无权限或读取失败：静默跳过，不影响保存 */
  }
}

/** 读取当前 AI 配置；控制室或配置不存在时返回 null（前端用默认值兜底）。 */
export async function getAiConfig(): Promise<AiConfig | null> {
  if (!mx) return null
  const rid = await resolveControlRoom()
  if (!rid) return null
  try {
    const ev = await (mx as any).getStateEvent(rid, AI_CONFIG_EVENT_TYPE, '')
    return {
      provider: ev?.provider || '',
      model: ev?.model || '',
      system_prompt: ev?.system_prompt || '',
      enabled_tools: Array.isArray(ev?.enabled_tools) ? ev.enabled_tools : null,
    }
  } catch {
    return null // 房间在但还没写过配置
  }
}

/**
 * 写入 AI 配置（必要时先建控制室）。bot 会在 ~20s 内读到并热应用。
 *
 * 安全：**不写 api_key**——密钥只在服务端配（环境变量/Secret Manager）。这里用不含
 * api_key 的内容**整体覆盖**旧事件，顺带抹掉历史上可能存过的明文 key（注：Matrix
 * 旧版本事件仍留在房间历史里，曾经存过的 key 仍需在服务端轮换才算彻底作废）。
 */
export async function setAiConfig(cfg: AiConfig): Promise<void> {
  if (!mx) throw new Error('未登录')
  const rid = await ensureControlRoom()
  await (mx as any).sendStateEvent(
    rid,
    AI_CONFIG_EVENT_TYPE,
    {
      provider: cfg.provider,
      model: cfg.model,
      system_prompt: cfg.system_prompt,
      enabled_tools: cfg.enabled_tools,
    },
    '',
  )
}

/* =====================================================================
 *  管理后台 · 会员等级（账号权限分层）
 *  存储：控制室 state event `cosmac.members`，{ members: { userId: {tier,...} } }。
 *  未列出的用户 = 免费会员（只存非免费的覆盖）。管理员手动调整；未来支付(模块4)由 bot 写。
 *  「服务器管理员」是另一套（独立于会员等级），仍走 Synapse admin 标志。
 * ===================================================================== */

/** 会员等级目录（与 bot 端 cosmac.members 的 MEMBER_TIERS 一致；slug 稳定、label 可改）。 */
export const MEMBER_TIERS: { slug: string; label: string }[] = [
  { slug: 'free', label: '免费会员' },
  { slug: 'paid', label: '付费会员' },
  { slug: 'creator', label: '创作者会员' },
]

/** 会员等级 slug → 中文标签（未知回落到「免费会员」）。 */
export function memberTierLabel(tier: string | undefined): string {
  return MEMBER_TIERS.find((t) => t.slug === tier)?.label || '免费会员'
}

/** 会员 map：userId → 等级 slug。只含非免费的；查不到即免费。 */
export type MemberMap = Record<string, string>

/**
 * 读控制室会员 map（管理员用）。控制室不存在返回空；其它读取错误向上抛。
 * 普通用户读不到控制室——他们查自己等级走「DM 问 bot：会员」。
 */
export async function getMembers(): Promise<MemberMap> {
  if (!mx) return {}
  const rid = await resolveControlRoom()
  if (!rid) return {}
  const events: any[] = await (mx as any).roomState(rid)
  const out: MemberMap = {}
  // 先兼容旧聚合事件；随后单用户事件覆盖，free tombstone 可撤销旧等级。
  for (const event of events || []) {
    const type = event?.getType?.() ?? event?.type
    const stateKey = event?.getStateKey?.() ?? event?.state_key
    const content = event?.getContent?.() ?? event?.content ?? {}
    if (type === MEMBERS_EVENT_TYPE && stateKey === '') {
      for (const [uid, rec] of Object.entries(content?.members || {})) {
        const tier = (rec as any)?.tier
        if (tier !== 'free' && MEMBER_TIERS.some((t) => t.slug === tier)) out[uid] = tier
      }
    }
  }
  for (const event of events || []) {
    const type = event?.getType?.() ?? event?.type
    if (type !== MEMBER_EVENT_TYPE) continue
    const sk = event?.getStateKey?.() ?? event?.state_key ?? ''
    const content = event?.getContent?.() ?? event?.content ?? {}
    // 真实 user_id 以 content.uid 为准（state_key 去了 @）；兼容旧数据
    let uid = content?.uid
    if (typeof uid !== 'string' || !uid) uid = sk.startsWith('@') ? sk : (sk ? '@' + sk : '')
    if (typeof uid !== 'string' || !uid.startsWith('@') || !uid.includes(':')) continue
    const tier = content?.tier
    if (tier === 'free') delete out[uid]
    else if (MEMBER_TIERS.some((t) => t.slug === tier)) out[uid] = tier
  }
  return out
}

/**
 * 单用户会员事件的 state_key：**去掉开头的 @**。
 * Matrix 规定 state_key 以 @ 开头的事件只有本人能写，否则 403——管理员/bot 给别人开会员会被拦。
 * 去 @ 后任何有写权限的人都能写；真实 user_id 存进 content.uid。
 */
function memberStateKey(userId: string): string {
  return userId.startsWith('@') ? userId.slice(1) : userId
}

/**
 * 设/调某用户的会员等级（必要时先建控制室）。每个用户独立 state_key，互不覆盖。
 * tier='free' 作为 tombstone，既是撤销，也会覆盖旧聚合事件里的历史记录。
 */
export async function setMemberTier(userId: string, tier: string): Promise<void> {
  if (!mx) throw new Error('未登录')
  if (!MEMBER_TIERS.some((t) => t.slug === tier)) throw new Error('未知会员等级')
  const rid = await ensureControlRoom()
  const content = { uid: userId, tier, source: 'admin', updated_ts: Math.floor(Date.now() / 1000) }
  // state_key 去掉 @（见 memberStateKey）——否则管理员给别人设等级会被 Matrix 403 拦
  await (mx as any).sendStateEvent(rid, MEMBER_EVENT_TYPE, content, memberStateKey(userId))
}

/* =====================================================================
 *  管理后台 · 功能门控（按会员等级限制能力）
 *  存储：控制室 state event `cosmac.gating`，{ gates: { capabilityKey: levelSlug } }。
 *  管理员逐项配「能力→最低等级」，bot 读取并**服务端强制**（前端只做展示/配置）。
 *  未配置的能力取目录里的 default。新增可门控能力 = 往 GATE_CATALOG 加一条（前后端各加）。
 * ===================================================================== */

/** 控制室里「功能门控策略」state event 的类型（与 bot 端 GATING_EVENT_TYPE 一致）。 */
const GATING_EVENT_TYPE = 'cosmac.gating'

/** 门槛阶梯（下拉可选项；与 bot 端 GATE_LEVELS 一致）。free<paid<creator<admin。 */
export const GATE_LEVELS: { slug: string; label: string }[] = [
  { slug: 'free', label: '免费（不限制）' },
  { slug: 'paid', label: '付费会员及以上' },
  { slug: 'creator', label: '创作者会员' },
  { slug: 'admin', label: '仅平台管理员' },
]

/** 可门控能力目录（与 bot 端 GATE_CATALOG 一致；key 稳定、default 为未配置时的默认门槛）。 */
export const GATE_CATALOG: { key: string; label: string; default: string }[] = [
  { key: 'ai_chat', label: '基础 AI 对话（@中枢AI / 私聊回复）', default: 'free' },
  { key: 'knowledge', label: '知识库（RAG 检索 + 知识命令）', default: 'free' },
  { key: 'create_room', label: '建群 / 开专班', default: 'free' },
  { key: 'workflow_run', label: '跑工作流（外部/付费、共享凭据）', default: 'admin' },
]

/** 门控策略 map：能力 key → 门槛 slug。 */
export type GatingMap = Record<string, string>

/**
 * 读门控策略（合并默认）。控制室不存在 / 事件不存在(404) → 返回纯默认（合法）。
 * #3：**瞬时读失败（网络/权限）会抛异常**，绝不伪装成"默认配置"——否则管理员在默认值上
 * 一保存，就把真实付费策略覆盖没了。调用方（AdminView）catch 后应提示失败、禁止保存。
 */
export async function getGating(): Promise<GatingMap> {
  // 先铺默认
  const merged: GatingMap = {}
  for (const g of GATE_CATALOG) merged[g.key] = g.default
  if (!mx) return merged
  const rid = await resolveControlRoom()
  if (!rid) return merged
  try {
    const ev = await (mx as any).getStateEvent(rid, GATING_EVENT_TYPE, '')
    const gates = ev?.gates
    if (gates && typeof gates === 'object') {
      for (const g of GATE_CATALOG) {
        const v = gates[g.key]
        if (typeof v === 'string' && GATE_LEVELS.some((l) => l.slug === v)) merged[g.key] = v
      }
    }
    return merged
  } catch (e: any) {
    // 事件不存在(404)=还没配过门控 → 返回默认（合法）。其余=瞬时读失败 → 抛，别伪装成默认。
    if (e?.errcode === 'M_NOT_FOUND') return merged
    throw new Error('读取门控策略失败，请重试（避免在读取失败时把默认值覆盖真实策略）')
  }
}

/** 写门控策略（必要时先建控制室）。只写目录里的已知能力、合法门槛。bot ~15s 内读到生效。 */
export async function setGating(gates: GatingMap): Promise<void> {
  if (!mx) throw new Error('未登录')
  const rid = await ensureControlRoom()
  const clean: GatingMap = {}
  for (const g of GATE_CATALOG) {
    const v = gates[g.key]
    if (typeof v === 'string' && GATE_LEVELS.some((l) => l.slug === v)) clean[g.key] = v
  }
  await (mx as any).sendStateEvent(rid, GATING_EVENT_TYPE, { gates: clean }, '')
}

/** 一条「全局技能」定义（管理后台编辑、主 AI 注入）。slug 在全局内唯一。 */
export interface GlobalSkill {
  slug: string
  name: string
  description: string
  instructions: string
  enabled: boolean
}

/** 读全局技能列表（控制室 state event）；房间/事件不存在时返回 []。 */
export async function getGlobalSkills(): Promise<GlobalSkill[]> {
  if (!mx) return []
  const rid = await resolveControlRoom()
  if (!rid) return []
  try {
    const ev = await (mx as any).getStateEvent(rid, SKILLS_EVENT_TYPE, '')
    const arr = Array.isArray(ev?.skills) ? ev.skills : []
    return arr.map((s: any) => ({
      slug: String(s?.slug || ''),
      name: String(s?.name || ''),
      description: String(s?.description || ''),
      instructions: String(s?.instructions || ''),
      enabled: s?.enabled !== false, // 缺省视为启用
    })).filter((s: GlobalSkill) => s.slug)
  } catch {
    return [] // 房间在但还没写过技能
  }
}

// 全局技能容量上限（与 bot 端 skill_cmd 一致；防刷爆模型上下文 / state event 过大）
const MAX_GLOBAL_SKILLS = 50
const MAX_SKILL_INSTRUCTIONS = 2000
const MAX_SKILL_NAME = 80
const MAX_SKILL_SLUG = 64

/**
 * 整体写入全局技能列表（必要时先建控制室）。主 AI 约 20 秒内读到并热生效。
 * 写前**校验 + 规范化**：数量/正文长度上限，且把每个字段强制成字符串——脏数据
 * （如 name 是数字）从源头就写不进去，bot 渲染时也不会因此崩/不回复。
 */
export async function setGlobalSkills(skills: GlobalSkill[]): Promise<void> {
  if (!mx) throw new Error('未登录')
  if (skills.length > MAX_GLOBAL_SKILLS) {
    throw new Error(`全局技能最多 ${MAX_GLOBAL_SKILLS} 个（当前 ${skills.length}）`)
  }
  const clean = skills.map((s) => {
    const slug = String(s.slug ?? '').trim().slice(0, MAX_SKILL_SLUG)
    if (!slug) throw new Error('技能标识（slug）不能为空')
    const instructions = String(s.instructions ?? '')
    if (instructions.length > MAX_SKILL_INSTRUCTIONS) {
      throw new Error(
        `技能「${slug}」正文超长（最多 ${MAX_SKILL_INSTRUCTIONS} 字，当前 ${instructions.length}）`,
      )
    }
    return {
      slug,
      name: String(s.name ?? '').trim().slice(0, MAX_SKILL_NAME),
      description: String(s.description ?? '').trim(),
      instructions,
      enabled: s.enabled !== false,
    }
  })
  const rid = await ensureControlRoom()
  await (mx as any).sendStateEvent(rid, SKILLS_EVENT_TYPE, { skills: clean }, '')
}

/** 一个「智能体(Agent)」定义 = 一套人设 + 模型覆盖 + 绑定的技能集。slug 全局唯一。 */
export interface GlobalAgent {
  slug: string
  name: string
  description: string
  system_prompt: string
  model: string
  skill_slugs: string[]
  enabled: boolean
}

/** 读全局智能体列表（控制室 state event）；房间/事件不存在时返回 []。 */
export async function getGlobalAgents(): Promise<GlobalAgent[]> {
  if (!mx) return []
  const rid = await resolveControlRoom()
  if (!rid) return []
  try {
    const ev = await (mx as any).getStateEvent(rid, AGENTS_EVENT_TYPE, '')
    const arr = Array.isArray(ev?.agents) ? ev.agents : []
    return arr.map((a: any) => ({
      slug: String(a?.slug || ''),
      name: String(a?.name || ''),
      description: String(a?.description || ''),
      system_prompt: String(a?.system_prompt || ''),
      model: String(a?.model || ''),
      skill_slugs: Array.isArray(a?.skill_slugs) ? a.skill_slugs.map(String) : [],
      enabled: a?.enabled !== false,
    })).filter((a: GlobalAgent) => a.slug)
  } catch {
    return []
  }
}

/** 整体写入全局智能体列表（必要时先建控制室）。 */
export async function setGlobalAgents(agents: GlobalAgent[]): Promise<void> {
  if (!mx) throw new Error('未登录')
  const rid = await ensureControlRoom()
  await (mx as any).sendStateEvent(rid, AGENTS_EVENT_TYPE, { agents }, '')
}

/** 一条「全局规则」：平台级硬约束，主 AI 在所有群都须遵守。 */
export interface GlobalRule {
  text: string
  enabled: boolean
}

/** 读全局规则列表（控制室 state event）；不存在时返回 []。 */
export async function getGlobalRules(): Promise<GlobalRule[]> {
  if (!mx) return []
  const rid = await resolveControlRoom()
  if (!rid) return []
  try {
    const ev = await (mx as any).getStateEvent(rid, RULES_EVENT_TYPE, '')
    const arr = Array.isArray(ev?.rules) ? ev.rules : []
    return arr
      .map((r: any) => ({ text: String(r?.text || ''), enabled: r?.enabled !== false }))
      .filter((r: GlobalRule) => r.text.trim())
  } catch {
    return []
  }
}

/** 整体写入全局规则列表（必要时先建控制室）。 */
export async function setGlobalRules(rules: GlobalRule[]): Promise<void> {
  if (!mx) throw new Error('未登录')
  const rid = await ensureControlRoom()
  await (mx as any).sendStateEvent(rid, RULES_EVENT_TYPE, { rules }, '')
}

/** 一个「工作流连接器」定义（对接 n8n/Make/Dify/Coze 等外部平台）。 */
export interface WorkflowDef {
  slug: string
  name: string
  platform: string          // webhook（n8n/Make/自建） | dify | coze
  url: string
  method: string            // POST/GET（webhook 用）
  cred: string              // 凭据名（真值在服务端 env COSMAC_WF_<CRED>；这里只放名字）
  input_hint: string
  enabled: boolean
  mode: string              // dify: workflow|chat
  ref_id: string            // coze: workflow_id
  input_key: string         // dify/coze: 输入变量名（默认 input）
  graph: string             // comfyui: API 格式工作流 JSON，用 {{input}} 占位
  async: boolean            // webhook: 长任务异步——提交后等平台回调，不同步等结果
}

/** 读工作流连接器列表（控制室 state event）；不存在返回 []。 */
export async function getWorkflows(): Promise<WorkflowDef[]> {
  if (!mx) return []
  const rid = await resolveControlRoom()
  if (!rid) return []
  try {
    const ev = await (mx as any).getStateEvent(rid, WORKFLOWS_EVENT_TYPE, '')
    const arr = Array.isArray(ev?.workflows) ? ev.workflows : []
    return arr.map((w: any) => ({
      slug: String(w?.slug || ''),
      name: String(w?.name || ''),
      platform: String(w?.platform || 'webhook'),
      url: String(w?.url || ''),
      method: String(w?.method || 'POST'),
      cred: String(w?.cred || ''),
      input_hint: String(w?.input_hint || ''),
      enabled: w?.enabled !== false,
      mode: String(w?.mode || 'workflow'),
      ref_id: String(w?.ref_id || ''),
      input_key: String(w?.input_key || ''),
      graph: String(w?.graph || ''),
      async: w?.async === true,
    })).filter((w: WorkflowDef) => w.slug)
  } catch {
    return []
  }
}

/** 整体写入工作流连接器列表（必要时先建控制室）。 */
export async function setWorkflows(workflows: WorkflowDef[]): Promise<void> {
  if (!mx) throw new Error('未登录')
  const rid = await ensureControlRoom()
  await (mx as any).sendStateEvent(rid, WORKFLOWS_EVENT_TYPE, { workflows }, '')
}

/* =====================================================================
 *  管理后台 · 会员套餐（模块4 交易系统）
 *  存储：控制室 state event `cosmac.plans`，{ plans: [{slug,name,tier,period_days,prices,enabled}] }。
 *  价格按货币存**最小单位整数(分/cent)**；前端编辑用元、保存时 ×100 取整。
 * ===================================================================== */

const PLANS_EVENT_TYPE = 'cosmac.plans'

/** 套餐支持的货币（与后端解析一致；prices 的 key 用小写 code）。 */
export const PLAN_CURRENCIES: { code: string; label: string }[] = [
  { code: 'usd', label: 'USD($)' },
  { code: 'cny', label: 'CNY(¥)' },
  { code: 'usdt', label: 'USDT' },
]

/** 一个会员套餐（管理后台编辑）。prices：货币 code → **分**(整数)。 */
export interface PlanDef {
  slug: string
  name: string
  tier: string                 // paid | creator（不能是 free）
  period_days: number
  prices: Record<string, number>  // 货币 → 分(cent)
  enabled: boolean
}

/**
 * 读套餐列表（控制室 state event）。事件不存在(404)→[]；**瞬时读失败抛异常**——
 * 否则管理员会在空列表上保存、把真实套餐覆盖没了（同 gating 的保护）。
 */
export async function getPlans(): Promise<PlanDef[]> {
  if (!mx) return []
  const rid = await resolveControlRoom()
  if (!rid) return []
  try {
    const ev = await (mx as any).getStateEvent(rid, PLANS_EVENT_TYPE, '')
    const arr = Array.isArray(ev?.plans) ? ev.plans : []
    return arr.map((p: any) => {
      const prices: Record<string, number> = {}
      if (p?.prices && typeof p.prices === 'object') {
        for (const [cur, cents] of Object.entries(p.prices)) {
          const c = Math.trunc(Number(cents))
          if (Number.isFinite(c) && c > 0) prices[String(cur).toLowerCase()] = c
        }
      }
      return {
        slug: String(p?.slug || ''),
        name: String(p?.name || ''),
        tier: p?.tier === 'creator' ? 'creator' : 'paid',
        period_days: Math.max(1, Math.trunc(Number(p?.period_days) || 30)),
        prices,
        enabled: p?.enabled !== false,
      }
    }).filter((p: PlanDef) => p.slug)
  } catch (e: any) {
    if (e?.errcode === 'M_NOT_FOUND') return []
    throw new Error('读取套餐失败，请重试（避免在读取失败时把空列表覆盖真实套餐）')
  }
}

/* —— 用户侧「升级会员」：调 bot 的 /cosmac/pay/* 端点（前端够不到 cosmac DB）——
 *  base = homeserver(hs.cosmac.cc)，nginx 已把 /cosmac/ 代理给 bot。 */

function payBase(): string {
  return String((mx as any)?.baseUrl || '').replace(/\/$/, '')
}

export interface PayPlan {
  slug: string; name: string; tier: string; period_days: number
  prices: Record<string, number>
}

/** 公开读上架套餐（给「升级会员」面板展示）。 */
export async function payGetPlans(): Promise<PayPlan[]> {
  const r = await fetch(`${payBase()}/cosmac/pay/plans`)
  if (!r.ok) throw new Error('读取套餐失败')
  const j = await r.json().catch(() => ({}))
  return Array.isArray(j?.plans) ? j.plans : []
}

export interface PayMe { tier: string; tier_label: string; expires_ts: number }

/** 查"我当前的会员状态"（升级弹窗顶部展示）。未登录/失败返回 null。 */
export async function payGetMe(): Promise<PayMe | null> {
  const token = (mx as any)?.getAccessToken?.() || ''
  if (!token) return null
  try {
    const r = await fetch(`${payBase()}/cosmac/pay/me`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!r.ok) return null
    return await r.json()
  } catch { return null }
}

/** 平台真实运营指标（数据看板用；CosMac 真正拥有的数据）。 */
export interface PlatformStats {
  members_paid: number; members_creator: number
  workflow_runs: number; orders_paid: number; kb_docs: number
}

export async function getPlatformStats(): Promise<PlatformStats | null> {
  const token = (mx as any)?.getAccessToken?.() || ''
  if (!token) return null
  try {
    const r = await fetch(`${payBase()}/cosmac/stats`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!r.ok) return null
    return await r.json()
  } catch { return null }
}

/** 任务看板的一条任务（AI 任务编排 P1）。 */
export interface TaskItem {
  id: number; title: string; assignee: string
  status: string; progress: number; goal: string; result: string
}

export async function getTasks(): Promise<TaskItem[]> {
  const token = (mx as any)?.getAccessToken?.() || ''
  if (!token) return []
  try {
    const r = await fetch(`${payBase()}/cosmac/tasks`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!r.ok) return []
    const j = await r.json()
    return Array.isArray(j?.tasks) ? j.tasks : []
  } catch { return [] }
}

/** 改任务状态/进度（看板手动操作）。返回是否成功。 */
export async function updateTask(
  id: number, patch: { status?: string; progress?: number },
): Promise<boolean> {
  const token = (mx as any)?.getAccessToken?.() || ''
  if (!token) return false
  try {
    const r = await fetch(`${payBase()}/cosmac/tasks/update`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ id, ...patch }),
    })
    return r.ok
  } catch { return false }
}

export interface CheckoutResp {
  order_no: string; amount_cents: number; currency: string
  tier: string; period_days: number
  checkout: { kind: string; url: string; address: string; extra: any }
}

/** 下单：带上自己的 access token，bot 验明身份后建订单、返回支付方式。 */
export async function payCheckout(
  planSlug: string, currency: string, provider = 'manual',
): Promise<CheckoutResp> {
  const token = (mx as any)?.getAccessToken?.() || ''
  const r = await fetch(`${payBase()}/cosmac/pay/checkout`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ plan_slug: planSlug, currency, provider }),
  })
  const j = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(j?.error || '下单失败')
  return j
}

/** 测试通道：模拟支付成功（manual）。需服务端开 COSMAC_PAY_ALLOW_MANUAL=1。 */
export async function payManualConfirm(orderNo: string, token: string): Promise<void> {
  const r = await fetch(`${payBase()}/cosmac/pay/callback/manual`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ order_no: orderNo, token }),
  })
  if (!r.ok) {
    throw new Error(
      r.status === 403
        ? '测试支付通道未开启（需服务端设 COSMAC_PAY_ALLOW_MANUAL=1）'
        : '确认失败，请重试',
    )
  }
}

/** 整体写入套餐列表（必要时先建控制室）。只写合法项。 */
export async function setPlans(plans: PlanDef[]): Promise<void> {
  if (!mx) throw new Error('未登录')
  const rid = await ensureControlRoom()
  const clean = plans
    .filter((p) => p.slug && (p.tier === 'paid' || p.tier === 'creator'))
    .map((p) => ({
      slug: p.slug, name: p.name || p.slug, tier: p.tier,
      period_days: Math.max(1, Math.trunc(p.period_days) || 30),
      prices: p.prices, enabled: p.enabled !== false,
    }))
  await (mx as any).sendStateEvent(rid, PLANS_EVENT_TYPE, { plans: clean }, '')
}

/** 读某个频道当前时间线的消息（含发送者昵称与 cosmac.card 富卡）。 */
export function listMessages(roomId: string): LiveMsg[] {
  const room = mx?.getRoom(roomId)
  if (!room) return []
  return room
    .getLiveTimeline()
    .getEvents()
    .filter((e) => e.getType() === 'm.room.message')
    // 已撤回(redacted)的消息 content 为空，跳过 → 不再显示空气泡
    .filter((e) => !(e as any).isRedacted?.() && Object.keys(e.getContent() || {}).length > 0)
    .map((e) => {
      const sender = e.getSender() || ''
      // 编辑：若有替换事件，取最新内容并标记 edited
      const replacing = (e as any).replacingEvent?.()
      const c: any = replacing
        ? (replacing.getContent()['m.new_content'] || replacing.getContent())
        : e.getContent()
      // 回复：读 m.in_reply_to → 解析被回复消息的名字/正文预览
      const inReplyTo = e.getContent()?.['m.relates_to']?.['m.in_reply_to']?.event_id
      let replyToSender: string | undefined
      let replyToName: string | undefined
      let replyToBody: string | undefined
      if (inReplyTo) {
        const re = room.findEventById?.(inReplyTo)
        if (re) {
          replyToSender = re.getSender() || ''
          replyToName = room.getMember(replyToSender)?.name || replyToSender
          replyToBody = stripReplyFallback(re.getContent()?.body || '').slice(0, 80)
        }
      }
      return {
        id: e.getId() || '',
        sender,
        senderName: room.getMember(sender)?.name || sender,
        body: stripReplyFallback(c.body || ''),
        ts: e.getTs(),
        card: c['cosmac.card'],
        edited: !!replacing,
        replyToId: inReplyTo,
        replyToSender,
        replyToName,
        replyToBody,
      }
    })
}

/** 去掉富回复正文里 "> <@x> 引用..." 的 fallback 前缀，只留用户真正打的内容。 */
function stripReplyFallback(body: string): string {
  // fallback 形如：连续若干 "> ..." 行 + 一个空行，之后才是正文
  const m = body.match(/^(> .*\n)+\n?/)
  return m ? body.slice(m[0].length) : body
}

/** 读某频道所有消息的反应聚合：{ 目标eventId: [{key,count,mine,myId}] }。 */
export function listReactions(roomId: string): Record<string, ReactionAgg[]> {
  const room = mx?.getRoom(roomId)
  if (!room) return {}
  const me = mx?.getUserId()
  const grouped: Record<string, Record<string, ReactionAgg>> = {}
  for (const e of room.getLiveTimeline().getEvents()) {
    if (e.getType() !== 'm.reaction' || (e as any).isRedacted?.()) continue
    const rel = e.getContent()?.['m.relates_to']
    if (!rel || rel.rel_type !== 'm.annotation' || !rel.event_id || !rel.key) continue
    const tgt = rel.event_id as string
    const key = rel.key as string
    grouped[tgt] ||= {}
    const agg = (grouped[tgt][key] ||= { key, count: 0, mine: false })
    agg.count++
    if (e.getSender() === me) { agg.mine = true; agg.myId = e.getId() || undefined }
  }
  const out: Record<string, ReactionAgg[]> = {}
  for (const tgt in grouped) out[tgt] = Object.values(grouped[tgt])
  return out
}

/** 给某条消息加一个 emoji 反应（m.reaction 注解）。 */
export async function react(roomId: string, targetEventId: string, key: string): Promise<void> {
  if (!mx) throw new Error('未登录')
  await (mx as any).sendEvent(roomId, 'm.reaction', {
    'm.relates_to': { rel_type: 'm.annotation', event_id: targetEventId, key },
  })
}

/** 取消我的某条反应（redact 那条 reaction 事件）。 */
export async function unreact(roomId: string, reactionEventId: string): Promise<void> {
  if (!mx) throw new Error('未登录')
  await mx.redactEvent(roomId, reactionEventId)
}

/** 编辑自己的某条消息（m.replace），消息会显示"已编辑"。 */
export async function editMessage(roomId: string, eventId: string, body: string): Promise<void> {
  if (!mx) throw new Error('未登录')
  await (mx as any).sendEvent(roomId, 'm.room.message', {
    msgtype: 'm.text',
    body: `* ${body}`, // 旧客户端 fallback
    'm.new_content': { msgtype: 'm.text', body },
    'm.relates_to': { rel_type: 'm.replace', event_id: eventId },
  })
}

/** 回复某条消息（m.in_reply_to）。 */
export async function sendReply(roomId: string, body: string, replyToEventId: string): Promise<void> {
  if (!mx) throw new Error('未登录')
  await (mx as any).sendEvent(roomId, 'm.room.message', {
    msgtype: 'm.text',
    body,
    'm.relates_to': { 'm.in_reply_to': { event_id: replyToEventId } },
  })
}

/** 往频道发一条纯文本消息（真发到 Synapse）。 */
export async function sendText(roomId: string, body: string): Promise<void> {
  if (!mx) return
  await mx.sendTextMessage(roomId, body)
}

/** 主 AI 的 localpart（用户名部分，固定）；完整 id 的域名按当前登录服务器动态拼。 */
const BOT_LOCALPART = 'guduu'
/**
 * 主 AI 的完整用户 id（私聊它 = 右侧"中枢 AI"面板）。
 * 按当前登录服务器域名动态拼（@guduu:<serverName>），不写死 cosmac.cc——
 * 否则本地 guduu.local 环境会去邀请一个不存在的账号，AI 进不了群。
 * 必须在登录后调用（serverName() 取自当前用户 id）。
 */
export function botId(): string {
  return `@${BOT_LOCALPART}:${serverName()}`
}

/** 找到我和主 AI 的私聊房间（仅两人）；没有返回 null。 */
export function findBotDm(): string | null {
  if (!mx) return null
  for (const r of mx.getRooms()) {
    const ids = r.getJoinedMembers().map((m) => m.userId)
    if (ids.length <= 2 && ids.includes(botId())) return r.roomId
  }
  return null
}

/** 确保有一个"中枢 AI"私聊房间：先复用已存在的（按名字），没有才新建。 */
export async function ensureBotDm(): Promise<string> {
  if (!mx) throw new Error('未登录')
  // 同步已完成，getRooms 可靠：复用任意一个已存在的"中枢 AI"房间，避免重复创建
  const existing = mx.getRooms().find((r) => r.name === '中枢 AI')
  if (existing) return existing.roomId
  const res: any = await mx.createRoom({
    name: '中枢 AI',
    preset: 'trusted_private_chat' as any,
    invite: [botId()],
    is_direct: true,
  })
  return res.room_id
}
