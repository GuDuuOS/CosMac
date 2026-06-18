"""对 Synapse 的最小客户端封装（主 AI 的"手"）。

主 AI 通过这里去操作 IM —— 当前只实现了"加入房间"和"发文本消息"两件事，
后续"创建群、查聊天记录、踢人"等能力都会作为新方法加到这里。

实现方式：用 appservice 的 as_token 直接调用 Synapse 的 Client-Server API。
appservice token 的默认身份就是注册文件里的 sender_localpart（即 @guduu）。
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import requests

logger = logging.getLogger("cosmac.matrix_client")


class MatrixClient:
    """以 appservice 身份调用 Synapse 的轻量客户端。"""

    def __init__(self, homeserver_url: str, as_token: str, bot_user_id: str):
        # 去掉末尾斜杠，避免拼出 http://host//_matrix 这种双斜杠
        self.homeserver_url = homeserver_url.rstrip("/")
        self.as_token = as_token
        self.bot_user_id = bot_user_id
        # 安全：as_token 是高权限凭证，**绝不放进 URL 查询参数**（会进 nginx/代理/错误
        # 日志）。改用 Authorization: Bearer 请求头，用一个 Session 统一带上。
        self._session = requests.Session()
        self._session.headers["Authorization"] = f"Bearer {as_token}"

    def _url(self, path: str) -> str:
        """拼出完整的 API URL，只在查询参数里带 user_id（身份标识，非密钥）。

        - user_id：明确以主 AI（@guduu）的身份操作（appservice 可代理其名下用户）。
        - 鉴权（as_token）走 Authorization 头，见 __init__ 的 Session，不进 URL。
        """
        sep = "&" if "?" in path else "?"
        return f"{self.homeserver_url}{path}{sep}user_id={quote(self.bot_user_id)}"

    def _txn_id(self) -> str:
        """生成一个唯一的事务 id（Matrix 要求发送类请求带上，用于去重）。"""
        # 用纳秒时间戳即可保证单进程内唯一
        return f"cosmac{time.time_ns()}"

    def join_room(self, room_id: str) -> None:
        """让主 AI 加入指定房间（通常是被邀请后调用）。"""
        url = self._url(f"/_matrix/client/v3/rooms/{quote(room_id)}/join")
        resp = self._session.post(url, json={}, timeout=10)
        if resp.status_code == 200:
            logger.info("已加入房间 %s", room_id)
        else:
            logger.warning("加入房间 %s 失败: %s %s", room_id, resp.status_code, resp.text)

    def send_text(self, room_id: str, text: str) -> Optional[str]:
        """以主 AI 身份往房间发一条纯文本消息。

        返回：成功时返回服务器分配的 event_id，失败返回 None。
        """
        txn = self._txn_id()
        url = self._url(
            f"/_matrix/client/v3/rooms/{quote(room_id)}/send/m.room.message/{txn}"
        )
        body = {"msgtype": "m.text", "body": text}
        # 发送类请求用 PUT（带事务 id 保证幂等）
        resp = self._session.put(url, json=body, timeout=10)
        if resp.status_code == 200:
            event_id = resp.json().get("event_id")
            logger.info("已向房间 %s 发送消息, event_id=%s", room_id, event_id)
            return event_id
        logger.warning("向房间 %s 发消息失败: %s %s", room_id, resp.status_code, resp.text)
        return None

    def set_displayname(self, displayname: str) -> None:
        """设置主 AI 在 IM 里的显示名（群里用户看到的就是它，而非用户 id）。

        用 appservice 身份调用 Synapse 的 profile API。失败只记日志、不阻断启动
        （比如品牌名改了、重启 bot 一次就会更新成新名字）。
        """
        url = self._url(
            f"/_matrix/client/v3/profile/{quote(self.bot_user_id)}/displayname"
        )
        try:
            resp = self._session.put(url, json={"displayname": displayname}, timeout=10)
            if resp.status_code == 200:
                logger.info("已设置主 AI 显示名: %s", displayname)
            else:
                logger.warning("设置显示名失败: %s %s", resp.status_code, resp.text)
        except requests.RequestException as exc:
            logger.warning("设置显示名异常: %s", exc)

    # —— 主 AI 操作 IM 的能力（"手"）：建群 / 拉人 / 发富卡 ——

    def create_room(self, name: str, invitees: Optional[List[str]] = None) -> Optional[str]:
        """新建一个房间（专班群），可在创建时直接邀请一批用户。

        参数：
            name:     房间显示名（如"爆款专班·职场"）。
            invitees: 创建时就邀请的用户 id 列表（如 ["@admin:cosmac.cc"]）。
        返回：成功返回新房间 room_id，失败返回 None。
        """
        url = self._url("/_matrix/client/v3/createRoom")
        body: Dict[str, Any] = {"name": name, "preset": "private_chat"}
        if invitees:
            body["invite"] = invitees
        resp = self._session.post(url, json=body, timeout=15)
        if resp.status_code == 200:
            room_id = resp.json().get("room_id")
            logger.info("已创建房间 %s (%s)", name, room_id)
            return room_id
        logger.warning("创建房间失败: %s %s", resp.status_code, resp.text)
        return None

    def invite_user(self, room_id: str, user_id: str) -> None:
        """把某用户邀请进房间。"""
        url = self._url(f"/_matrix/client/v3/rooms/{quote(room_id)}/invite")
        resp = self._session.post(url, json={"user_id": user_id}, timeout=10)
        if resp.status_code == 200:
            logger.info("已邀请 %s 进 %s", user_id, room_id)
        else:
            logger.warning(
                "邀请 %s 进 %s 失败: %s %s", user_id, room_id, resp.status_code, resp.text
            )

    def set_power_levels(self, room_id: str, content: Dict[str, Any]) -> bool:
        """整体覆盖某房间的 m.room.power_levels 状态事件（调用方负责传完整内容）。

        用于控制室成员对齐——把非管理员从 users 里删掉（回落 users_default=0）。
        需要 bot 在该房有改 power_levels 的权限（控制室里 bot=100，够）。成功返回 True。
        """
        url = self._url(
            f"/_matrix/client/v3/rooms/{quote(room_id)}/state/m.room.power_levels/"
        )
        resp = self._session.put(url, json=content, timeout=10)
        if resp.status_code == 200:
            return True
        logger.warning("设置 power_levels@%s 失败: %s %s", room_id, resp.status_code, resp.text)
        return False

    def kick(self, room_id: str, user_id: str, reason: str = "") -> bool:
        """把某用户踢出房间（控制室对齐时移除已撤销的管理员）。成功返回 True。

        需要 bot 的 power 高于对方且 ≥ kick 等级（控制室里 bot=100，够）。
        """
        url = self._url(f"/_matrix/client/v3/rooms/{quote(room_id)}/kick")
        body: Dict[str, Any] = {"user_id": user_id}
        if reason:
            body["reason"] = reason
        resp = self._session.post(url, json=body, timeout=10)
        if resp.status_code == 200:
            logger.info("已把 %s 踢出 %s", user_id, room_id)
            return True
        logger.warning("踢出 %s@%s 失败: %s %s", user_id, room_id, resp.status_code, resp.text)
        return False

    def send_card(self, room_id: str, body: str, card: Dict[str, Any]) -> Optional[str]:
        """往房间发一条"富卡"消息。

        Matrix 协议不能改，所以用标准 m.room.message 承载：
        - body：纯文本兜底，Element 等不认识富卡的客户端只显示这段文字。
        - cosmac.card：自定义字段（命名空间 cosmac.*，不与协议的 m.* 冲突），
          CosMac 自己的客户端据此把它渲染成结构化富卡。
        返回 event_id 或 None。
        """
        txn = self._txn_id()
        url = self._url(
            f"/_matrix/client/v3/rooms/{quote(room_id)}/send/m.room.message/{txn}"
        )
        payload: Dict[str, Any] = {
            "msgtype": "m.text",
            "body": body,
            "cosmac.card": card,
        }
        resp = self._session.put(url, json=payload, timeout=10)
        if resp.status_code == 200:
            return resp.json().get("event_id")
        logger.warning("发送富卡失败: %s %s", resp.status_code, resp.text)
        return None

    def resolve_alias(self, alias: str) -> Optional[str]:
        """把房间别名（#cosmac-ctrl:host）解析成 room_id。

        语义区分（让调用方能安全回退、不"失效开放"）：
          - 200 → 返回 room_id；
          - 404 → 别名确实不存在 → 返回 None（控制室还没建，属正常）；
          - 其它状态码 / 网络异常 → **抛异常**，让调用方保留上次配置，
            而不是把"读失败"误当成"控制室不存在"。
        """
        url = self._url(f"/_matrix/client/v3/directory/room/{quote(alias)}")
        resp = self._session.get(url, timeout=10)  # 网络异常向上抛
        if resp.status_code == 200:
            return resp.json().get("room_id")
        if resp.status_code == 404:
            return None
        raise RuntimeError(f"解析别名 {alias} 失败: HTTP {resp.status_code}")

    def get_state_event(
        self, room_id: str, event_type: str, state_key: str = ""
    ) -> Optional[Dict[str, Any]]:
        """读某房间的一个 state event 内容（如 AI 配置）。

        需要 bot 已加入该房间。语义区分（避免读失败被当成"没配置"而失效开放）：
          - 200 → 返回内容 dict；
          - 404 → 该房间确实没有这个 state event → 返回 None（正常，无覆盖）；
          - 403/网络错/5xx 等 → **抛异常**，让调用方保留上次成功的配置。
        """
        url = self._url(
            f"/_matrix/client/v3/rooms/{quote(room_id)}/state/"
            f"{quote(event_type)}/{quote(state_key)}"
        )
        resp = self._session.get(url, timeout=10)  # 网络异常向上抛
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 404:
            return None
        raise RuntimeError(
            f"读 state {event_type}@{room_id} 失败: HTTP {resp.status_code}"
        )

    def get_members(self, room_id: str) -> List[Dict[str, str]]:
        """查房间已加入的成员列表（主 AI 的"眼睛"之一）。

        返回：[{"user_id": "@a:host", "display_name": "Alice"}, ...]；
        查不到返回空列表。
        """
        url = self._url(f"/_matrix/client/v3/rooms/{quote(room_id)}/joined_members")
        try:
            resp = self._session.get(url, timeout=10)
            if resp.status_code == 200:
                joined = resp.json().get("joined", {})
                return [
                    {"user_id": uid, "display_name": info.get("display_name") or uid}
                    for uid, info in joined.items()
                ]
            logger.warning("查成员失败: %s %s", resp.status_code, resp.text)
        except requests.RequestException as exc:
            logger.warning("查成员异常: %s", exc)
        return []

    def get_messages(self, room_id: str, limit: int = 20) -> List[Dict[str, str]]:
        """查房间最近的文本消息（主 AI"读聊天记录"的能力）。

        参数：
            room_id: 房间 id。
            limit:   最多取多少条（从最新往回数）。
        返回：按时间正序（旧→新）排列的 [{"sender", "body"}, ...]；查不到返回空列表。
        """
        # dir=b 表示从最新往回翻；Matrix 返回的是"新→旧"，我们再倒过来给上层
        url = self._url(
            f"/_matrix/client/v3/rooms/{quote(room_id)}/messages?dir=b&limit={int(limit)}"
        )
        try:
            resp = self._session.get(url, timeout=10)
            if resp.status_code != 200:
                logger.warning("查消息失败: %s %s", resp.status_code, resp.text)
                return []
            chunk = resp.json().get("chunk", [])
            msgs: List[Dict[str, str]] = []
            for ev in chunk:
                if ev.get("type") != "m.room.message":
                    continue
                content = ev.get("content", {})
                body = content.get("body")
                if not body:
                    continue
                msgs.append({"sender": ev.get("sender", ""), "body": body})
            msgs.reverse()  # 倒成旧→新，读起来顺
            return msgs
        except requests.RequestException as exc:
            logger.warning("查消息异常: %s", exc)
            return []

    def joined_member_count(self, room_id: str) -> int:
        """查房间当前已加入的成员数（用于区分"私聊"和"群聊"）。

        私聊（只有用户 + 主 AI，共 2 人）里，主 AI 对每句话都回；
        群聊里则只在被 @ 时才回。查不到就保守按群聊处理。
        """
        url = self._url(f"/_matrix/client/v3/rooms/{quote(room_id)}/joined_members")
        try:
            resp = self._session.get(url, timeout=10)
            if resp.status_code == 200:
                return len(resp.json().get("joined", {}))
        except requests.RequestException:
            pass
        return 99
