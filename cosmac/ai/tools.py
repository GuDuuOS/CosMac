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
from typing import Any, Callable, Dict, List

from cosmac.ai.base import ToolCall, ToolSpec
from cosmac.bots.matrix_client import MatrixClient

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

    def __init__(self, client: MatrixClient):
        self.client = client
        # 工具名 → (说明书, 执行函数)。执行函数签名: (arguments, ctx) -> 结果文本
        self._tools: Dict[str, Dict[str, Any]] = {}
        self._register_default_tools()

    # —— 对外接口 ——

    def specs(self) -> List[ToolSpec]:
        """返回所有工具的说明书（交给模型，让它知道有哪些工具可用）。"""
        return [entry["spec"] for entry in self._tools.values()]

    def execute(self, call: ToolCall, ctx: ToolContext) -> str:
        """执行一次工具调用，返回给模型读的文本结果（绝不抛异常，出错也转成文本）。"""
        entry = self._tools.get(call.name)
        if entry is None:
            return f"错误：不存在名为 {call.name} 的工具。"
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
