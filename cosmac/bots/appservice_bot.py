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

import json
import logging
import time
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional, Set, Tuple

from cosmac.ai import build_provider, get_provider
from cosmac.ai.agent import Agent
from cosmac.ai.base import LLMProvider
from cosmac.ai.tools import Toolbox, ToolContext
from cosmac.bots.matrix_client import MatrixClient
from cosmac.config import (
    AGENTS_EVENT_TYPE,
    AI_CONFIG_EVENT_TYPE,
    CHANNEL_CONFIG_EVENT_TYPE,
    CONTROL_ADMINS_EVENT_TYPE,
    SKILLS_EVENT_TYPE,
    CosmacConfig,
)
from cosmac.skills_text import render_skills  # 纯渲染、不依赖 DB

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
        # 当前已生效的 (provider, model, system_prompt, _) 签名；任一项变了才热重建模型/Agent。
        # 第 4 段保留位恒为 ""（key 只走环境变量、绝不进签名，见 _apply_runtime_config）。
        self._applied_sig: Tuple[str, str, str, str] = (
            config.llm_provider, config.llm_model, config.system_prompt, "",
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

            # 2b) 否则交给会"动手"的 Agent：它能边想边调用工具（建群/发消息/查记录），
            #     最后把结论发回群。（echo 后端不支持工具，会自动退化为纯文本回复。）
            # 回复前先按管理后台下发的运行时配置（人设/模型/工具开关）对齐一次。
            self._apply_runtime_config()
            # 按 (本群, 发起人) 算出当前生效的技能说明，作为本轮 system addendum 注入。
            # 任何失败（DB 没装/没数据/出错）都返回空串、绝不阻断回复（见 _skill_addendum）。
            extra_system = self._skill_addendum(room_id, sender)
            reply = self.agent.run(
                text or user_text,
                ToolContext(room_id=room_id, sender=sender),
                extra_system=extra_system,
            )
            self.client.send_text(room_id, reply)

    def _skill_addendum(self, room_id: str, sender: str) -> str:
        """拼出本轮注入主 AI 的技能说明 = 全局技能 + 本群/个人技能，合并渲染一次。

        两个来源、各自兜异常、互不拖累：
          - **全局技能**：控制室的 state event（管理后台写、bot 读），纯 Matrix、不需要 DB。
          - **群级/个人技能**：cosmac DB（聊天命令写），``cosmac.db`` 懒导入；服务器没装
            SQLAlchemy / 读失败时这部分降级为空，全局技能仍照常注入。
        **绝不能因为它出问题就让主 AI 不回话**——任一来源异常都只是少注入、不抛出。
        """
        try:
            # 本群绑定的智能体：贡献「人设文本」+「额外要启用的技能 slug」
            persona, agent_slugs = self._group_persona(room_id)
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
            # 人设在前、技能在后，合成本轮 addendum
            return "\n\n".join(p for p in (persona, skills_text) if p)
        except Exception as e:
            # 兜住**最终组装**：脏数据绝不能让这条消息收不到回复（docstring 的承诺）
            logger.debug("组装技能/人设失败（忽略，按无附加继续）：%s", e)
            return ""

    def _group_persona(self, room_id: str) -> Tuple[str, List[str]]:
        """读本群频道配置，得出「人设文本」和「绑定智能体要启用的技能 slug」。

        优先级：① 绑定了全局智能体(persona.agentSlug) → 用它的人设 + 它绑的技能；
                ② 否则用本群自定义人设(persona.prompt)。都没有 → 空。
        失败一律返回空（绝不阻断回复）。模型覆盖(agent.model)本期先不做。
        """
        try:
            cfg = self.client.get_state_event(room_id, CHANNEL_CONFIG_EVENT_TYPE) or {}
            persona = cfg.get("persona") or {}
            slug = (persona.get("agentSlug") or "").strip()
            if slug:
                agent = self._find_global_agent(slug)
                if agent:
                    name = agent.get("name") or slug
                    sp = (agent.get("system_prompt") or "").strip()
                    text = f"本群已绑定智能体「{name}」，请始终以下述人设与职责回应：\n{sp}"
                    slugs = [str(s) for s in (agent.get("skill_slugs") or [])]
                    return text, slugs
            # 退回自定义人设（自由文本）
            free = (persona.get("prompt") or "").strip()
            if free:
                return f"本群人设：\n{free}", []
            return "", []
        except Exception as e:
            logger.debug("读取本群人设失败（忽略）：%s", e)
            return "", []

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
                name = text[len(prefix):].strip(" :：") or "新专班"
                self._launch_campaign(room_id, sender, name)
                return True
        # 技能管理命令：先用不连 DB 的前缀闸判断，命中再执行（DB 不可用则提示未启用）
        if self._is_skill_command(text):
            self.client.send_text(room_id, self._run_skill_command(room_id, sender, text))
            return True
        return False

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
