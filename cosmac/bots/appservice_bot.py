"""CosMac Star 主 AI —— Application Service Bot（最小骨架）。

职责（第一步，主 AI 控制层的地基）：
  1. 启动一个 HTTP 服务，接收 Synapse 推送过来的事件（这是主 AI 的"眼睛"）。
  2. 看到群里每一条文本消息。
  3. 被邀请进群时自动加入。
  4. 对收到的消息，调用 AI 模型生成回复，并发回群（这是主 AI 的"嘴"）。

后续会在这个地基上扩展：让 AI 真正"理解"消息、调用创建群/查记录等 IM 能力、
接入群级记忆与知识库等。

技术说明：用 Python 标准库 http.server 起服务（开发够用、无额外依赖）；
对 Synapse 的反向调用走 cosmac.bots.matrix_client。
"""

from __future__ import annotations

import hmac
import json
import logging
import socket
import threading
import time
from collections import OrderedDict
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional, Set, Tuple

from cosmac.ai import build_provider, get_provider
from cosmac.ai.agent import Agent
from cosmac.ai.base import LLMProvider, Message
from cosmac.ai.tools import Toolbox, ToolContext
from cosmac.bots.matrix_client import MatrixClient
from cosmac.config import (
    AGENTS_EVENT_TYPE,
    AI_CONFIG_EVENT_TYPE,
    CHANNEL_CONFIG_EVENT_TYPE,
    CONTROL_ADMINS_EVENT_TYPE,
    RULES_EVENT_TYPE,
    SKILLS_EVENT_TYPE,
    WORKFLOWS_EVENT_TYPE,
    CosmacConfig,
)
from cosmac.members import (
    GATE_ADMIN,
    MEMBER_TIERS,
    GatingStore,
    MembersStore,
    gate_capability_label,
    gate_rank,
    is_valid_tier,
    tier_label,
)
from cosmac.skills_text import render_skills  # 纯渲染、不依赖 DB

logger = logging.getLogger("cosmac.appservice_bot")

# 公开回调端点（外部工作流平台调）允许的最大请求体（防无认证内存 DoS）。
# 工作流结果文本不大、下游还会截断，512KB 绰绰有余。
_MAX_CALLBACK_BODY = 512 * 1024
# 回调结果发进群的消息正文上限（防超 Matrix 事件大小→send 持续失败→无限重试）。
_MAX_WF_MSG = 4000
# Synapse 事务推送请求体上限（纵深防御；批量事件给足余量）。
_MAX_TXN_BODY = 8 * 1024 * 1024


