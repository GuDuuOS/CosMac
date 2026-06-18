"""管理后台「AI 配置」运行时下发的单元测试。

不依赖运行中的 Synapse、不需要 key：用假 MatrixClient 模拟"控制室里读到的配置"，
验证 bot 会按下发的人设/模型/工具开关热应用，且**读不到时完全回退启动配置**。

运行：.venv/bin/python -m unittest cosmac.tests.test_runtime_config
"""

from __future__ import annotations

import unittest
from typing import Any, Dict, Optional

from cosmac.ai.tools import ToolContext
from cosmac.ai.base import ToolCall
from cosmac.bots.appservice_bot import CosmacBot
from cosmac.config import CosmacConfig


class FakeClient:
    """假 MatrixClient：构造期 set_displayname 等被调到也无所谓，只关心配置读取。"""

    def __init__(self, alias_room: Optional[str], state: Optional[Dict[str, Any]]):
        self._alias_room = alias_room
        self._state = state

    # CosmacBot 构造/启动会用到的方法，给空实现
    def set_displayname(self, *_a, **_k): pass
    def send_text(self, *_a, **_k): return "$e"

    # 配置读取相关
    def resolve_alias(self, alias: str) -> Optional[str]:
        return self._alias_room

    def get_state_event(self, room_id, event_type, state_key=""):
        return self._state


def _bot(alias_room, state) -> CosmacBot:
    """构造一个用假 client 的 bot（provider=echo，无需 key）。"""
    bot = CosmacBot(CosmacConfig(llm_provider="echo"))
    bot.client = FakeClient(alias_room, state)  # 换成假 client
    return bot


class TestRuntimeConfig(unittest.TestCase):
    def test_no_control_room_keeps_startup_config(self) -> None:
        # 控制室解析不到 → 覆盖为空 → 签名不变、全工具启用（零回归）
        bot = _bot(alias_room=None, state=None)
        before = bot._applied_sig
        bot._apply_runtime_config()
        self.assertEqual(bot._applied_sig, before)
        self.assertEqual(len(bot.toolbox.specs()), 4)  # 仍是全部 4 个工具

    def test_persona_override_rebuilds_agent(self) -> None:
        # 下发新人设 → 签名变、Agent 被换成新对象、system_prompt 生效
        bot = _bot("!ctrl:host", {"system_prompt": "你是测试版人设"})
        old_agent = bot.agent
        bot._apply_runtime_config()
        self.assertEqual(bot._applied_sig[2], "你是测试版人设")
        self.assertIsNot(bot.agent, old_agent)
        self.assertEqual(bot.agent.system_prompt, "你是测试版人设")

    def test_tool_toggle_filters_specs(self) -> None:
        # 只启用 create_room → specs 只剩它；停用的工具执行被拒
        bot = _bot("!ctrl:host", {"enabled_tools": ["create_room"]})
        bot._apply_runtime_config()
        names = [s.name for s in bot.toolbox.specs()]
        self.assertEqual(names, ["create_room"])
        out = bot.toolbox.execute(
            ToolCall(id="x", name="send_message_to_room", arguments={"text": "hi"}),
            ToolContext("!r:host", "@a:host"),
        )
        self.assertIn("停用", out)

    def test_cache_avoids_refetch(self) -> None:
        # 20s 缓存：第一次读到配置后，把 state 改掉也仍返回缓存（不重复打服务器）
        bot = _bot("!ctrl:host", {"system_prompt": "甲"})
        first = bot._read_overrides()
        self.assertEqual(first.get("system_prompt"), "甲")
        bot.client._state = {"system_prompt": "乙"}  # 改掉源
        second = bot._read_overrides()  # 仍在缓存窗口内
        self.assertEqual(second.get("system_prompt"), "甲")

    def test_read_failure_falls_back(self) -> None:
        # get_state_event 抛异常 → _read_overrides 不崩、回退（空/上次），_apply 不报错
        bot = _bot("!ctrl:host", {"system_prompt": "甲"})

        def boom(*_a, **_k):
            raise RuntimeError("network down")

        bot.client.get_state_event = boom  # type: ignore
        # 不应抛异常
        bot._apply_runtime_config()


if __name__ == "__main__":
    unittest.main()
