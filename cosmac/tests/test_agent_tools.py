"""Agent 工具调用循环的单元测试。

不依赖运行中的 Synapse、不需要任何 API key：
  - 用一个"假大脑"(FakeLLM) 按脚本先要求调用工具、再给最终答复；
  - 用一个"假 MatrixClient"(FakeClient) 记录工具到底有没有真的被调到。
这样就能纯逻辑验证「模型决定调工具 → 工具真的执行 → 结果回灌 → 给出最终回复」整条链路。

运行：.venv/bin/python -m unittest cosmac.tests.test_agent_tools
"""

from __future__ import annotations

import unittest
from typing import List

from cosmac.ai.agent import Agent
from cosmac.ai.base import LLMProvider, Message, ToolCall, ToolSpec, TurnResult
from cosmac.ai.tools import Toolbox, ToolContext


class FakeClient:
    """假的 MatrixClient：只记录被调用了什么，不连任何服务器。"""

    def __init__(self) -> None:
        self.created: List[str] = []
        self.sent: List[tuple] = []

    def create_room(self, name, invitees=None):
        self.created.append(name)
        return "!fakeroom:test"  # 假装建好了，返回一个 room_id

    def send_text(self, room_id, text):
        self.sent.append((room_id, text))
        return "$fakeevent"

    def get_members(self, room_id):
        return [{"user_id": "@alice:test", "display_name": "Alice"}]

    def get_messages(self, room_id, limit=20):
        return [{"sender": "@alice:test", "body": "历史消息一条"}]


class FakeLLM(LLMProvider):
    """假大脑：按预设脚本逐轮返回 TurnResult（先调工具，再给最终文本）。"""

    name = "fake"

    def __init__(self, script: List[TurnResult]) -> None:
        self._script = script
        self._i = 0
        self.seen_tools: List[str] = []  # 记录每轮拿到的工具名，验证确实把工具喂进去了

    def complete(self, messages: List[Message]) -> str:  # 接口要求，测试用不到
        return "（不该走到这里）"

    def complete_with_tools(self, messages, tools: List[ToolSpec]) -> TurnResult:
        self.seen_tools = [t.name for t in tools]
        result = self._script[self._i]
        self._i += 1
        return result


class TestAgentTools(unittest.TestCase):
    def _agent(self, script):
        self.client = FakeClient()
        toolbox = Toolbox(self.client)  # 真工具箱，但底层是假 client
        llm = FakeLLM(script)
        return Agent(llm=llm, toolbox=toolbox, system_prompt="测试人设"), llm

    def test_model_calls_create_room_then_answers(self) -> None:
        # 脚本：第一轮要求建群，第二轮给最终答复
        script = [
            TurnResult(
                tool_calls=[
                    ToolCall(id="c1", name="create_room", arguments={"name": "爆款专班"})
                ]
            ),
            TurnResult(text="已经帮你把『爆款专班』群建好啦！"),
        ]
        agent, llm = self._agent(script)
        reply = agent.run("帮我建个爆款专班群", ToolContext("!cur:test", "@alice:test"))

        # 工具真的被执行了（假 client 记录到建群）
        self.assertEqual(self.client.created, ["爆款专班"])
        # 最终回复是模型第二轮给的文本
        self.assertEqual(reply, "已经帮你把『爆款专班』群建好啦！")
        # 模型每轮都拿到了 4 个工具的说明书
        self.assertIn("create_room", llm.seen_tools)

    def test_create_room_invites_requester(self) -> None:
        # 验证 ToolContext 注入：建群默认把发起人拉进去
        captured = {}
        client = FakeClient()
        client.create_room = lambda name, invitees=None: (  # type: ignore
            captured.update(name=name, invitees=invitees) or "!r:test"
        )
        toolbox = Toolbox(client)
        out = toolbox.execute(
            ToolCall(id="x", name="create_room", arguments={"name": "群A"}),
            ToolContext("!cur:test", "@bob:test"),
        )
        self.assertEqual(captured["name"], "群A")
        self.assertIn("@bob:test", captured["invitees"])  # 发起人被自动邀请
        self.assertIn("群A", out)

    def test_no_tool_calls_returns_text(self) -> None:
        # 模型不调工具时，直接返回文本
        agent, _ = self._agent([TurnResult(text="你好呀")])
        reply = agent.run("在吗", ToolContext("!c:test", "@a:test"))
        self.assertEqual(reply, "你好呀")

    def test_max_steps_guard(self) -> None:
        # 模型一直要求调工具（不收敛），Agent 应在 max_steps 后兜底退出，不死循环
        loop = TurnResult(
            tool_calls=[ToolCall(id="c", name="list_room_members", arguments={})]
        )
        client = FakeClient()
        agent = Agent(FakeLLM([loop] * 10), Toolbox(client), max_steps=3)
        reply = agent.run("看看谁在", ToolContext("!c:test", "@a:test"))
        self.assertIn("没能完成", reply)


if __name__ == "__main__":
    unittest.main()
