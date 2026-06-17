// CosMac 客户端的 Matrix 适配层：用 matrix-js-sdk 连 Synapse 后端。
// 能力：登录（带会话记忆，刷新不用重登）→ 同步 → 列频道 → 读消息（含 cosmac.card 富卡）→ 发消息。

// matrix-js-sdk 里有些代码引用了 node 风格的 global，浏览器里先补个垫片。
;(globalThis as any).global ||= globalThis

import { createClient, type MatrixClient } from 'matrix-js-sdk'

/** 给 UI 用的精简频道结构 */
export interface LiveRoom {
  id: string
  name: string
}

/** 给 UI 用的精简消息结构；card 为 cosmac.card 自定义富卡（可能没有） */
export interface LiveMsg {
  id: string
  sender: string
  senderName: string
  body: string
  ts: number
  card?: any
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

/** 列出我加入的频道（按名称排序）。 */
export function listRooms(): LiveRoom[] {
  if (!mx) return []
  return mx
    .getRooms()
    .map((r) => ({ id: r.roomId, name: r.name || r.roomId }))
    .sort((a, b) => a.name.localeCompare(b.name, 'zh'))
}

/** 读某个频道当前时间线的消息（含发送者昵称与 cosmac.card 富卡）。 */
export function listMessages(roomId: string): LiveMsg[] {
  const room = mx?.getRoom(roomId)
  if (!room) return []
  return room
    .getLiveTimeline()
    .getEvents()
    .filter((e) => e.getType() === 'm.room.message')
    .map((e) => {
      const c: any = e.getContent()
      const sender = e.getSender() || ''
      return {
        id: e.getId() || '',
        sender,
        senderName: room.getMember(sender)?.name || sender,
        body: c.body || '',
        ts: e.getTs(),
        card: c['cosmac.card'],
      }
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

/** 确保存在一个和主 AI 的私聊房间：有就返回，没有就新建一个。 */
export async function ensureBotDm(): Promise<string> {
  const found = findBotDm()
  if (found) return found
  const res: any = await mx!.createRoom({
    preset: 'trusted_private_chat' as any,
    invite: [BOT_ID],
    is_direct: true,
  })
  return res.room_id
}
