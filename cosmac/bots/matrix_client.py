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

    def _url(self, path: str) -> str:
        """拼出完整的 API URL，并带上 appservice 鉴权与身份参数。

        - access_token：用 as_token 表明"我是这个 appservice"。
        - user_id：明确以主 AI（@guduu）的身份操作。
        """
        sep = "&" if "?" in path else "?"
        return (
            f"{self.homeserver_url}{path}{sep}"
            f"access_token={self.as_token}&user_id={quote(self.bot_user_id)}"
        )

    def _txn_id(self) -> str:
        """生成一个唯一的事务 id（Matrix 要求发送类请求带上，用于去重）。"""
        # 用纳秒时间戳即可保证单进程内唯一
        return f"guduu{time.time_ns()}"

    def join_room(self, room_id: str) -> None:
        """让主 AI 加入指定房间（通常是被邀请后调用）。"""
        url = self._url(f"/_matrix/client/v3/rooms/{quote(room_id)}/join")
        resp = requests.post(url, json={}, timeout=10)
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
        resp = requests.put(url, json=body, timeout=10)
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
            resp = requests.put(url, json={"displayname": displayname}, timeout=10)
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
        resp = requests.post(url, json=body, timeout=15)
        if resp.status_code == 200:
            room_id = resp.json().get("room_id")
            logger.info("已创建房间 %s (%s)", name, room_id)
            return room_id
        logger.warning("创建房间失败: %s %s", resp.status_code, resp.text)
        return None

    def invite_user(self, room_id: str, user_id: str) -> None:
        """把某用户邀请进房间。"""
        url = self._url(f"/_matrix/client/v3/rooms/{quote(room_id)}/invite")
        resp = requests.post(url, json={"user_id": user_id}, timeout=10)
        if resp.status_code == 200:
            logger.info("已邀请 %s 进 %s", user_id, room_id)
        else:
            logger.warning(
                "邀请 %s 进 %s 失败: %s %s", user_id, room_id, resp.status_code, resp.text
            )

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
        resp = requests.put(url, json=payload, timeout=10)
        if resp.status_code == 200:
            return resp.json().get("event_id")
        logger.warning("发送富卡失败: %s %s", resp.status_code, resp.text)
        return None

    def joined_member_count(self, room_id: str) -> int:
        """查房间当前已加入的成员数（用于区分"私聊"和"群聊"）。

        私聊（只有用户 + 主 AI，共 2 人）里，主 AI 对每句话都回；
        群聊里则只在被 @ 时才回。查不到就保守按群聊处理。
        """
        url = self._url(f"/_matrix/client/v3/rooms/{quote(room_id)}/joined_members")
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                return len(resp.json().get("joined", {}))
        except requests.RequestException:
            pass
        return 99
