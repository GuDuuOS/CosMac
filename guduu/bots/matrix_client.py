"""对 Synapse 的最小客户端封装（主 AI 的"手"）。

主 AI 通过这里去操作 IM —— 当前只实现了"加入房间"和"发文本消息"两件事，
后续"创建群、查聊天记录、踢人"等能力都会作为新方法加到这里。

实现方式：用 appservice 的 as_token 直接调用 Synapse 的 Client-Server API。
appservice token 的默认身份就是注册文件里的 sender_localpart（即 @guduu）。
"""

from __future__ import annotations

import logging
import time
from typing import Optional
from urllib.parse import quote

import requests

logger = logging.getLogger("guduu.matrix_client")


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
