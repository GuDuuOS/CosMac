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
  /** 回复的目标消息（m.in_reply_to）：对方名 + 正文预览 */
  replyToId?: string
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
  await new Promise<void>((resolve) => {
    const handler = (state: string) => {
      if (state === 'PREPARED') {
        ;(mx as any).off('sync', handler)
        resolve()
      }
    }
    if ((mx as any).getSyncState?.() === 'PREPARED') resolve()
    else (mx as any).on('sync', handler)
  })
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

/** 退出登录、清掉记住的会话。 */
export function logout(): void {
  localStorage.removeItem(SESSION_KEY)
  try {
    mx?.stopClient()
  } catch {
    /* ignore */
  }
  mx = null
}

/** 注册"有更新就回调"——同步完成或来新消息时触发，UI 据此刷新。 */
export function onUpdate(cb: () => void): void {
  if (!mx) return
  ;(mx as any).on('sync', (state: string) => {
    if (state === 'PREPARED' || state === 'SYNCING') cb()
  })
  ;(mx as any).on('Room.timeline', () => cb())
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
    invite: [BOT_ID], // 拉主 AI 进群，频道里 AI 能回
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
    isBot: m.userId === BOT_ID,
  }))
}

/** 邀请一个已有用户进某频道（标准 Matrix 邀请）。 */
export async function inviteToRoom(roomId: string, userId: string): Promise<void> {
  if (!mx) throw new Error('未登录')
  await mx.invite(roomId, userId)
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
      let replyToName: string | undefined
      let replyToBody: string | undefined
      if (inReplyTo) {
        const re = room.findEventById?.(inReplyTo)
        if (re) {
          const rs = re.getSender() || ''
          replyToName = room.getMember(rs)?.name || rs
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

/** 主 AI 的用户 id（私聊它 = 右侧"中枢 AI"面板）。 */
export const BOT_ID = '@guduu:cosmac.cc'

/** 找到我和主 AI 的私聊房间（仅两人）；没有返回 null。 */
export function findBotDm(): string | null {
  if (!mx) return null
  for (const r of mx.getRooms()) {
    const ids = r.getJoinedMembers().map((m) => m.userId)
    if (ids.length <= 2 && ids.includes(BOT_ID)) return r.roomId
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
    invite: [BOT_ID],
    is_direct: true,
  })
  return res.room_id
}
