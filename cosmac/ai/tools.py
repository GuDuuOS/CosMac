"""主 AI 的工具箱：把"工具"映射到真实的 IM 操作。

这是"让 AI 真正动手"的关键一层：
  - 每个工具 = 一份给模型看的 ``ToolSpec``（说明书）+ 一个真正执行的 Python 函数。
  - 执行函数把调用转发到 ``MatrixClient``（主 AI 的"手"），从而真的建群/发消息/查记录。

设计原则：
  - 工具定义（ToolSpec）是厂商中立的，由各 provider 翻译成自家格式。
  - 工具的"执行"统一返回一段**给模型读的文本结果**（成功与否、关键信息），
    Agent 会把它回灌给模型，让模型据此决定下一步或给用户最终答复。
  - 涉及"当前所在房间 / 发起人是谁"的上下文，通过 ``ToolContext`` 传入，
    不让模型去猜这些它不该知道的内部 id。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Set

from cosmac.ai.base import ToolCall, ToolSpec
from cosmac.bots.matrix_client import MatrixClient
from cosmac.config import WORKFLOWS_EVENT_TYPE

logger = logging.getLogger("cosmac.ai.tools")


@dataclass
class ToolContext:
    """一次工具调用的上下文（模型不该感知的内部信息从这里注入）。

    room_id: 当前对话所在房间（"发到这个群""查本群记录"等默认指向它）。
    sender:  发起人用户 id（建群时默认把他拉进去）。
    """

    room_id: str
    sender: str


class Toolbox:
    """主 AI 可用工具的注册表 + 执行器。

    第一版工具（够验证"AI 真能动手"且实用）：
      - create_room          建一个新群，并把发起人拉进去
      - send_message_to_room  往指定房间发一条消息
      - list_room_members     看某房间都有谁（默认当前房间）
      - get_recent_messages   读某房间最近的聊天记录（默认当前房间）
    """

    def __init__(self, client: MatrixClient, control_room_alias: str = ""):
        self.client = client
        # 控制室别名：run_workflow 工具据此读「工作流连接器」定义（state event）。
        self._control_room_alias = control_room_alias
        # 异步连接器(async=true)的提交回调：由 bot 注入 self._dispatch_async；
        # 签名 (conn, user_input, room_id, sender, name) -> 提交结果文本。None 则回退后台同步跑。
        self.dispatch_async: Optional[Callable[..., str]] = None
        # 功能门控钩子：由 bot 注入。签名 (sender, tool_name) -> 拒绝文案 或 None(放行)。
        # 在 execute() 里、真正跑工具前调用——让"让 AI 帮我建群/跑工作流"也受会员门控约束
        # （与聊天命令同一道闸，防止绕过命令直接走自然语言）。None = 不做门控（如单测）。
        self.gate_check: Optional[Callable[[str, str], Optional[str]]] = None
        # 工具名 → (说明书, 执行函数)。执行函数签名: (arguments, ctx) -> 结果文本
        self._tools: Dict[str, Dict[str, Any]] = {}
        # 启用集合：None = 全部启用（默认）；否则只启用集合内的工具。
        # 管理后台「AI 配置」可下发工具开关，运行时由 bot 调 set_enabled 更新。
        self._enabled: Optional[Set[str]] = None
        self._register_default_tools()

    # —— 工具开关 ——

    def set_enabled(self, names: Optional[Set[str]]) -> None:
        """设置启用的工具集合。传 None = 全部启用（不限制）。

        只对"已注册的工具名"生效；未知名字忽略。这样管理后台即使下发了已废弃的
        工具名也不会出错。
        """
        if names is None:
            self._enabled = None
        else:
            # 只保留确实存在的工具名
            self._enabled = {n for n in names if n in self._tools}

    def _is_enabled(self, name: str) -> bool:
        return self._enabled is None or name in self._enabled

    # —— 对外接口 ——

    def specs(self) -> List[ToolSpec]:
        """返回当前启用工具的说明书（交给模型，让它知道有哪些工具可用）。"""
        return [
            entry["spec"]
            for name, entry in self._tools.items()
            if self._is_enabled(name)
        ]

    def execute(self, call: ToolCall, ctx: ToolContext) -> str:
        """执行一次工具调用，返回给模型读的文本结果（绝不抛异常，出错也转成文本）。"""
        entry = self._tools.get(call.name)
        if entry is None:
            return f"错误：不存在名为 {call.name} 的工具。"
        if not self._is_enabled(call.name):
            return f"工具 {call.name} 已被管理员停用。"
        # 会员门控：跑工具前先过 bot 注入的门控钩子（同聊天命令那道闸，防自然语言绕过）。
        # 返回拒绝文案就把它当作工具结果回灌给模型，让模型据此礼貌告知用户需升级。
        if self.gate_check is not None:
            denial = self.gate_check(ctx.sender, call.name)
            if denial:
                return denial
        try:
            logger.info("执行工具 %s 参数=%s", call.name, call.arguments)
            return entry["fn"](call.arguments, ctx)
        except Exception as exc:  # 工具出错也要回文本，别让 Agent 循环崩掉
            logger.exception("工具 %s 执行异常", call.name)
            return f"工具 {call.name} 执行出错：{exc}"

    # —— 工具注册 ——

    def _register(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        fn: Callable[[Dict[str, Any], ToolContext], str],
    ) -> None:
        self._tools[name] = {
            "spec": ToolSpec(name=name, description=description, parameters=parameters),
            "fn": fn,
        }

    def _register_default_tools(self) -> None:
        # 1) 建群（核心：从"会聊天"到"会动手"的分水岭）
        self._register(
            name="create_room",
            description=(
                "创建一个新的群聊/房间，并自动把当前请求人拉进去。"
                "当用户想要『建群/开个专班/拉个群/新建一个频道』时调用。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "新群的名字，如『爆款专班』。",
                    },
                    "invitees": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "可选。除请求人外还要邀请的用户 id 列表"
                            "（完整格式如 @bob:host）。没有就留空。"
                        ),
                    },
                },
                "required": ["name"],
            },
            fn=self._tool_create_room,
        )

        # 2) 往某房间发消息
        self._register(
            name="send_message_to_room",
            description=(
                "往指定房间发一条文本消息。如果用户没指定房间，就用当前房间。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "要发送的消息正文。"},
                    "room_id": {
                        "type": "string",
                        "description": "目标房间 id；不填则发到当前房间。",
                    },
                },
                "required": ["text"],
            },
            fn=self._tool_send_message,
        )

        # 3) 看某房间成员
        self._register(
            name="list_room_members",
            description="列出某个房间当前的成员；不指定 room_id 则看当前房间。",
            parameters={
                "type": "object",
                "properties": {
                    "room_id": {
                        "type": "string",
                        "description": "房间 id；不填则看当前房间。",
                    }
                },
            },
            fn=self._tool_list_members,
        )

        # 4) 读某房间最近聊天记录
        self._register(
            name="get_recent_messages",
            description=(
                "读取某房间最近的聊天记录，用于了解上下文/做总结。"
                "不指定 room_id 则读当前房间。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "room_id": {
                        "type": "string",
                        "description": "房间 id；不填则读当前房间。",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "读取最近多少条，默认 20。",
                    },
                },
            },
            fn=self._tool_get_messages,
        )

        # 5) 跑外部工作流连接器（n8n/Make 等）
        self._register(
            name="run_workflow",
            description=(
                "运行一个已配置的外部工作流/自动化（对接 n8n、Make 等平台）。"
                "当用户想『跑某个工作流、用 n8n/自动化做某事、触发某流程』时调用。"
                "不确定 slug 就先不带 slug 调用一次，会返回可用工作流列表。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "slug": {
                        "type": "string",
                        "description": "工作流标识(slug)；不确定就留空以获取可用列表。",
                    },
                    "input": {
                        "type": "string",
                        "description": "传给工作流的输入文本/参数（如『科技感蓝色封面』）。",
                    },
                },
            },
            fn=self._tool_run_workflow,
        )

    # —— 各工具的具体执行（转发到 MatrixClient）——

    def _tool_create_room(self, args: Dict[str, Any], ctx: ToolContext) -> str:
        name = (args.get("name") or "新群").strip()
        # 默认把发起人拉进新群，再并上模型额外指定的邀请人（去重）
        invitees = list(dict.fromkeys([ctx.sender, *(args.get("invitees") or [])]))
        room_id = self.client.create_room(name, invitees=invitees)
        if not room_id:
            return f"建群「{name}」失败了（创建房间接口返回错误）。"
        return (
            f"已成功创建群「{name}」（room_id={room_id}），"
            f"并已邀请：{', '.join(invitees)}。"
        )

    def _tool_send_message(self, args: Dict[str, Any], ctx: ToolContext) -> str:
        text = args.get("text") or ""
        if not text.strip():
            return "没有可发送的内容。"
        room_id = args.get("room_id") or ctx.room_id
        event_id = self.client.send_text(room_id, text)
        if not event_id:
            return f"往房间 {room_id} 发消息失败。"
        return f"已往房间 {room_id} 发送消息（event_id={event_id}）。"

    def _tool_list_members(self, args: Dict[str, Any], ctx: ToolContext) -> str:
        room_id = args.get("room_id") or ctx.room_id
        members = self.client.get_members(room_id)
        if not members:
            return f"房间 {room_id} 没查到成员（或查询失败）。"
        lines = [f"- {m['display_name']}（{m['user_id']}）" for m in members]
        return f"房间 {room_id} 共有 {len(members)} 名成员：\n" + "\n".join(lines)

    def _tool_get_messages(self, args: Dict[str, Any], ctx: ToolContext) -> str:
        room_id = args.get("room_id") or ctx.room_id
        limit = int(args.get("limit") or 20)
        msgs = self.client.get_messages(room_id, limit=limit)
        if not msgs:
            return f"房间 {room_id} 没查到聊天记录（或查询失败）。"
        # 用 JSON 回灌，模型读起来结构清晰
        return "最近聊天记录（旧→新）：\n" + json.dumps(msgs, ensure_ascii=False)

    # —— 工作流连接器 ——

    def _workflow_defs(self) -> List[Dict[str, Any]]:
        """读控制室「工作流连接器」定义（启用的）；失败/无配置返回空。"""
        if not self._control_room_alias:
            return []
        try:
            ctrl = self.client.resolve_alias(self._control_room_alias)
            if not ctrl:
                return []
            ev = self.client.get_state_event(ctrl, WORKFLOWS_EVENT_TYPE) or {}
            return [
                w for w in (ev.get("workflows") or [])
                if isinstance(w, dict) and w.get("slug") and w.get("enabled", True)
            ]
        except Exception:
            return []

    def _is_platform_admin(self, sender: str) -> bool:
        """是否平台管理员 = 控制室 power≥50。工作流(共享付费凭据)只许平台管理员触发，
        **不分 DM/群**——否则任何人和 bot 开个两人 DM 就能跑。读不到/非控制室成员→拒。
        """
        if not self._control_room_alias:
            return False
        try:
            ctrl = self.client.resolve_alias(self._control_room_alias)
            if not ctrl:
                return False
            pl = self.client.get_state_event(ctrl, "m.room.power_levels", "") or {}
            users = pl.get("users") or {}
            level = users.get(sender, pl.get("users_default", 0))
            return isinstance(level, int) and level >= 50
        except Exception:
            return False

    def _tool_run_workflow(self, args: Dict[str, Any], ctx: ToolContext) -> str:
        # #1/#2 越权防护：跑工作流触发外部/付费操作、用服务端共享凭据，必须授权。
        # 接了门控钩子时(生产)由 execute() 的 gate_check 统一裁决(走 workflow_run 门槛配置)；
        # 没接门控钩子时(独立/单测)退回硬基线——只许平台管理员，绝不无授权放行。
        if self.gate_check is None and not self._is_platform_admin(ctx.sender):
            return "只有平台管理员能让我跑工作流（它会触发外部/付费操作、用服务端共享凭据）。"
        defs = self._workflow_defs()
        slug = (args.get("slug") or "").strip()
        if not slug:
            if not defs:
                return "当前没有已配置的工作流连接器（去管理后台→工作流添加）。"
            listing = "；".join(
                f"{w.get('slug')}（{w.get('name') or ''}）" for w in defs
            )
            return f"可用工作流：{listing}。请带 slug 再调一次。"
        conn = next((w for w in defs if w.get("slug") == slug), None)
        if conn is None:
            avail = "、".join(w.get("slug", "") for w in defs) or "（空）"
            return f"没找到工作流「{slug}」。可用：{avail}"
        # 延迟导入：HTTP 执行与 DB 记录都不在工具加载期引入
        from cosmac.wf import run_connector, submit_background

        user_input = args.get("input") or ""
        name = conn.get("name") or slug
        platform = conn.get("platform", "webhook")

        # #1/#3：异步连接器(async=true、bot 注入了 dispatch_async、**且平台支持回调**) → 走回调
        # 协议；dify/coze/comfyui 没有回调通道，即便误存 async=true 也按后台同步跑（不挂 pending）。
        from cosmac.wf import supports_async_callback
        if conn.get("async") and self.dispatch_async and supports_async_callback(platform):
            return self.dispatch_async(conn, user_input, ctx.room_id, ctx.sender, name)

        # #1/#4/#5：**其余所有连接器**都放有界后台池跑、立即给 Agent 一个"已开始"让它继续——
        # webhook/dify/coze(≤30s) 也会卡住 Agent + appservice 事务，ComfyUI 更甚(120s)。
        # 跑完把结果发回群（ComfyUI 自己发图，其它平台发文本）。池满则拒。
        def _work() -> None:
            try:
                r = run_connector(
                    conn, user_input, client=self.client, room_id=ctx.room_id
                )
                self._record_workflow_run(slug, platform, ctx, user_input, r)
                if not r.get("ok"):
                    self.client.send_text(
                        ctx.room_id, f"⚠️ 工作流「{name}」执行失败：{r.get('error')}"
                    )
                elif platform != "comfyui":
                    self.client.send_text(
                        ctx.room_id,
                        f"✅ 工作流「{name}」已完成：\n{r.get('output') or '（无内容）'}",
                    )
            except Exception:
                logger.exception("后台工作流执行出错：%s", name)

        pool = "slow" if platform == "comfyui" else "fast"  # ComfyUI 走慢池(#5)
        if submit_background(_work, pool=pool):
            return f"工作流「{name}」已开始，完成后我会把结果发到群里。"
        return "任务太多、系统繁忙，请稍后再让我跑。"

    def _record_workflow_run(self, slug, platform, ctx, user_input, result) -> None:
        """尽力把运行记录落库；DB 不可用就跳过（不影响已拿到的结果）。"""
        try:
            from cosmac.db import session_scope
            from cosmac.db.wf_repo import record_run

            with session_scope() as s:
                record_run(
                    s, slug=slug, platform=platform, room_id=ctx.room_id,
                    sender=ctx.sender, user_input=user_input, result=result,
                )
        except Exception:
            pass