def _token_hash(token: str) -> str:
    """回调 token 只在 DB 里存**哈希**（#4）：DB/日志泄露也拿不到可用的明文 token。
    明文 token 只活在交给外部平台的回调地址里、且单次用完即废。"""
    import hashlib

    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


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
        self.toolbox = Toolbox(
            self.client, control_room_alias=config.control_room_alias
        )
        # 会员等级（账号权限分层）读写：控制室 cosmac.members（见 cosmac.members）。
        # 用于「会员」自查/管理命令，以及预留给模块4支付的 grant_member_tier。
        self.members = MembersStore(self.client, config.control_room_alias)
        # 功能门控策略：控制室 cosmac.gating（带 TTL 缓存）。后台配「能力→最低等级」，
        # bot 在执行点服务端强制（见 _gate_allows / _tool_gate_check）。
        self.gating = GatingStore(self.client, config.control_room_alias)
        # 让 run_workflow 工具能走异步连接器的回调协议（#1）：注入 bot 的 _dispatch_async。
        # 没配 public_url 时不注入——_dispatch_async 没有回调地址也没意义。
        if config.public_url:
            self.toolbox.dispatch_async = self._dispatch_async
        # 功能门控：把工具调用也接进会员门控（"让 AI 帮我建群/跑工作流"与命令同一道闸）。
        self.toolbox.gate_check = self._tool_gate_check
        self.agent = Agent(
            llm=self.llm,
            toolbox=self.toolbox,
            system_prompt=config.system_prompt,
        )
        # 已处理过的事务 id，用于去重（Synapse 可能重发同一批事件）。
        # #2：用有界 LRU(OrderedDict) 防无限增长；并尽力持久化到 DB，重启后也能识别重放。
        self._seen_txns: "OrderedDict[str, None]" = OrderedDict()
        self._seen_txn_calls = 0  # 计数器，偶尔触发一次 DB 旧记录清理
        # 「按群模型覆盖」用的 Agent 缓存：model_id → Agent（同 provider 换 model）。
        # 全局配置(provider/人设)变化时清空，避免用到旧 provider/人设构建的实例。
        self._model_agents: Dict[str, Agent] = {}

        # —— 运行时 AI 配置（管理后台「AI 配置」下发）——
        self._control_room: Optional[str] = None  # 控制室 room_id（别名解析一次后缓存）
        self._cfg_cache: Dict[str, Any] = {}        # 上次读到的配置覆盖
        # 上次读取时间（缓存 20s，别每条消息都打服务器）。
        # 用 -inf 当"从未读过"的哨兵：保证首次必读（monotonic 起点不定，别用 0）。
        self._cfg_cache_ts: float = float("-inf")
        # 当前已生效的 (provider, model, system_prompt, _) 签名；任一项变了才热重建模型/Agent。
        # 第 4 段保留位恒为 ""（key 只走环境变量、绝不进签名，见 _apply_runtime_config）。
        self._applied_sig: Tuple[str, str, str, str] = (
            config.llm_provider, config.llm_model, config.system_prompt, "",
        )

    # —— 事件分发 ——

    _SEEN_TXN_MAX = 4096  # 内存去重 LRU 上限（防无限增长）

    def handle_transaction(self, txn_id: str, events: List[Dict[str, Any]]) -> bool:
        """处理 Synapse 推来的一批事件（一个事务）。返回是否可回 200。

        去重 + 崩溃安全（#2/#3）：内存有界 LRU 快路 + DB **原子两阶段抢占**。
          - True ：已处理完 / 已是重复（回 200，告诉 Synapse 别重发）。
          - False：另一处理中(未过期)，或 DB 暂判定让位（回非 200，让 Synapse 稍后重试）——
                   避免重复处理，也避免"先标记后处理"在崩溃时永久丢一整批。
        """
        # 内存快路：本进程已处理过直接跳过（也是 DB 不可用时的唯一防线）
        if txn_id in self._seen_txns:
            logger.info("事务 %s 已处理过（内存），跳过", txn_id)
            return True

        # DB 原子抢占。DB 不可用 → None，退回"内存标记后处理"（尽力而为）。
        status = self._claim_txn(txn_id)
        if status == "done":
            self._remember_txn(txn_id)  # 回填内存，下次走快路
            logger.info("事务 %s 已处理完（持久化），跳过重放", txn_id)
            return True
        if status == "inflight":
            # 另一处理中且未过期：不重复处理，让 Synapse 稍后重试（届时多半已 done→200）
            logger.info("事务 %s 正在处理中，让上游稍后重试", txn_id)
            return False

        # status == "claimed"（抢到）或 None（无 DB，退回内存去重）：占住并处理
        for event in events:
            try:
                self._handle_event(event)
            except Exception:  # 单条事件出错不应拖垮整批（也不触发整批重投）
                logger.exception("处理事件出错: %s", event.get("event_id"))
        # #1：**处理成功后**才标记 done + 记内存。绝不能在处理前就写内存——否则处理途中
        # Synapse 超时重试会命中内存快路直接回 200，原处理若随后崩溃，DB 的 processing
        # 再没机会被重抢（Synapse 已不再重试）→ 整批永久丢。
        # 进程崩在处理中途则到不了这里：DB 行留 processing、内存也没记，过期后由 Synapse
        # 重试时 claim 重新抢占重处理（at-least-once，不永久丢）。
        self._finish_txn(txn_id)
        self._remember_txn(txn_id)
        return True

    def recover_interrupted_runs(self) -> None:
        """启动时结清上次进程遗留的未完成工作流运行并通知用户（尽力而为，#2）。

        进程内线程池不跨重启——in-flight/排队的提交与 ComfyUI 轮询随旧进程一起消失，
        对应的 pending/processing 永远等不到完成。这里在启动时一次性收口：标记失败、
        告诉用户"因服务重启中断、请重试"，避免永久干等。DB 不可用则跳过。
        （注意：这是"让中断**可见**"，不是"恢复执行"——真要不丢任务需durable队列，见架构说明。）
        """
        try:
            from cosmac.db import session_scope
            from cosmac.db.wf_repo import reclaim_orphans

            with session_scope() as s:
                orphans = reclaim_orphans(s)
        except Exception:
            return  # 没 DB / 出错：跳过，不阻断启动
        for run_id, slug, room_id in orphans:
            if not room_id:
                continue
            try:
                # 固定 txn id：万一通知本身重发也被 Synapse 去重，群里不重复
                self.client.send_text(
                    room_id,
                    f"⚠️ 工作流「{slug}」(#{run_id}) 因服务重启中断，请重试。",
                    txn_id=f"cosmac-wf-orphan-{run_id}",
                )
            except Exception:
                logger.warning("通知中断运行失败 run_id=%s", run_id)
        if orphans:
            logger.info("启动时结清 %d 条中断的工作流运行", len(orphans))

    def _remember_txn(self, txn_id: str) -> None:
        """记进内存有界 LRU；超上限淘汰最旧的。"""
        self._seen_txns[txn_id] = None
        self._seen_txns.move_to_end(txn_id)
        while len(self._seen_txns) > self._SEEN_TXN_MAX:
            self._seen_txns.popitem(last=False)

    def _claim_txn(self, txn_id: str) -> Optional[str]:
        """DB 原子抢占（尽力而为）。返回 'claimed'/'done'/'inflight'；DB 不可用返回 None。"""
        try:
            from cosmac.db import session_scope
            from cosmac.db.dedup import claim_txn

            with session_scope() as s:
                return claim_txn(s, txn_id)
        except Exception:
            return None  # 没 DB → 调用方退回内存去重，不阻断收消息

    def _finish_txn(self, txn_id: str) -> None:
        """标记事务处理完成（尽力而为）；偶尔顺手清理过期记录控制表大小。"""
        try:
            from cosmac.db import session_scope
            from cosmac.db.dedup import finish_txn, prune_old

            with session_scope() as s:
                finish_txn(s, txn_id)
                self._seen_txn_calls += 1
                if self._seen_txn_calls % 500 == 0:
                    prune_old(s)
        except Exception:
            pass  # 没 DB 就只靠内存去重，不阻断收消息

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

        # 1b) 控制室「期望管理员集」变化 → 主 AI(power 100)对齐控制室成员：
        #     把不再是服务器管理员、却仍有写权限的成员降权 + 踢出。这是浏览器(管理员
        #     power 只有 50)做不到的——同级互相无法降权/踢出，所以交给 100 的 bot 执行。
        if event_type == CONTROL_ADMINS_EVENT_TYPE and event.get("state_key") is not None:
            self._reconcile_control_members(room_id, event.get("content", {}))
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

            # 2b) 否则交给会"动手"的 Agent。但先过「基础 AI 对话」门控：低于门槛的用户
            #     @ 中枢AI 会被礼貌提示升级（命令如「会员/技能/知识/工作流」已在上面处理、
            #     不受此门控影响——保证用户随时能查/升级会员）。
            if not self._gate_allows(sender, "ai_chat"):
                self.client.send_text(room_id, self._gate_denied_text("ai_chat"))
                return
            #     它能边想边调用工具（建群/发消息/查记录），最后把结论发回群。
            #     （echo 后端不支持工具，会自动退化为纯文本回复。）
            # 回复前先按管理后台下发的运行时配置（人设/模型/工具开关）对齐一次。
            self._apply_runtime_config()
            # 本群上下文读一次（人设/绑定技能/模型覆盖），供 addendum 与选模型共用。
            gctx = self._group_context(room_id)
            # 按 (本群, 发起人) 算出本轮 system addendum：人设 + 技能 + 知识库检索片段(RAG)。
            # 任何失败（DB 没装/没数据/出错）都返回空串、绝不阻断回复（见 _skill_addendum）。
            extra_system = self._skill_addendum(
                room_id, sender, query=text or user_text, gctx=gctx
            )
            # 短期记忆：把本房间最近的对话(不含当前这条)喂给模型，主 AI 才"记得"上文。
            history = self._recent_history(room_id, sender, user_text)
            # 本群若绑定的智能体指定了模型 → 用该模型的 Agent 回这条（否则用默认 Agent）。
            agent = self._agent_for_model(gctx.get("model", ""))
            reply = agent.run(
                text or user_text,
                ToolContext(room_id=room_id, sender=sender),
                extra_system=extra_system,
                history=history,
            )
            self.client.send_text(room_id, reply)

    # 短期记忆窗口：最多带最近这么多条历史；单条正文截断长度（控 token）。
    _HISTORY_LIMIT = 12
    _HISTORY_CHARS = 600

    def _recent_history(
        self, room_id: str, cur_sender: str, cur_body: str
    ) -> List[Message]:
        """读本房间最近消息，映射成对话历史(不含当前这条)，给主 AI 短期记忆。

        聊天记录存在 Synapse(见 CLAUDE.md §3，不重存)，这里实时读最近 N 条。
        bot 自己发的→assistant，其它人→user。任何失败都返回空(不阻断回复)。
        """
        try:
            msgs = self.client.get_messages(room_id, limit=self._HISTORY_LIMIT + 1)
        except Exception as e:
            logger.debug("读历史失败（忽略，无短期记忆继续）：%s", e)
            return []
        out: List[Message] = []
        dropped_current = False
        for m in msgs:
            body = (m.get("body") or "").strip()
            s = m.get("sender") or ""
            if not body:
                continue
            # 跳过"当前这条触发消息"(它会作为最后的 user 单独追加，避免重复)
            if not dropped_current and s == cur_sender and body == (cur_body or "").strip():
                dropped_current = True
                continue
            if len(body) > self._HISTORY_CHARS:
                body = body[: self._HISTORY_CHARS] + "…"
            role = "assistant" if s == self.config.bot_user_id else "user"
            out.append(Message(role=role, content=body))
        return out[-self._HISTORY_LIMIT:]

    def _skill_addendum(
        self,
        room_id: str,
        sender: str,
        query: str = "",
        gctx: Optional[Dict[str, Any]] = None,
    ) -> str:
        """拼出本轮注入主 AI 的 system addendum = 人设 + 技能 + 知识库检索片段(RAG)。

        多来源、各自兜异常、互不拖累：
          - **人设/技能**：控制室 state event(全局) + cosmac DB(群/个人) + 绑定的智能体。
          - **知识库(RAG)**：按 query 检索本群/个人知识库 top-K 片段(cosmac DB)。
        **绝不能因为它出问题就让主 AI 不回话**——任一来源异常都只是少注入、不抛出。
        """
        try:
            # 平台级硬约束（全局规则）——放最前、优先级最高
            rules_text = self._global_rules_text()
            # 本群上下文（人设/绑定技能/模型）——_handle_event 已读则复用，避免重复读
            if gctx is None:
                gctx = self._group_context(room_id)
            persona = gctx.get("persona", "")
            agent_slugs = gctx.get("skill_slugs", [])
            items = (
                self._global_skill_items()
                + self._db_skill_items(room_id, sender)
                + self._agent_skill_items(agent_slugs)
            )
            # 按 slug 去重（全局已注入的技能若又被 Agent 绑定，不重复注入；保留首次出现）
            seen: Set[str] = set()
            deduped: List[Dict[str, Any]] = []
            for it in items:
                slug = str(it.get("slug") or "")
                if slug and slug in seen:
                    continue
                seen.add(slug)
                deduped.append(it)
            skills_text = render_skills(deduped)
            kb_text = self._kb_context(room_id, sender, query)
            # 规则(硬约束) → 人设 → 技能 → 知识库，依次拼成本轮 addendum
            return "\n\n".join(p for p in (rules_text, persona, skills_text, kb_text) if p)
        except Exception as e:
            # 兜住**最终组装**：脏数据绝不能让这条消息收不到回复（docstring 的承诺）
            logger.debug("组装 addendum 失败（忽略，按无附加继续）：%s", e)
            return ""

    def _global_rules_text(self) -> str:
        """读控制室「全局规则」state event，渲染成「必须遵守」块（失败返回空）。"""
        try:
            ctrl = self.client.resolve_alias(self.config.control_room_alias)
            if not ctrl:
                return ""
            ev = self.client.get_state_event(ctrl, RULES_EVENT_TYPE) or {}
            texts = [
                str(r.get("text") or "").strip()
                for r in (ev.get("rules") or [])
                if isinstance(r, dict) and r.get("enabled", True)
            ]
            texts = [t for t in texts if t]
            if not texts:
                return ""
            lines = ["【必须严格遵守的平台规则，优先级高于其它指示】："]
            lines += [f"{i}. {t}" for i, t in enumerate(texts, 1)]
            return "\n".join(lines)
        except Exception as e:
            logger.debug("读取全局规则失败（忽略）：%s", e)
            return ""

    def _kb_context(self, room_id: str, sender: str, query: str) -> str:
        """RAG：按 query 检索本群+个人知识库 top-K 片段，渲染成「参考资料」块。

        cosmac.db 懒导入 + 全程兜异常：没装 SQLAlchemy / 无文档 / 出错都返回空串。
        min_score 过滤掉太不相关的（哈希兜底嵌入下尤其重要，避免硬塞无关内容）。
        """
        q = (query or "").strip()
        if not q:
            return ""
        # 知识库门控：低于门槛的用户在普通对话里也不享受 RAG 注入（与知识命令同一道闸）
        if not self._gate_allows(sender, "knowledge"):
            return ""
        try:
            from cosmac.ai.embeddings import get_embedder
            from cosmac.db import session_scope
            from cosmac.db.kb import search
            from cosmac.db.models import SCOPE_ROOM, SCOPE_USER

            # #3：查询向量只算一次（embed_one 可能要打网络），群库/个人库共用，省一半请求
            emb = get_embedder()
            qvec = emb.embed_one(q)
            with session_scope() as s:
                hits = search(s, query=q, scope=SCOPE_ROOM, scope_id=room_id, k=3,
                              min_score=0.05, embedder=emb, qvec=qvec)
                hits += search(s, query=q, scope=SCOPE_USER, scope_id=sender, k=2,
                               min_score=0.05, embedder=emb, qvec=qvec)
                if not hits:
                    return ""
                hits.sort(key=lambda t: t[1], reverse=True)
                lines = ["参考以下「知识库」资料作答（与问题相关，未必完整）："]
                for i, (ch, _score) in enumerate(hits[:4], 1):
                    title = (ch.doc.title or "").strip()
                    lines.append(f"[{i}] 《{title}》 {ch.text}")
            return "\n".join(lines)
        except Exception as e:
            logger.debug("知识库检索失败（忽略，无 RAG 继续）：%s", e)
            return ""

    def _group_context(self, room_id: str) -> Dict[str, Any]:
        """读本群频道配置**一次**，得出 {persona, skill_slugs, model}。

        优先级：① 绑定了全局智能体(persona.agentSlug) → 用它的人设 + 绑定技能 + 模型覆盖；
                ② 否则用本群自定义人设(persona.prompt)。都没有 → 空。
        失败一律返回空 dict（绝不阻断回复）。
        """
        out: Dict[str, Any] = {"persona": "", "skill_slugs": [], "model": ""}
        try:
            cfg = self.client.get_state_event(room_id, CHANNEL_CONFIG_EVENT_TYPE) or {}
            persona = cfg.get("persona") or {}
            slug = (persona.get("agentSlug") or "").strip()
            if slug:
                agent = self._find_global_agent(slug)
                if agent:
                    name = agent.get("name") or slug
                    sp = (agent.get("system_prompt") or "").strip()
                    out["persona"] = (
                        f"本群已绑定智能体「{name}」，请始终以下述人设与职责回应：\n{sp}"
                    )
                    out["skill_slugs"] = [str(s) for s in (agent.get("skill_slugs") or [])]
                    out["model"] = (agent.get("model") or "").strip()
                    return out
            # 退回自定义人设（自由文本）
            free = (persona.get("prompt") or "").strip()
            if free:
                out["persona"] = f"本群人设：\n{free}"
            return out
        except Exception as e:
            logger.debug("读取本群上下文失败（忽略）：%s", e)
            return out

    def _agent_for_model(self, model: str) -> Agent:
        """按「本群模型覆盖」拿一个 Agent：没覆盖或与当前一致 → 用 self.agent；
        否则用**同 provider、换 model**构建一个并缓存（人设走 addendum、不在此设）。
        构建失败回退 self.agent，绝不阻断回复。"""
        model = (model or "").strip()
        provider, applied_model, applied_sys, _ = self._applied_sig
        if not model or model == applied_model:
            return self.agent
        cached = self._model_agents.get(model)
        if cached is not None:
            return cached
        try:
            llm = build_provider(
                provider, api_key="", model=model, system_prompt=applied_sys
            )
            ag = Agent(llm=llm, toolbox=self.toolbox, system_prompt=applied_sys)
            self._model_agents[model] = ag
            logger.info("按群模型构建 Agent: provider=%s model=%s", provider, model)
            return ag
        except Exception:
            logger.exception("按群模型 %s 构建失败，回退默认模型", model)
            return self.agent

    def _find_global_agent(self, slug: str) -> Optional[Dict[str, Any]]:
        """在控制室「全局智能体」里按 slug 找一个**启用**的智能体（找不到返回 None）。"""
        try:
            ctrl = self.client.resolve_alias(self.config.control_room_alias)
            if not ctrl:
                return None
            ev = self.client.get_state_event(ctrl, AGENTS_EVENT_TYPE) or {}
            for a in ev.get("agents") or []:
                if (
                    isinstance(a, dict)
                    and a.get("slug") == slug
                    and a.get("enabled", True)
                ):
                    return a
            return None
        except Exception as e:
            logger.debug("查找全局智能体失败（忽略）：%s", e)
            return None  # 当作没找到

    def _agent_skill_items(self, slugs: List[str]) -> List[Dict[str, Any]]:
        """把「智能体绑定的技能 slug」解析成技能字典——取启用的全局技能里 slug 命中的。"""
        if not slugs:
            return []
        want = set(slugs)
        return [s for s in self._global_skill_items() if str(s.get("slug")) in want]

    def _global_skill_items(self) -> List[Dict[str, Any]]:
        """读控制室「全局技能」state event，返回启用的技能字典列表（失败返回空）。"""
        try:
            ctrl = self.client.resolve_alias(self.config.control_room_alias)
            if not ctrl:
                return []
            ev = self.client.get_state_event(ctrl, SKILLS_EVENT_TYPE) or {}
            skills = ev.get("skills") or []
            return [
                s for s in skills
                if isinstance(s, dict) and s.get("enabled", True)
            ]
        except Exception as e:
            logger.debug("读取全局技能失败（忽略）：%s", e)
            return []

    def _db_skill_items(self, room_id: str, sender: str) -> List[Dict[str, Any]]:
        """从 cosmac DB 读本群/个人启用的技能（聊天命令建的），转成字典列表。

        cosmac.db 懒导入 + 全程兜异常：服务器没装 SQLAlchemy/读失败就返回空。
        """
        try:
            from cosmac.db import session_scope
            from cosmac.db.service import effective_skills

            with session_scope() as s:
                return [
                    {
                        "slug": k.slug,
                        "name": k.name,
                        "description": k.description,
                        "instructions": k.instructions,
                    }
                    for k in effective_skills(s, room_id=room_id, user_id=sender)
                ]
        except Exception as e:
            logger.debug("读取 DB 技能失败（忽略）：%s", e)
            return []

    # —— 控制室成员对齐：把已撤销的管理员降权 + 踢出（浏览器做不到，bot 用 100 权限做）——

    def _reconcile_control_members(
        self, room_id: str, content: Dict[str, Any]
    ) -> None:
        """按「期望管理员集」对齐控制室成员：移除不再是管理员、却仍有写权限的人。

        安全约束（务必守住，否则可能误踢）：
          - **只在确实是控制室时动手**：room_id 必须等于别名解析出的控制室，否则有人
            往任意房间塞这个事件就能借 bot 之手踢人。解析不到/对不上 → 直接不动。
          - **绝不动所有者和 bot 自己**：只移除 power < 100 的成员（owner/bot=100 跳过）。
          - 只“降权 + 踢出”不在期望集里的成员；其余一律不碰。任何异常都不抛、只记日志。
          - 降权/踢出**检查结果**：失败的明确报 error（被撤销者仍有写权限是安全问题），
            绝不无条件报成功；power≥100 的遗留成员 bot 无权移除，单独 warning。
        """
        desired = set(content.get("admins") or [])
        try:
            # 控制室校验：必须是别名解析出的那个房间
            ctrl = self.client.resolve_alias(self.config.control_room_alias)
        except Exception:
            logger.exception("对齐控制室成员：解析控制室别名失败，跳过")
            return
        if not ctrl or ctrl != room_id:
            logger.debug("对齐控制室成员：%s 非控制室，忽略", room_id)
            return

        try:
            pl = self.client.get_state_event(room_id, "m.room.power_levels", "") or {}
        except Exception:
            logger.exception("对齐控制室成员：读 power_levels 失败，跳过")
            return

        bot = self.config.bot_user_id
        users: Dict[str, Any] = dict(pl.get("users") or {})

        # #1 防御：power≥100 且不在期望集的成员——bot(=100) 在 Matrix 里**无法**降权/踢出
        # 同级或更高的人（历史遗留 bug 曾把管理员设成 100 才会出现）。无法自动修，明确告警，
        # 提示需要重建控制室；绝不把他们当 owner 静默跳过。
        stuck = [
            uid
            for uid, lvl in users.items()
            if uid != bot
            and isinstance(lvl, int)
            and lvl >= 100
            and uid not in desired
        ]
        if stuck:
            logger.warning(
                "控制室对齐：成员 %s 权限≥100 且已非管理员，bot 无权移除——"
                "该控制室需重建（早期 bug 把管理员设成了 100）。",
                stuck,
            )

        # 待移除：有显式写权限(50≤power<100) 且不在期望管理员集里的成员
        to_remove = [
            uid
            for uid, lvl in users.items()
            if uid != bot
            and isinstance(lvl, int)
            and lvl < 100
            and uid not in desired
        ]
        if not to_remove:
            return

        # ① 降权：从 users 里删掉这些人（回落 users_default=0），保留 power_levels 其它字段。
        #    #2：检查写入结果——失败说明被撤销者**仍有写权限**，是安全问题，必须报错。
        new_users = {u: lv for u, lv in users.items() if u not in to_remove}
        new_pl = {**pl, "users": new_users}
        if not self.client.set_power_levels(room_id, new_pl):
            logger.error(
                "控制室对齐：降权写入失败，被撤销者可能仍能写 AI 配置：%s", to_remove
            )
        # ② 踢出控制室——逐个检查结果，**只对真正踢成功的报成功**，失败的明确报错
        removed, failed = [], []
        for uid in to_remove:
            if self.client.kick(room_id, uid, "已撤销服务器管理员，移出控制室"):
                removed.append(uid)
            else:
                failed.append(uid)
        if removed:
            logger.info("控制室对齐：已降权并移除非管理员 %s", removed)
        if failed:
            logger.error(
                "控制室对齐：移除失败（权限不足或对方≥bot 权限），仍是控制室成员：%s",
                failed,
            )

    # —— 运行时 AI 配置：管理后台写控制室 state event，bot 读并应用 ——

    def _read_overrides(self) -> Dict[str, Any]:
        """从控制室读取 AI 配置覆盖。带 20s 缓存。

        关键安全语义（修掉"失效开放"）：
          - 读成功且有配置 → 用新配置并缓存；
          - 读成功但控制室没有配置(别名 404 / state 404) → 覆盖确实为空（属正常，
            全工具启用），缓存空；
          - 读失败(403 / 网络错 / 5xx 等) → **保留上次成功的缓存**，绝不因一次抖动
            把管理员设的工具限制/人设清空（client 的 resolve_alias/get_state_event
            现在对这类失败会抛异常，正好走 except 分支）。

        别名每轮都重新解析：控制室被删/重建/重指向后能跟上新 room_id（不再永久缓存）。
        """
        now = time.monotonic()
        if now - self._cfg_cache_ts < 20:
            return self._cfg_cache
        try:
            # 别名→room_id：每轮重解析；404 返回 None（控制室还没建），其它失败抛异常
            room = self.client.resolve_alias(self.config.control_room_alias)
            self._control_room = room  # 仅记录当前解析结果，不再当永久缓存
            overrides: Dict[str, Any] = {}
            if room:
                ev = self.client.get_state_event(room, AI_CONFIG_EVENT_TYPE)
                if isinstance(ev, dict):
                    # 只取我们认识的字段，避免脏数据。
                    # 安全：**绝不**从控制室事件读 api_key——state event 无法加密、会明文
                    # 进 DB/历史/被全员可读。密钥只走服务端环境变量/Secret Manager。
                    for k in (
                        "provider", "model", "system_prompt", "enabled_tools"
                    ):
                        if k in ev:
                            overrides[k] = ev[k]
            # 读成功（含"控制室/配置不存在"这种正常的空）→ 更新缓存
            self._cfg_cache = overrides
            self._cfg_cache_ts = now
            return overrides
        except Exception:  # 读失败：保留上次成功配置，绝不失效开放
            logger.exception("读取运行时 AI 配置失败，沿用上次成功配置")
            self._cfg_cache_ts = now  # 20s 退避，避免每条消息都猛打故障中的服务器
            return self._cfg_cache

    def _apply_runtime_config(self) -> None:
        """把控制室下发的配置应用到 llm/agent/toolbox（按需热重建，幂等）。

        管理后台可下发 provider / model / 人设 / 工具开关。任一缺省时用启动配置兜底。
        **api_key 永远不从网页/控制室来**：密钥只走服务端环境变量/Secret Manager
        （build_provider 传 api_key="" 即让各 SDK 自己读环境变量）。
        """
        ov = self._read_overrides()
        provider = ov.get("provider") or self.config.llm_provider
        model = ov.get("model") or self.config.llm_model
        system_prompt = ov.get("system_prompt") or self.config.system_prompt
        sig = (provider, model, system_prompt, "")
        if sig != self._applied_sig:
            try:
                # api_key="" → 各 provider SDK 从环境变量读密钥（绝不接受网页传入的 key）
                self.llm = build_provider(
                    provider, api_key="", model=model, system_prompt=system_prompt
                )
                self.agent = Agent(
                    llm=self.llm, toolbox=self.toolbox, system_prompt=system_prompt
                )
                self._applied_sig = sig
                self._model_agents.clear()  # provider/人设变了，按群模型缓存作废
                logger.info(
                    "已应用运行时 AI 配置: provider=%s model=%s 人设已更新",
                    provider, model or "默认",
                )
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
            技能 列表/添加/删除/停用/启用  → 管理本群（或私聊=个人）的技能
        （也兼容 /专班、/技能，万一用户在 Element 里点了"作为消息发送"）
        """
        text = text.strip()
        for prefix in ("建专班", "/专班", "专班"):
            if text.startswith(prefix):
                # 建群/开专班门控：低于门槛者拦下并提示升级（仍算"命中命令"，return True）
                if not self._gate_allows(sender, "create_room"):
                    self.client.send_text(room_id, self._gate_denied_text("create_room"))
                    return True
                name = text[len(prefix):].strip(" :：") or "新专班"
                self._launch_campaign(room_id, sender, name)
                return True
        # 技能管理命令：先用不连 DB 的前缀闸判断，命中再执行（DB 不可用则提示未启用）
        if self._is_skill_command(text):
            self.client.send_text(room_id, self._run_skill_command(room_id, sender, text))
            return True
        # 知识库管理命令（同套路）
        if self._is_kb_command(text):
            self.client.send_text(room_id, self._run_kb_command(room_id, sender, text))
            return True
        # 工作流连接器命令（列表/跑外部 n8n/Make 等）
        if self._is_wf_command(text):
            self.client.send_text(room_id, self._run_wf_command(room_id, sender, text))
            return True
        # 会员等级命令（自查 / 管理员设置）
        if self._is_member_command(text):
            self.client.send_text(room_id, self._run_member_command(sender, text))
            return True
        return False

    # —— 会员等级（账号权限分层）命令 ——

    def _is_member_command(self, text: str) -> bool:
        """是不是「会员」命令——纯字符串判断。"""
        t = text.strip()
        low = t.lower()
        return (
            t.startswith("会员")
            or t.startswith("我的会员")
            or t.startswith("/会员")
            or low == "member"
            or low.startswith("member ")
            or low.startswith("/member")
        )

    # 中文等级词 → slug（命令里允许用中文或直接用 slug）
    _TIER_ALIASES = {
        "免费": "free", "免费会员": "free",
        "付费": "paid", "付费会员": "paid",
        "创作者": "creator", "创作者会员": "creator", "创作": "creator",
    }

    def _resolve_tier_word(self, word: str) -> Optional[str]:
        """把命令里的等级词（中文别名或 slug）解析成合法 slug；无法识别返回 None。"""
        w = (word or "").strip()
        if is_valid_tier(w):
            return w
        return self._TIER_ALIASES.get(w)

    def _run_member_command(self, sender: str, text: str) -> str:
        """执行会员命令。

        任何人可查自己：``会员`` / ``我的会员``。
        平台管理员（控制室 power≥50）可管理（同工作流的授权口径——会员等级是付费门槛，
        不能让普通人自封）：
          ``会员 列表``            —— 列出所有非免费会员
          ``会员 设置 @user 付费``  —— 设/调某人等级（免费=撤销）
          ``会员 撤销 @user``       —— 回落到免费
        全程兜异常，绝不抛。
        """
        # 去前缀，留下参数体
        body = text.strip()
        for p in ("我的会员", "会员", "/会员", "/member", "member"):
            if body.lower().startswith(p.lower()):
                body = body[len(p):]
                break
        body = body.strip()

        # 无参 / 帮助：当作"查自己"（最常用），并附管理员用法提示
        if not body or body in ("帮助", "help", "?", "？"):
            mine = tier_label(self.members.get_tier(sender))
            tip = ""
            if self._is_platform_admin(sender):
                tip = (
                    "\n（管理员可用：会员 列表 / 会员 设置 @用户 付费 / 会员 撤销 @用户）"
                )
            return f"👤 你当前是「{mine}」。{tip}"

        # —— 以下是管理命令：先验平台管理员 ——
        if not self._is_platform_admin(sender):
            return "只有平台管理员能管理会员等级。你可以发「会员」查看自己的等级。"

        if body.startswith(("列表", "list", "ls")):
            mp = self.members.get_all()
            if not mp:
                return "目前没有付费/创作者会员（所有人默认免费会员）。"
            lines = [f"👥 非免费会员（{len(mp)} 人）："]
            for uid, rec in mp.items():
                src = rec.get("source") or "admin"
                lines.append(f"  · {uid} —— {tier_label(rec.get('tier'))}（来源:{src}）")
            return "\n".join(lines)

        if body.startswith(("设置", "set", "授予")):
            parts = body.split()
            # 形如：设置 @user 付费 —— parts[0]=动词, parts[1]=@user, parts[2]=等级
            if len(parts) < 3:
                return "用法：会员 设置 @用户 <免费|付费|创作者>"
            target, tier_word = parts[1], parts[2]
            tier = self._resolve_tier_word(tier_word)
            if not tier:
                tiers = "/".join(t["label"] for t in MEMBER_TIERS)
                return f"未知等级「{tier_word}」。可选：{tiers}（或 slug）。"
            if self.members.grant(target, tier, source="admin"):
                return f"✅ 已把 {target} 设为「{tier_label(tier)}」。"
            return "⚠️ 设置失败（控制室不存在或写入失败），请稍后再试。"

        if body.startswith(("撤销", "revoke", "取消")):
            parts = body.split()
            if len(parts) < 2:
                return "用法：会员 撤销 @用户"
            target = parts[1]
            if self.members.revoke(target):
                return f"✅ 已把 {target} 撤销为「免费会员」。"
            return "⚠️ 撤销失败（控制室不存在或写入失败），请稍后再试。"

        return "没听懂。发「会员」查看自己的等级；管理员发「会员 帮助」看用法。"

    def grant_member_tier(
        self, user_id: str, tier: str, source: str = "purchase"
    ) -> bool:
        """【预留接口】授予会员等级——给未来模块4（交易系统）支付成功后调用。

        本期不接真实支付：把数据模型(控制室 cosmac.members)和这个服务端入口先立起来，
        模块4 在支付回调里调本方法把用户提到对应等级即可。source 默认 'purchase' 以便审计
        区分「买来的」与「管理员手动给的」。成功返回 True。
        """
        return self.members.grant(user_id, tier, source=source)

    def _is_wf_command(self, text: str) -> bool:
        """是不是「工作流」命令——纯字符串判断。"""
        t = text.strip()
        low = t.lower()
        return (
            t.startswith("工作流")
            or t.startswith("/工作流")
            or low == "wf"
            or low.startswith("wf ")
            or low.startswith("/wf")
        )

    def _workflow_defs(self) -> List[Dict[str, Any]]:
        """读控制室「工作流连接器」定义（启用的）。失败返回空。"""
        try:
            ctrl = self.client.resolve_alias(self.config.control_room_alias)
            if not ctrl:
                return []
            ev = self.client.get_state_event(ctrl, WORKFLOWS_EVENT_TYPE) or {}
            return [
                w for w in (ev.get("workflows") or [])
                if isinstance(w, dict) and w.get("slug") and w.get("enabled", True)
            ]
        except Exception as e:
            logger.debug("读取工作流连接器失败（忽略）：%s", e)
            return []

    def _run_wf_command(self, room_id: str, sender: str, text: str) -> str:
        """执行工作流命令：`工作流 列表` / `工作流 跑 <slug> <输入>`。

        连接器定义读控制室 state event；运行同步调外部 webhook；结果尽力落库(DB 可用时)。
        全程兜异常，绝不抛。
        """
        # 去前缀
        body = text.strip()
        for p in ("工作流", "/工作流", "/wf", "wf"):
            if body.lower().startswith(p.lower()):
                body = body[len(p):]
                break
        body = body.strip()
        defs = self._workflow_defs()

        if not body or body in ("帮助", "help", "?", "？"):
            return (
                "🔗 工作流命令：\n"
                "  工作流 列表\n"
                "  工作流 跑 <编号> <输入>\n"
                "（连接器在「管理后台 → 工作流」配置，对接 n8n/Make 等）"
            )
        if body.startswith(("列表", "list", "ls")):
            if not defs:
                return "还没有可用的工作流连接器。请在「管理后台 → 工作流」添加。"
            lines = [f"🔗 可用工作流（{len(defs)} 个）："]
            for w in defs:
                hint = f" —— {w.get('input_hint')}" if w.get("input_hint") else ""
                lines.append(f"  · {w.get('slug')}（{w.get('name') or w.get('slug')}）{hint}")
            return "\n".join(lines)
        if body.startswith(("跑", "run", "执行")):
            # #1/#2 越权防护：跑工作流触发付费生成/外部写、用的是**服务端共享凭据**。
            # 授权走「workflow_run」门控（后台可配；默认「仅平台管理员」＝维持原行为，
            # 管理员可下调到付费/创作者）。不分 DM/群（否则任何人和 bot 开个两人 DM 就能跑）。
            # 普通成员只能「工作流 列表」查看。
            if not self._gate_allows(sender, "workflow_run"):
                return self._gate_denied_text("workflow_run") + " 你可以用「工作流 列表」查看可用工作流。"
            rest = body.split(maxsplit=1)
            arg = rest[1].strip() if len(rest) > 1 else ""
            parts = arg.split(maxsplit=1)
            slug = parts[0] if parts else ""
            user_input = parts[1].strip() if len(parts) > 1 else ""
            if not slug:
                return "用法：工作流 跑 <编号> <输入>（编号见「工作流 列表」）"
            conn = next((w for w in defs if w.get("slug") == slug), None)
            if conn is None:
                return f"没找到工作流「{slug}」。用「工作流 列表」看可用的。"
            name = conn.get("name") or slug
            # 异步连接器（长任务）：登记 pending + 回调 URL，提交后即返回，等平台回调。
            # #3：只有 webhook 家族支持回调；dify/coze/comfyui 即便误存了 async=true 也走后台同步。
            from cosmac.wf import supports_async_callback
            if (conn.get("async") and self.config.public_url
                    and supports_async_callback(conn.get("platform"))):
                return self._dispatch_async(conn, user_input, room_id, sender, name)
            # #4/#5：**所有同步连接器**都放有界后台池跑、立即返回——webhook/dify/coze 也可能
            # 等到 30s、ComfyUI 更到 120s，同步执行会卡住 appservice 事务响应（Synapse 超时重试）。
            # 后台跑完把结果发回本群。池满则提示繁忙。
            if self._run_wf_in_background(conn, user_input, room_id, sender, name):
                return f"⏳ 工作流「{name}」已开始，完成后结果会自动发到本群。"
            return "⚠️ 任务太多、系统繁忙，请稍后再试。"
        return f"没听懂「{body}」。发「工作流 帮助」看用法。"

    def _run_wf_in_background(self, conn, user_input, room_id, sender, name) -> bool:
        """把同步连接器放**有界**后台线程池跑，避免阻塞 appservice 事务（#4/#5）。

        ComfyUI 成功时已自行把图发回房间（不再补文字）；其它平台返回文本→后台发回群。
        失败/异常补一条文字。运行记录尽力落库。池满（在跑+排队超上限）返回 False。
        """
        from cosmac.wf import run_connector, submit_background

        def work() -> None:
            try:
                result = run_connector(
                    conn, user_input, client=self.client, room_id=room_id
                )
                self._record_wf_run(room_id, sender, conn, user_input, result)
                if not result.get("ok"):
                    self.client.send_text(
                        room_id, f"⚠️ 工作流「{name}」执行失败：{result.get('error')}"
                    )
                elif conn.get("platform") != "comfyui":
                    out = result.get("output") or "（无返回内容）"
                    self.client.send_text(room_id, f"✅ 工作流「{name}」已完成：\n{out}")
            except Exception:
                logger.exception("后台工作流执行出错：%s", name)

        # ComfyUI 走慢池，避免长生成把快连接器/提交堵在队尾（#5）
        pool = "slow" if conn.get("platform") == "comfyui" else "fast"
        return submit_background(work, pool=pool)

    def _dispatch_async(self, conn, user_input, room_id, sender, name) -> str:
        """异步连接器：建 pending 运行(带一次性 token)+ 回调 URL，提交给平台后即返回。

        平台跑完反向 POST 到 {public_url}/cosmac/wf/callback/<run_id>（URL **不含 token**）。
        token 放进我们发给平台的 payload(callback_token)，平台回传 X-Cosmac-Token 头来鉴权，
        token 从此不进任何 URL/日志。DB 只存哈希、单次用完即废。DB 不可用则退回同步说明。
        """
        import secrets

        from cosmac.wf import run_connector, submit_background

        try:
            from cosmac.db import session_scope
            from cosmac.db.wf_repo import complete_run, create_pending

            token = secrets.token_urlsafe(16)
            with session_scope() as s:
                run = create_pending(
                    s, slug=conn.get("slug", ""), platform=conn.get("platform", "webhook"),
                    room_id=room_id, sender=sender, user_input=user_input,
                    token=_token_hash(token),  # #4：DB 只存 token 哈希，不存明文
                )
                run_id = run.id
            # #2：回调 URL **不含 token**（路径也会进 nginx 日志）。token 放进我们 POST 给
            # 平台的 payload(callback_token)，平台据此回传 X-Cosmac-Token 头来鉴权——token
            # 从此不进任何 URL/日志。DB 只存哈希、单次用完即废。
            cb = f"{self.config.public_url.rstrip('/')}/cosmac/wf/callback/{run_id}"

            # #3：**提交也放后台**——webhook 提交本身可能等到 30s，同步会卡住 appservice 事务。
            # 提交成功就等平台回调；提交失败则结清 pending + 通知群。
            def _submit() -> None:
                err = ""
                try:
                    r = run_connector(
                        conn, user_input, callback_url=cb, callback_token=token
                    )
                    if not r.get("ok"):
                        err = r.get("error") or "提交失败"
                except Exception as exc:
                    # #4：提交抛异常也要结清 pending + 通知，否则平台没收到任务、用户却看到"已提交"，
                    # 这条 run 永久卡 pending。
                    logger.exception("异步工作流提交出错：%s", name)
                    err = f"提交异常：{exc}"
                if err:
                    with session_scope() as s2:
                        complete_run(s2, run_id, error=err)
                    self.client.send_text(
                        room_id, f"⚠️ 工作流「{name}」提交失败：{err}"
                    )

            # #5：异步"提交"走独立 submit 池——绝不被长任务(ComfyUI/同步连接器)堵在队尾，
            # 否则用户已收到"已提交"、提交动作却还排队迟迟发不出去。
            if submit_background(_submit, pool="submit"):
                return f"⏳ 工作流「{name}」已提交（#{run_id}），完成后结果会自动发到本群。"
            # 池满 → 结清这条 pending，提示繁忙
            with session_scope() as s:
                complete_run(s, run_id, error="系统繁忙")
            return "⚠️ 任务太多、系统繁忙，请稍后再试。"
        except Exception as e:
            logger.warning("异步工作流提交失败：%s", e)
            return f"⚠️ 工作流「{name}」提交失败（异步未就绪）。"

    def handle_wf_callback(self, run_id: int, token: str, body: Dict[str, Any]) -> int:
        """处理外部平台的异步回调：校验 token→把结果发回原群→结清运行。返回 HTTP 状态码。

        body 约定：{"output": "..."} 成功 / {"error": "..."} 失败。
        返回 200(成功) / 403(token 不符) / 404(无此 pending 运行) / 500(内部错)。
        """
        try:
            import hmac

            from cosmac.db import session_scope
            from cosmac.db.wf_repo import (
                claim_pending, complete_run, get_run, revert_to_pending,
            )

            with session_scope() as s:
                run = get_run(s, run_id)
                if run is None:
                    return 404
                if run.status in ("ok", "error"):
                    return 200  # 已处理完 → 幂等返回，不重复发/不再结算
                # pending / processing 才往下走（processing 可能是上次半途崩的，靠 claim 判定）
                # #4：比对 token 的哈希（DB 存的是哈希），用 compare_digest 防时序侧信道
                if not token or not hmac.compare_digest(
                    _token_hash(token), run.token or ""
                ):
                    return 403
                room_id = run.room_id
                slug = run.slug
                # #2/#3：原子抢占成 processing。并发回调只有一个抢到；卡死(超时)的可被重抢。
                # 抢不到 = 别的回调正在处理 → 幂等返回 200，绝不重复发/重复结算。
                if not claim_pending(s, run_id):
                    return 200
            # #5：消息正文按字节截断——回调体可达 512KB，整条塞进 Matrix 事件会超事件大小上限
            # 导致 send 持续失败、run 反复回到 pending 无限重试。完整结果在 DB 的 run 记录里。
            output = str(body.get("output") or "")[:_MAX_WF_MSG]
            error = str(body.get("error") or "")[:_MAX_WF_MSG]
            # #6：**先发消息、确认发出去了再结清**。发失败（返回假值或抛异常）就回滚到 pending、
            # 回 500 让平台重试，不会丢结果。
            # #4：用**固定 txn id**(随 run_id)，崩溃恢复后重发同一条会被 Synapse 去重，群里不重复。
            text = (
                f"⚠️ 工作流「{slug}」(#{run_id}) 失败：{error}" if error
                else f"✅ 工作流「{slug}」(#{run_id}) 完成：\n{output or '（无内容）'}"
            )
            try:
                sent = self.client.send_text(room_id, text, txn_id=f"cosmac-wf-{run_id}")
            except Exception:
                logger.exception("工作流回调发消息抛异常 run_id=%s", run_id)
                sent = None
            if not sent:
                logger.warning("工作流回调发消息失败 run_id=%s，回滚 pending 待重试", run_id)
                with session_scope() as s:
                    revert_to_pending(s, run_id)
                return 500
            with session_scope() as s:
                complete_run(s, run_id, output=output, error=error)
            return 200
        except Exception:
            logger.exception("处理工作流回调出错 run_id=%s", run_id)
            return 500

    def _record_wf_run(self, room_id, sender, conn, user_input, result) -> None:
        """尽力把运行记录落库；DB 不可用就跳过（不影响已拿到的结果）。"""
        try:
            from cosmac.db import session_scope
            from cosmac.db.wf_repo import record_run

            with session_scope() as s:
                record_run(
                    s, slug=conn.get("slug", ""), platform=conn.get("platform", "webhook"),
                    room_id=room_id, sender=sender, user_input=user_input, result=result,
                )
        except Exception as e:
            logger.debug("工作流运行记录入库失败（忽略）：%s", e)

    def _is_kb_command(self, text: str) -> bool:
        """是不是「知识」命令——纯字符串判断，不导入 cosmac.db。"""
        t = text.strip()
        low = t.lower()
        return (
            t.startswith("知识")
            or t.startswith("/知识")
            or low == "kb"
            or low.startswith("kb ")
            or low.startswith("/kb")
        )

    def _run_kb_command(self, room_id: str, sender: str, text: str) -> str:
        """执行知识库命令并返回回复文本（私聊→个人库，群→本群库；写操作群里需管理员）。"""
        # 知识库门控：低于门槛者整条知识命令都不放行
        if not self._gate_allows(sender, "knowledge"):
            return self._gate_denied_text("knowledge")
        try:
            is_dm = self.client.joined_member_count(room_id) <= 2
        except Exception:
            is_dm = False
        can_write = True if is_dm else self._is_room_admin(room_id, sender)
        try:
            from cosmac.db import session_scope
            from cosmac.db.kb_cmd import handle_kb_command

            with session_scope() as s:
                return handle_kb_command(
                    s,
                    is_dm=is_dm,
                    room_id=room_id,
                    user_id=sender,
                    text=text,
                    can_write=can_write,
                )
        except Exception as e:
            logger.warning("知识库命令执行失败：%s", e)
            return "知识库功能暂不可用（服务器可能还没配置数据库）。"

    def _is_skill_command(self, text: str) -> bool:
        """是不是「技能」命令——纯字符串判断，不导入 cosmac.db（避免无谓依赖加载）。"""
        t = text.strip()
        low = t.lower()
        return (
            t.startswith("技能")
            or t.startswith("/技能")
            or low == "skill"
            or low.startswith("skill ")
            or low.startswith("/skill")
        )

    def _run_skill_command(self, room_id: str, sender: str, text: str) -> str:
        """执行技能命令并返回回复文本。作用域：私聊→个人技能，群里→本群技能。

        和 _skill_addendum 一样：cosmac.db 懒导入 + 全程兜异常——服务器没装
        SQLAlchemy / 没配 DB 时，回一句"未启用"而不是让 bot 崩或不吭声。
        """
        try:
            is_dm = self.client.joined_member_count(room_id) <= 2
        except Exception:
            is_dm = False
        # #1 群级技能写操作要求发送者是房间管理员（个人技能/私聊不限）。
        can_write = True if is_dm else self._is_room_admin(room_id, sender)
        try:
            from cosmac.db import session_scope
            from cosmac.db.skill_cmd import handle_skill_command

            with session_scope() as s:
                return handle_skill_command(
                    s,
                    is_dm=is_dm,
                    room_id=room_id,
                    user_id=sender,
                    text=text,
                    can_write=can_write,
                )
        except Exception as e:
            logger.warning("技能命令执行失败：%s", e)
            return "技能功能暂不可用（服务器可能还没配置数据库）。"

    def _is_room_admin(self, room_id: str, user_id: str) -> bool:
        """发送者在该房间是否为管理员（power≥50）。读不到权限 → 保守视为否（写被挡）。

        用于群级技能的写权限判断：群级技能会注入所有群成员的 AI 请求，普通成员不能改。
        """
        try:
            pl = self.client.get_state_event(room_id, "m.room.power_levels", "") or {}
            users = pl.get("users") or {}
            default = pl.get("users_default", 0)
            level = users.get(user_id, default)
            return isinstance(level, int) and level >= 50
        except Exception:
            return False

    def _is_platform_admin(self, user_id: str) -> bool:
        """是否**平台管理员** = 在控制室里 power≥50。用于工作流这类"用服务端共享凭据、
        触发付费/外部操作"的授权——不分 DM/群，堵住"和 bot 开个 DM 就能跑"的绕过。
        非控制室成员/读不到一律视为否（保守拒绝）。
        """
        try:
            ctrl = self.client.resolve_alias(self.config.control_room_alias)
            if not ctrl:
                return False
            pl = self.client.get_state_event(ctrl, "m.room.power_levels", "") or {}
            users = pl.get("users") or {}
            level = users.get(user_id, pl.get("users_default", 0))
            return isinstance(level, int) and level >= 50
        except Exception:
            return False

    # —— 功能门控：按后台配置的「能力→最低等级」服务端强制 ——

    def _gate_allows(self, sender: str, capability: str) -> bool:
        """sender 是否被允许使用 capability（读控制室 cosmac.gating 配置裁决）。

        规则（见 cosmac.members 门控阶梯）：
          - 门槛 = admin → 仅平台管理员；
          - 门槛 = tier(free/paid/creator) → **平台管理员永远放行**；否则按会员等级比较。
        读不到配置 → GatingStore 回落默认（多为 free，不限制），不失效锁死。
        """
        req = self.gating.required(capability)
        if req == GATE_ADMIN:
            return self._is_platform_admin(sender)
        # tier 门槛：staff（平台管理员）一律放行，免得给自己开会员
        if self._is_platform_admin(sender):
            return True
        return gate_rank(self.members.get_tier(sender)) >= gate_rank(req)

    def _gate_denied_text(self, capability: str) -> str:
        """被门控拦下时给用户的友好提示（点名所需等级，引导查/升级会员）。"""
        label = gate_capability_label(capability)
        req = self.gating.required(capability)
        if req == GATE_ADMIN:
            return f"「{label}」仅平台管理员可用。"
        return (
            f"「{label}」需要{tier_label(req)}及以上。"
            "发「会员」查看你的等级，或联系管理员升级。"
        )

    # 工具名 → 门控能力 key（只有这些工具受会员门控；其余由入口的 ai_chat 门控覆盖）
    _TOOL_GATE_MAP = {
        "create_room": "create_room",
        "run_workflow": "workflow_run",
    }

    def _tool_gate_check(self, sender: str, tool_name: str) -> Optional[str]:
        """工具门控钩子（注入 Toolbox.gate_check）：放行返回 None，拦下返回拒绝文案。"""
        cap = self._TOOL_GATE_MAP.get(tool_name)
        if not cap:
            return None  # 该工具不单独门控
        if self._gate_allows(sender, cap):
            return None
        return self._gate_denied_text(cap)

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


class _DeadlineSocket:
    """给 socket 包一层「整次请求的绝对时限」（#1 真正防住 Slowloris）。

    单纯设 socket timeout 只约束"单次 recv"——攻击者每隔 19s 挤一个字节就能不断重置
    20s 计时器，把请求行/请求头/正文的读取无限拖住，占死一个线程。

    这里把时限**下沉到每次 recv**：每次读前，把 socket 超时设成"距整次请求 deadline 的
    剩余时间"。剩余时间随墙钟单调缩到 0、与对端是否还在发字节无关——所以无论慢速 drip
    怎么发，整次请求都无法越过 deadline。一旦越过就抛 socket.timeout，由上层(请求行/头读取
    或 _read_body)收口：要么优雅关连接、要么回 408。

    因 BaseHTTPRequestHandler 读请求行/头/正文最终都经 SocketIO.readinto → 本对象的
    recv_into，故装一处即覆盖整次请求（默认 HTTP/1.0 一连接一请求，deadline 即请求级）。
    """

    def __init__(self, sock: Any, total_secs: float) -> None:
        self._sock = sock
        self._deadline = time.monotonic() + total_secs

    def recv_into(self, buf: Any, *args: Any) -> int:
        left = self._deadline - time.monotonic()
        if left <= 0:
            raise socket.timeout("request deadline exceeded")  # 上层按超时处理
        self._sock.settimeout(left)
        return self._sock.recv_into(buf, *args)

    def __getattr__(self, name: str) -> Any:
        # close/fileno/send/settimeout/... 一律透传给真实 socket
        return getattr(self._sock, name)


class _Handler(BaseHTTPRequestHandler):
    """HTTP 请求处理器：实现 Matrix Application Service 协议的服务端。

    Synapse 会向我们发起：
      - PUT  .../transactions/{txnId} —— 推送一批事件（核心）。
      - GET  .../users/{userId}       —— 查询某用户是否归我们管。
    """

    # 由工厂注入的对象
    bot: CosmacBot
    hs_token: str

    # #1 防 Slowloris：整次请求的绝对时限（秒）。慢/停的客户端最多占住线程这么久。
    # 真正的强制在 setup() 装的 _DeadlineSocket（把时限下沉到每次 recv），单纯 socket
    # timeout 会被每隔几秒挤一字节的 drip 不断重置、约束不住。
    timeout = 20

    def setup(self) -> None:
        """在标准 setup 之后，把读端 socket 包成 _DeadlineSocket，给整次请求装上绝对时限。

        这样请求行/请求头/正文(都经 SocketIO.readinto → recv_into)都受同一个 deadline 约束，
        慢速 drip 无法分别在"读头"或"读体"阶段把线程拖死。失败则降级为普通 socket timeout。
        """
        super().setup()
        try:
            raw = getattr(self.rfile, "raw", None)  # BufferedReader → SocketIO
            if raw is not None and hasattr(raw, "_sock"):
                raw._sock = _DeadlineSocket(raw._sock, self.timeout)
        except Exception:  # 包装失败不致命：退回 setup() 已设的 socket timeout
            logger.debug("装配请求绝对时限失败（降级为 socket timeout）", exc_info=True)

    # 关掉默认那行嘈杂的访问日志，改用我们自己的 logger
    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: N802
        logger.debug("HTTP " + fmt, *args)

    def _read_body(self, length: int) -> Optional[bytes]:
        """读 length 字节的请求体；靠 setup() 装的 _DeadlineSocket 兜底防 Slowloris。

        _DeadlineSocket 把整次请求的绝对时限下沉到每次 recv：哪怕攻击者每隔几秒挤一个字节，
        读取也无法越过 deadline——越过即抛 socket.timeout，这里 ``except OSError`` 收成 None，
        调用方回 408，不会无限阻塞线程。length 已被调用方按上限校验，单次读入内存可控。
        """
        out = bytearray()
        remaining = length
        while remaining > 0:
            try:
                chunk = self.rfile.read(min(remaining, 65536))
            except OSError:  # socket.timeout（含 _DeadlineSocket 触发的）等
                return None
            if not chunk:
                break
            out += chunk
            remaining -= len(chunk)
        return bytes(out)

    def _check_auth(self) -> bool:
        """校验请求确实来自我们的 Synapse（比对 hs_token）。

        Synapse 会通过 Authorization: Bearer <hs_token> 头，或老式的
        ?access_token= 查询参数携带 token，两种都兼容一下。
        """
        # 用 compare_digest 做常数时间比较，避免 hs_token 被时序侧信道逐字节猜出来
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return hmac.compare_digest(auth[len("Bearer "):], self.hs_token)
        # 兼容老式查询参数
        if "access_token=" in self.path:
            token = self.path.split("access_token=", 1)[1].split("&", 1)[0]
            return hmac.compare_digest(token, self.hs_token)
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

        # 读取请求体（里面是事件数组）。同回调端点一样按 Content-Length 限大小、拒负数/非法值，
        # 防把超大请求整个读进内存（纵深防御；事务批量事件给 8MB 余量）。
        try:
            length = int(self.headers.get("Content-Length", 0))
        except (TypeError, ValueError):
            self._send_json(400, {"errcode": "M_NOT_JSON"})
            return
        if length < 0 or length > _MAX_TXN_BODY:
            self._send_json(413, {"errcode": "M_TOO_LARGE"})
            return
        raw = self._read_body(length) if length else b"{}"  # #1 防 Slowloris
        if raw is None:
            self._send_json(408, {"errcode": "M_REQUEST_TIMEOUT"})
            return
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            self._send_json(400, {"errcode": "M_NOT_JSON"})
            return

        events = data.get("events", [])
        # 已处理/重复 → True 回 200；正被处理中(未过期) → False 回 503 让 Synapse 稍后重试
        # （#3：宁可让上游重试，也不在崩溃窗口里把一整批事务永久跳过/丢失）。
        if self.bot.handle_transaction(txn_id, events):
            self._send_json(200, {})
        else:
            self._send_json(503, {"errcode": "M_UNAVAILABLE"})

    def do_GET(self) -> None:  # noqa: N802
        # Synapse 查询"这个用户/别名是否归你管"，回 200 表示存在
        if "/users/" in self.path or "/rooms/" in self.path:
            if not self._check_auth():
                self._send_json(403, {"errcode": "M_FORBIDDEN"})
                return
            self._send_json(200, {})
            return
        self._send_json(404, {"errcode": "M_UNRECOGNIZED"})

    def do_POST(self) -> None:  # noqa: N802
        # 外部工作流平台的异步回调：/cosmac/wf/callback/<run_id>?token=...
        # **不**用 hs_token 鉴权（这是外部平台调的，不是 Synapse）；用每次运行的一次性 token。
        if "/cosmac/wf/callback/" not in self.path:
            self._send_json(404, {"errcode": "M_UNRECOGNIZED"})
            return
        # 路径形如 /cosmac/wf/callback/<run_id>[/<token>][?token=...]
        try:
            tail = self.path.split("/cosmac/wf/callback/", 1)[1].split("?", 1)[0]
            parts = tail.split("/")
            run_id = int(parts[0])
        except (ValueError, IndexError):
            self._send_json(400, {"error": "bad run id"})
            return
        # #4：token 优先请求头（不进 URL/日志）；其次 URL 路径段；最后兼容老 ?token=。
        token = (self.headers.get("X-Cosmac-Token") or "").strip()
        if not token and len(parts) > 1 and parts[1]:
            token = parts[1]
        if not token and "token=" in self.path:
            token = self.path.split("token=", 1)[1].split("&", 1)[0]
        # #3 防 DoS：验证前就按 Content-Length 限制请求体大小，绝不把超大请求整个读进内存。
        # **负数/非法值要拒**：Content-Length:-1 不会 >上限、read(-1) 会读到 EOF（无界）；
        # 非整数会让 int() 抛 ValueError。故要求 0 ≤ length ≤ 上限，否则直接拒、不读 body。
        try:
            length = int(self.headers.get("Content-Length", 0))
        except (TypeError, ValueError):
            self._send_json(400, {"error": "bad content-length"})
            return
        if length < 0 or length > _MAX_CALLBACK_BODY:
            self._send_json(413, {"error": "bad body length"})
            return
        # #1：按总时限分块读，防 Slowloris 慢速占住线程
        raw = self._read_body(length) if length else b"{}"
        if raw is None:
            self._send_json(408, {"error": "request timeout"})
            return
        # #4：JSON 非法 → 回 400 且**不动 pending**。绝不能把解析失败当成"无内容的成功"——
        # 那样会发"（无内容）"并结清运行，平台收到 200 后再也无法重投正确结果。
        try:
            body = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            self._send_json(400, {"error": "invalid json"})
            return
        if not isinstance(body, dict):
            self._send_json(400, {"error": "expected json object"})
            return
        code = self.bot.handle_wf_callback(run_id, token, body)
        self._send_json(code, {} if code == 200 else {"error": code})


class _BoundedThreadingHTTPServer(ThreadingHTTPServer):
    """带**并发连接上限**的 ThreadingHTTPServer（#3 防连接洪泛耗尽线程）。

    ThreadingHTTPServer 每个连接开一个线程；单纯靠每请求 20s 时限，攻击者只要持续高频
    建连，仍能在窗口内堆出大量线程。这里用 BoundedSemaphore 卡住"同时在处理的连接数"：
    超限的新连接**直接关闭、不开线程**，从源头封住线程膨胀。
    （仍建议在 nginx 加 limit_conn 做网关层兜底；这里是应用层的最后一道。）
    """

    _max_conns = 128  # 同时在处理的连接上限（appservice 正常并发远低于此）

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._conn_sem = threading.BoundedSemaphore(self._max_conns)

    def process_request(self, request: Any, client_address: Any) -> None:
        # 抢不到名额 = 并发已满：直接关连接、不开线程（防线程耗尽）
        if not self._conn_sem.acquire(blocking=False):
            logger.warning("并发连接达上限 %d，拒绝新连接（防线程耗尽）", self._max_conns)
            self.shutdown_request(request)
            return
        super().process_request(request, client_address)

    def process_request_thread(self, request: Any, client_address: Any) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._conn_sem.release()  # 处理完归还名额


def run(config: CosmacConfig) -> None:
    """启动主 AI Bot 的 HTTP 服务，开始监听 Synapse 推来的事件。"""
    bot = CosmacBot(config)
    # 启动时把主 AI 的群内显示名设为品牌名（用户看到的是它，而非 @guduu 用户 id）
    bot.client.set_displayname(config.bot_displayname)
    # #2：清理上次进程遗留的未完成工作流运行（in-flight 随重启消失），通知用户别干等
    bot.recover_interrupted_runs()

    # 把 bot 和 hs_token 注入到 Handler 类上（http.server 用类、不便传参，用 partial 构造）
    handler_cls = partial(_make_handler, bot=bot, hs_token=config.hs_token)

    server = _BoundedThreadingHTTPServer(
        (config.listen_host, config.listen_port), handler_cls
    )
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
