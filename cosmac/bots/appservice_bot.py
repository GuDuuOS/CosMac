"""CosMac Star 主 AI —— Application Service Bot（最小骨架）。

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
import time
from dataclasses import replace
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional, Set, Tuple

from cosmac.ai import get_provider
from cosmac.ai.agent import Agent
from cosmac.ai.base import LLMProvider
from cosmac.ai.tools import Toolbox, ToolContext
from cosmac.bots.matrix_client import MatrixClient
from cosmac.config import AI_CONFIG_EVENT_TYPE, CosmacConfig

logger = logging.getLogger("cosmac.appservice_bot")


class CosmacBot:
    """主 AI 的事件处理核心：把 Synapse 推来的事件变成 AI 的反应。"""

    def __init__(self, config: CosmacConfig):
        self.config = config
        # 主 AI 操作 IM 的"手"
        self.client = MatrixClient(
            homeserver_url=config.homeserver_url,
            as_token=config.as_token,
            bot_user_id=config.bot_user_id,
        )
        # 主 AI 的"大脑"（可配置的多模型后端）
        self.llm: LLMProvider = get_provider(config)
        # 主 AI 的"工具箱"（把指令落成真实 IM 操作）+ "会动手的大脑"Agent
        self.toolbox = Toolbox(self.client)
        self.agent = Agent(
            llm=self.llm,
            toolbox=self.toolbox,
            system_prompt=config.system_prompt,
        )
        # 已处理过的事务 id，用于去重（Synapse 可能重发同一批事件）
        self._seen_txns: Set[str] = set()

        # —— 运行时 AI 配置（管理后台「AI 配置」下发）——
        self._control_room: Optional[str] = None  # 控制室 room_id（别名解析一次后缓存）
        self._cfg_cache: Dict[str, Any] = {}        # 上次读到的配置覆盖
        # 上次读取时间（缓存 20s，别每条消息都打服务器）。
        # 用 -inf 当"从未读过"的哨兵：保证首次必读（monotonic 起点不定，别用 0）。
        self._cfg_cache_ts: float = float("-inf")
        # 当前已生效的 (provider, model, system_prompt) 签名；变了才热重建模型/Agent
        self._applied_sig: Tuple[str, str, str] = (
            config.llm_provider, config.llm_model, config.system_prompt,
        )

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

        # 2) 群里的文本消息
        if event_type == "m.room.message":
            content = event.get("content", {})
            if content.get("msgtype") != "m.text":
                return  # 第一步只处理纯文本，图片/文件等以后再说
            user_text = content.get("body", "")

            # 私聊（仅用户+主AI，≤2人）里对每句话都回；
            # 群聊里只在被 @ 提及时才回（避免误触发/刷屏）。
            is_dm = self.client.joined_member_count(room_id) <= 2
            if not is_dm and not self._is_bot_mentioned(content):
                return
            logger.info(
                "[房间 %s|%s] %s: %s",
                room_id, "私聊" if is_dm else "群@", sender, user_text,
            )

            # 去掉开头的 @提及，拿到真正的指令/内容
            text = self._strip_mention(user_text)

            # 2a) 确定性命令快路（建专班等）。命中就执行动作、不再走 Agent。
            #     保留它做"一句话直接出富卡派单"的演示；自然语言走下面的 Agent。
            if self._try_handle_command(room_id, sender, text):
                return

            # 2b) 否则交给会"动手"的 Agent：它能边想边调用工具（建群/发消息/查记录），
            #     最后把结论发回群。（echo 后端不支持工具，会自动退化为纯文本回复。）
            # 回复前先按管理后台下发的运行时配置（人设/模型/工具开关）对齐一次。
            self._apply_runtime_config()
            reply = self.agent.run(
                text or user_text,
                ToolContext(room_id=room_id, sender=sender),
            )
            self.client.send_text(room_id, reply)

    # —— 运行时 AI 配置：管理后台写控制室 state event，bot 读并应用 ——

    def _read_overrides(self) -> Dict[str, Any]:
        """从控制室读取 AI 配置覆盖。带 20s 缓存；任何失败都返回上次缓存/空，
        从而**完全回退到启动配置**（控制室不存在/未加入/网络错都不影响正常回话）。
        """
        now = time.monotonic()
        if now - self._cfg_cache_ts < 20:
            return self._cfg_cache
        overrides: Dict[str, Any] = {}
        try:
            # 别名只解析一次，之后缓存 room_id
            if not self._control_room:
                self._control_room = self.client.resolve_alias(
                    self.config.control_room_alias
                )
            if self._control_room:
                ev = self.client.get_state_event(
                    self._control_room, AI_CONFIG_EVENT_TYPE
                )
                if isinstance(ev, dict):
                    # 只取我们认识的字段，避免脏数据
                    for k in ("model", "system_prompt", "enabled_tools"):
                        if k in ev:
                            overrides[k] = ev[k]
        except Exception:  # 读配置绝不能拖垮回话
            logger.exception("读取运行时 AI 配置失败，沿用启动配置")
            overrides = self._cfg_cache  # 沿用上次成功的
        self._cfg_cache = overrides
        self._cfg_cache_ts = now
        return overrides

    def _apply_runtime_config(self) -> None:
        """把控制室下发的配置应用到 llm/agent/toolbox（按需热重建，幂等）。"""
        ov = self._read_overrides()
        # 模型/人设：与启动配置合并（覆盖项缺省时用启动值）。
        # provider 本期不开放前端改（避免切到没 key 的后端→静默降级 echo）。
        model = ov.get("model") or self.config.llm_model
        system_prompt = ov.get("system_prompt") or self.config.system_prompt
        sig = (self.config.llm_provider, model, system_prompt)
        if sig != self._applied_sig:
            try:
                cfg = replace(
                    self.config, llm_model=model, system_prompt=system_prompt
                )
                self.llm = get_provider(cfg)
                self.agent = Agent(
                    llm=self.llm, toolbox=self.toolbox, system_prompt=system_prompt
                )
                self._applied_sig = sig
                logger.info("已应用运行时 AI 配置: model=%s 人设已更新", model or "默认")
            except Exception:
                logger.exception("应用运行时 AI 配置失败，沿用当前模型")
        # 工具开关：enabled_tools 是字符串列表 → 只启用这些；缺省/非法 = 全开
        enabled = ov.get("enabled_tools")
        self.toolbox.set_enabled(
            set(enabled) if isinstance(enabled, list) else None
        )

    # —— @ 提及识别：只有被 @ 才响应 ——

    def _bot_localpart(self) -> str:
        """从完整用户 id（@guduu:cosmac.cc）取出 localpart（guduu）。"""
        return self.config.bot_user_id.split(":", 1)[0].lstrip("@")

    def _mention_tokens(self) -> List[str]:
        """所有"算作在叫主 AI"的开头词（大小写不敏感比较）。

        这样用户不用跟 Element 的 @ 弹窗较劲——消息开头直接打 'CosMac' 即可。
        """
        lp = self._bot_localpart()
        return [
            self.config.bot_user_id,        # @guduu:cosmac.cc（@pill）
            f"@{lp}",                        # @guduu
            self.config.bot_displayname,     # CosMac Star
            "CosMac Star",
            "@CosMac",
            "CosMac",                        # 直接打名字开头就算叫它
        ]

    def _is_bot_mentioned(self, content: Dict[str, Any]) -> bool:
        """判断这条消息是否在叫主 AI（被 @ 或以它的名字开头）。"""
        # 1) 现代客户端：标准 m.mentions.user_ids 字段（最可靠）
        mentions = content.get("m.mentions") or {}
        if self.config.bot_user_id in (mentions.get("user_ids") or []):
            return True
        body = (content.get("body") or "").strip()
        low = body.lower()
        # 2) 以 bot 名字 / @ 开头 = 在叫它
        if any(low.startswith(t.lower()) for t in self._mention_tokens()):
            return True
        # 3) 正文里出现完整用户 id（@pill）
        return self.config.bot_user_id in body

    def _strip_mention(self, text: str) -> str:
        """去掉开头的"叫它"前缀（@pill / 名字），留下真正的指令文本。"""
        text = text.strip()
        low = text.lower()
        for token in self._mention_tokens():
            if low.startswith(token.lower()):
                text = text[len(token):]
                break
        return text.lstrip(" :：,，@")

    # —— 主 AI 的"手"：把指令落成真实的 IM 操作 ——
    # 第一步用确定性的斜杠命令验证"建群+拉人+发富卡"全链路；
    # 第二步会换成 LLM 工具调用，让自然语言自动触发这些动作。

    def _try_handle_command(self, room_id: str, sender: str, text: str) -> bool:
        """识别并执行 IM 控制命令。命中返回 True，否则 False（交回对话处理）。

        目前支持（注意不要用 / 开头，否则会被 Element 当成它自己的客户端命令拦截）：
            建专班 <名字> / 专班 <名字>   → 新建专班群、拉发起人进去、发一张派单富卡
        （也兼容 /专班，万一用户在 Element 里点了"作为消息发送"）
        """
        text = text.strip()
        for prefix in ("建专班", "/专班", "专班"):
            if text.startswith(prefix):
                name = text[len(prefix):].strip(" :：") or "新专班"
                self._launch_campaign(room_id, sender, name)
                return True
        return False

    def _launch_campaign(self, origin_room: str, requester: str, name: str) -> None:
        """建一个专班群、拉发起人进来，并在群里发一张"派单"富卡。"""
        new_room = self.client.create_room(name, invitees=[requester])
        if not new_room:
            self.client.send_text(origin_room, f"抱歉，建专班「{name}」失败了，请稍后再试。")
            return

        # 派单富卡：body 是纯文本兜底（Element 显示这个），card 是结构化数据（CosMac 客户端渲染）
        card = {
            "kind": "dispatch",
            "title": f"{name} · 专班已建立",
            "subtitle": "由 CosMac Star 中枢自动派单",
            "rows": [
                {"task": "选题锁定", "owner": "选题 Agent", "type": "ai"},
                {"task": "脚本撰写", "owner": "文案 Agent", "type": "ai"},
                {"task": "数据排期", "owner": "数据 Agent", "type": "ai"},
                {"task": "拍板确认", "owner": requester, "type": "human"},
            ],
        }
        body = (
            f"【{name}】专班已建立，派单如下：\n"
            "· 选题锁定 → 选题 Agent\n"
            "· 脚本撰写 → 文案 Agent\n"
            "· 数据排期 → 数据 Agent\n"
            f"· 拍板确认 → {requester}"
        )
        self.client.send_card(new_room, body, card)
        self.client.send_text(
            origin_room, f"已为你建立专班「{name}」并把你拉进群，派单已发到新群里。"
        )


class _Handler(BaseHTTPRequestHandler):
    """HTTP 请求处理器：实现 Matrix Application Service 协议的服务端。

    Synapse 会向我们发起：
      - PUT  .../transactions/{txnId} —— 推送一批事件（核心）。
      - GET  .../users/{userId}       —— 查询某用户是否归我们管。
    """

    # 由工厂注入的对象
    bot: CosmacBot
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


def run(config: CosmacConfig) -> None:
    """启动主 AI Bot 的 HTTP 服务，开始监听 Synapse 推来的事件。"""
    bot = CosmacBot(config)
    # 启动时把主 AI 的群内显示名设为品牌名（用户看到的是它，而非 @guduu 用户 id）
    bot.client.set_displayname(config.bot_displayname)

    # 把 bot 和 hs_token 注入到 Handler 类上（http.server 用类、不便传参，用 partial 构造）
    handler_cls = partial(_make_handler, bot=bot, hs_token=config.hs_token)

    server = ThreadingHTTPServer((config.listen_host, config.listen_port), handler_cls)
    logger.info(
        "CosMac Star 主 AI Bot 已启动: 监听 http://%s:%d ，连接 Synapse %s ，模型后端=%s",
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


def _make_handler(*args: Any, bot: CosmacBot, hs_token: str, **kwargs: Any) -> _Handler:
    """构造一个带有 bot/hs_token 的请求处理器实例。"""
    handler = _Handler.__new__(_Handler)
    handler.bot = bot
    handler.hs_token = hs_token
    _Handler.__init__(handler, *args, **kwargs)
    return handler
