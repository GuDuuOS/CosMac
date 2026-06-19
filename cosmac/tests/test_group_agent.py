"""本群绑定智能体 / 自定义人设 → bot 注入的单元测试。

用假 MatrixClient 模拟「频道配置 + 控制室里的全局智能体/技能」三个 state event，
验证 bot 的 _skill_addendum 会按本群绑定注入对应人设与技能。不连真服务器、不需要 key。

运行：.venv/bin/python -m unittest cosmac.tests.test_group_agent
"""

from __future__ import annotations

import unittest
from typing import Any, Dict, Optional

from cosmac.bots.appservice_bot import CosmacBot
from cosmac.config import (
    AGENTS_EVENT_TYPE,
    CHANNEL_CONFIG_EVENT_TYPE,
    SKILLS_EVENT_TYPE,
    CosmacConfig,
)
from cosmac.db import init_engine

CTRL = "!ctrl:host"
ROOM = "!grp:host"


class FakeClient:
    """按 (event_type) 返回不同 state event；其余调用给安全默认。"""

    def __init__(self, channel_cfg: Optional[Dict], agents: Optional[Dict], skills: Optional[Dict]):
        self._by_type = {
            CHANNEL_CONFIG_EVENT_TYPE: channel_cfg,
            AGENTS_EVENT_TYPE: agents,
            SKILLS_EVENT_TYPE: skills,
        }

    def set_displayname(self, *_a, **_k): pass
    def send_text(self, *_a, **_k): return "$e"
    def resolve_alias(self, _alias: str) -> Optional[str]: return CTRL
    def joined_member_count(self, _room: str) -> int: return 5  # 群聊

    def get_state_event(self, _room_id: str, event_type: str, _state_key: str = "") -> Any:
        return self._by_type.get(event_type)


def _bot(channel_cfg=None, agents=None, skills=None) -> CosmacBot:
    bot = CosmacBot(CosmacConfig(llm_provider="echo"))
    bot.client = FakeClient(channel_cfg, agents, skills)
    return bot


class TestGroupAgent(unittest.TestCase):
    def setUp(self) -> None:
        init_engine("sqlite://", create_all=True)  # 隔离的空 DB（群/个人技能为空）

    def test_bound_agent_injects_persona_and_skills(self) -> None:
        bot = _bot(
            channel_cfg={"persona": {"agentSlug": "planner"}},
            agents={"agents": [
                {"slug": "planner", "name": "策划", "system_prompt": "你是资深策划",
                 "skill_slugs": ["s1"], "enabled": True},
            ]},
            skills={"skills": [
                {"slug": "s1", "name": "周报", "instructions": "三步生成周报", "enabled": True},
                {"slug": "s2", "name": "选题", "instructions": "选题方法", "enabled": True},
            ]},
        )
        out = bot._skill_addendum(ROOM, "@u:host")
        self.assertIn("已绑定智能体「策划」", out)
        self.assertIn("你是资深策划", out)
        self.assertIn("三步生成周报", out)  # 绑定的技能 s1 注入

    def test_disabled_agent_falls_back_to_nothing(self) -> None:
        bot = _bot(
            channel_cfg={"persona": {"agentSlug": "planner"}},
            agents={"agents": [{"slug": "planner", "name": "策划", "enabled": False}]},
            skills={"skills": []},
        )
        out = bot._skill_addendum(ROOM, "@u:host")
        self.assertNotIn("已绑定智能体", out)  # 停用 → 找不到 → 不注入人设

    def test_free_text_persona_when_no_agent(self) -> None:
        bot = _bot(
            channel_cfg={"persona": {"prompt": "本群只聊技术"}},
            agents={"agents": []},
            skills={"skills": []},
        )
        out = bot._skill_addendum(ROOM, "@u:host")
        self.assertIn("本群人设", out)
        self.assertIn("本群只聊技术", out)

    def test_no_config_empty(self) -> None:
        bot = _bot(channel_cfg=None, agents=None, skills=None)
        self.assertEqual(bot._skill_addendum(ROOM, "@u:host"), "")

    def test_global_skills_still_inject_without_binding(self) -> None:
        # 没绑智能体，但有全局技能 → 全局技能照常注入（不依赖绑定）
        bot = _bot(
            channel_cfg=None,
            agents=None,
            skills={"skills": [{"slug": "g", "name": "全局技能", "instructions": "G正文", "enabled": True}]},
        )
        out = bot._skill_addendum(ROOM, "@u:host")
        self.assertIn("全局技能", out)
        self.assertIn("G正文", out)


if __name__ == "__main__":
    unittest.main()
