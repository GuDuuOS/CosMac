"""GuDuu 主 AI —— Application Service Bot（最小骨架）。

职责（第一步，主 AI 控制层的地基）：
  1. 启动一个 HTTP 服务，接收 Synapse 推送过来的事件（这是主 AI 的"眼睛"）。
  2. 看到群里每一条文本消息。
  3. 被邀请进群时自动加入。
  4. 对收到的消息，调用 AI 模型生成回复，并发回群（这是主 AI 的"嘴"）。

后续会在这个地基上扩展：让 AI 真正"理解"消息、调用创建群/查记录等 IM 能力、
接入群级记忆与知识库等。

技术说明：用 Python 标准库 http.server 起服务（开发够用、无额外依赖）；
对 Synapse 的反向调用走 guduu.bots.matrix_client。
"""

from __future__ import annotations

import json
import logging
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Set

from guduu.ai import Message, get_provider
from guduu.ai.base import LLMProvider
from guduu.bots.matrix_client import MatrixClient
from guduu.config import GuduuConfig

logger = logging.getLogger("guduu.appservice_bot")


class GuduuBot:
    """主 AI 的事件处理核心：把 Synapse 推来的事件变成 AI 的反应。"""

    def __init__(self, config: GuduuConfig):
        self.config = config
        # 主 AI 操作 IM 的"手"
        self.client = MatrixClient(
            homeserver_url=config.homeserver_url,
            as_token=config.as_token,
            bot_user_id=config.bot_user_id,
        )
        # 主 AI 的"大脑"（可配置的多模型后端）
        self.llm: LLMProvider = get_provider(config)
        # 已处理过的事务 id，用于去重（Synapse 可能重发同一批事件）
        self._seen_txns: Set[str] = set()

    # —— 事件分发 ——

    def handle_transaction(self, txn_id: str, events: List[Dict[str, Any]]) -> None:
        """处理 Synapse 推来的一批事件（一个事务）。"""
        # 同一个事务只处理一次，避免重复回复
        if txn_id in self._seen_txns:
            logger.info("事务 %s 已处理过，跳过", txn_id)
            return
        self._seen_txns.add(txn_id)

        for event in events:
            try:
                self._handle_event(event)
            except Exception:  # 单条事件出错不应拖垮整批
                logger.exception("处理事件出错: %s", event.get("event_id"))

    def _handle_event(self, event: Dict[str, Any]) -> None:
        """处理单条事件。"""
        sender = event.get("sender", "")
        event_type = event.get("type", "")
        room_id = event.get("room_id", "")

        # 忽略主 AI 自己发的消息，否则会无限自我回复
        if sender == self.config.bot_user_id:
            return

        # 1) 被邀请进群 → 自动加入
        if event_type == "m.room.member":
            membership = event.get("content", {}).get("membership")
            state_key = event.get("state_key")
            if state_key == self.config.bot_user_id and membership == "invite":
                logger.info("收到来自 %s 的入群邀请，自动加入 %s", sender, room_id)
                self.client.join_room(room_id)
            return

        # 2) 群里的文本消息 → 喂给 AI，生成回复并发回群
        if event_type == "m.room.message":
            content = event.get("content", {})
            if content.get("msgtype") != "m.text":
                return  # 第一步只处理纯文本，图片/文件等以后再说
            user_text = content.get("body", "")
            logger.info("[房间 %s] %s 说: %s", room_id, sender, user_text)

            # 调用可配置的 AI 后端生成回复
            reply = self.llm.complete([Message(role="user", content=user_text)])
            self.client.send_text(room_id, reply)


class _Handler(BaseHTTPRequestHandler):
    """HTTP 请求处理器：实现 Matrix Application Service 协议的服务端。

    Synapse 会向我们发起：
      - PUT  .../transactions/{txnId} —— 推送一批事件（核心）。
      - GET  .../users/{userId}       —— 查询某用户是否归我们管。
    """

    # 由工厂注入的对象
    bot: GuduuBot
    hs_token: str

    # 关掉默认那行嘈杂的访问日志，改用我们自己的 logger
    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: N802
        logger.debug("HTTP " + fmt, *args)

    def _check_auth(self) -> bool:
        """校验请求确实来自我们的 Synapse（比对 hs_token）。

        Synapse 会通过 Authorization: Bearer <hs_token> 头，或老式的
        ?access_token= 查询参数携带 token，两种都兼容一下。
        """
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return auth[len("Bearer "):] == self.hs_token
        # 兼容老式查询参数
        if "access_token=" in self.path:
            token = self.path.split("access_token=", 1)[1].split("&", 1)[0]
            return token == self.hs_token
        return False

    def _send_json(self, status: int, body: Dict[str, Any]) -> None:
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_PUT(self) -> None:  # noqa: N802
        # 只接收事务推送
        if "/transactions/" not in self.path:
            self._send_json(404, {"errcode": "M_UNRECOGNIZED"})
            return
        if not self._check_auth():
            self._send_json(403, {"errcode": "M_FORBIDDEN"})
            return

        # 从路径里取出事务 id（.../transactions/{txnId}?...）
        txn_id = self.path.split("/transactions/", 1)[1].split("?", 1)[0]

        # 读取请求体（里面是事件数组）
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            self._send_json(400, {"errcode": "M_NOT_JSON"})
            return

        events = data.get("events", [])
        self.bot.handle_transaction(txn_id, events)

        # 必须回 200 + {}，否则 Synapse 会认为推送失败并重试
        self._send_json(200, {})

    def do_GET(self) -> None:  # noqa: N802
        # Synapse 查询"这个用户/别名是否归你管"，回 200 表示存在
        if "/users/" in self.path or "/rooms/" in self.path:
            if not self._check_auth():
                self._send_json(403, {"errcode": "M_FORBIDDEN"})
                return
            self._send_json(200, {})
            return
        self._send_json(404, {"errcode": "M_UNRECOGNIZED"})


def run(config: GuduuConfig) -> None:
    """启动主 AI Bot 的 HTTP 服务，开始监听 Synapse 推来的事件。"""
    bot = GuduuBot(config)

    # 把 bot 和 hs_token 注入到 Handler 类上（http.server 用类、不便传参，用 partial 构造）
    handler_cls = partial(_make_handler, bot=bot, hs_token=config.hs_token)

    server = ThreadingHTTPServer((config.listen_host, config.listen_port), handler_cls)
    logger.info(
        "GuDuu 主 AI Bot 已启动: 监听 http://%s:%d ，连接 Synapse %s ，模型后端=%s",
        config.listen_host,
        config.listen_port,
        config.homeserver_url,
        config.llm_provider,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("收到中断信号，正在关闭…")
        server.shutdown()


def _make_handler(*args: Any, bot: GuduuBot, hs_token: str, **kwargs: Any) -> _Handler:
    """构造一个带有 bot/hs_token 的请求处理器实例。"""
    handler = _Handler.__new__(_Handler)
    handler.bot = bot
    handler.hs_token = hs_token
    _Handler.__init__(handler, *args, **kwargs)
    return handler
