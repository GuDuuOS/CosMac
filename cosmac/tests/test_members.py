"""会员等级（cosmac.members）的回归测试。

覆盖：
  - 纯逻辑：normalize/label/level/parse 的脏数据兜底；
  - MembersStore：读 map / 查等级 / 授予 / 撤销（用假 client，断言写回的 state 内容）；
  - bot 会员命令：普通人查自己、非管理员被挡、管理员设置/撤销/列表。
"""

from __future__ import annotations

import unittest
from typing import Any, Dict, Optional

from cosmac.bots.appservice_bot import CosmacBot
from cosmac.config import CosmacConfig
from cosmac.config import GATING_EVENT_TYPE
from cosmac.members import (
    DEFAULT_TIER,
    GATE_ADMIN,
    TIER_CREATOR,
    TIER_FREE,
    TIER_PAID,
    GatingStore,
    MembersStore,
    gate_rank,
    normalize_tier,
    parse_gates,
    parse_members,
    tier_label,
    tier_level,
)

CTRL = "!ctrl:guduu.local"
BOT = "@guduu:guduu.local"
ADMIN = "@admin:guduu.local"
ALICE = "@alice:guduu.local"
BOB = "@bob:guduu.local"


class FakeClient:
    """假 client：内存存 state event + power_levels，记录写入，便于断言。"""

    def __init__(self, alias_room: Optional[str], ctrl_admin: bool = True):
        self._alias_room = alias_room
        # 控制室成员谁有 power（_is_platform_admin 读这个）
        self._power = {BOT: 100}
        if ctrl_admin:
            self._power[ADMIN] = 50
        self._state: Dict[str, Dict[str, Any]] = {}  # event_type → content
        self.sent: list = []

    def resolve_alias(self, _alias: str) -> Optional[str]:
        return self._alias_room

    def get_state_event(self, _room, event_type, _state_key=""):
        if event_type == "m.room.power_levels":
            return {"users": dict(self._power)}
        return self._state.get(event_type)

    def set_state_event(self, _room, event_type, content, _state_key="") -> bool:
        self._state[event_type] = content
        return True

    def send_text(self, _room, text, txn_id=None):
        self.sent.append(text)
        return "$evt"

    def joined_member_count(self, _room) -> int:
        return 2  # 当私聊处理（不影响会员命令）

    def set_displayname(self, *_a, **_k):
        pass


def _store(alias_room=CTRL) -> MembersStore:
    return MembersStore(FakeClient(alias_room), "#cosmac-ctrl:guduu.local")


def _bot(ctrl_admin=True, alias_room=CTRL, gates=None) -> CosmacBot:
    bot = CosmacBot(CosmacConfig(llm_provider="echo"))
    fake = FakeClient(alias_room, ctrl_admin=ctrl_admin)
    if gates is not None:
        fake._state[GATING_EVENT_TYPE] = {"gates": gates}
    bot.client = fake
    # MembersStore/GatingStore 持有的是构造时的 client，要替换成同一个 fake。
    # GatingStore ttl=0：测试里每次都重读，避免缓存掩盖刚设的门控。
    bot.members = MembersStore(fake, bot.config.control_room_alias)
    bot.gating = GatingStore(fake, bot.config.control_room_alias, ttl=0)
    return bot


class PureLogicTests(unittest.TestCase):
    def test_normalize_unknown_to_free(self):
        self.assertEqual(normalize_tier("paid"), TIER_PAID)
        self.assertEqual(normalize_tier("nonsense"), DEFAULT_TIER)
        self.assertEqual(normalize_tier(None), DEFAULT_TIER)
        self.assertEqual(normalize_tier(""), DEFAULT_TIER)

    def test_label_and_level(self):
        self.assertEqual(tier_label("paid"), "付费会员")
        self.assertEqual(tier_label("bogus"), "免费会员")
        self.assertGreater(tier_level(TIER_CREATOR), tier_level(TIER_PAID))
        self.assertGreater(tier_level(TIER_PAID), tier_level(DEFAULT_TIER))

    def test_parse_drops_free_and_garbage(self):
        content = {
            "members": {
                ALICE: {"tier": "paid"},
                BOB: {"tier": "free"},        # 免费=默认，丢弃
                "not-a-user": {"tier": "paid"},  # 非法 key，丢弃
                "@c:guduu.local": {"tier": "junk"},  # 非法 tier → 规整成 free → 丢弃
            }
        }
        out = parse_members(content)
        self.assertEqual(set(out.keys()), {ALICE})
        self.assertEqual(out[ALICE]["tier"], TIER_PAID)

    def test_parse_empty(self):
        self.assertEqual(parse_members(None), {})
        self.assertEqual(parse_members({}), {})
        self.assertEqual(parse_members({"members": "x"}), {})


class MembersStoreTests(unittest.TestCase):
    def test_grant_writes_state(self):
        s = _store()
        self.assertTrue(s.grant(ALICE, TIER_PAID, now_ts=123))
        mp = s.get_all()
        self.assertEqual(mp[ALICE]["tier"], TIER_PAID)
        self.assertEqual(mp[ALICE]["updated_ts"], 123)
        self.assertEqual(s.get_tier(ALICE), TIER_PAID)
        # 未授予的人默认免费
        self.assertEqual(s.get_tier(BOB), DEFAULT_TIER)

    def test_grant_invalid_tier_rejected(self):
        s = _store()
        self.assertFalse(s.grant(ALICE, "vip"))
        self.assertEqual(s.get_tier(ALICE), DEFAULT_TIER)

    def test_free_grant_is_revoke(self):
        s = _store()
        s.grant(ALICE, TIER_CREATOR)
        self.assertEqual(s.get_tier(ALICE), TIER_CREATOR)
        self.assertTrue(s.revoke(ALICE))
        self.assertEqual(s.get_tier(ALICE), DEFAULT_TIER)
        self.assertNotIn(ALICE, s.get_all())

    def test_no_control_room(self):
        s = _store(alias_room=None)
        self.assertFalse(s.grant(ALICE, TIER_PAID))
        self.assertEqual(s.get_all(), {})


class BotCommandTests(unittest.TestCase):
    def test_self_check_default_free(self):
        bot = _bot()
        out = bot._run_member_command(ALICE, "会员")
        self.assertIn("免费会员", out)

    def test_non_admin_cannot_set(self):
        bot = _bot()
        out = bot._run_member_command(ALICE, "会员 设置 @bob:guduu.local 付费")
        self.assertIn("只有平台管理员", out)
        self.assertEqual(bot.members.get_tier(BOB), DEFAULT_TIER)

    def test_admin_set_and_revoke(self):
        bot = _bot()
        out = bot._run_member_command(ADMIN, "会员 设置 @alice:guduu.local 创作者")
        self.assertIn("创作者会员", out)
        self.assertEqual(bot.members.get_tier(ALICE), TIER_CREATOR)
        # 自查反映新等级
        self.assertIn("创作者会员", bot._run_member_command(ALICE, "会员"))
        # 撤销
        out = bot._run_member_command(ADMIN, "会员 撤销 @alice:guduu.local")
        self.assertIn("免费会员", out)
        self.assertEqual(bot.members.get_tier(ALICE), DEFAULT_TIER)

    def test_admin_set_unknown_tier(self):
        bot = _bot()
        out = bot._run_member_command(ADMIN, "会员 设置 @alice:guduu.local 钻石")
        self.assertIn("未知等级", out)

    def test_admin_list(self):
        bot = _bot()
        bot.members.grant(ALICE, TIER_PAID)
        out = bot._run_member_command(ADMIN, "会员 列表")
        self.assertIn(ALICE, out)
        self.assertIn("付费会员", out)

    def test_command_detection(self):
        bot = _bot()
        self.assertTrue(bot._is_member_command("会员"))
        self.assertTrue(bot._is_member_command("我的会员"))
        self.assertTrue(bot._is_member_command("member"))
        self.assertFalse(bot._is_member_command("会议安排"))

    def test_grant_member_tier_reserved_entry(self):
        bot = _bot()
        self.assertTrue(bot.grant_member_tier(BOB, TIER_PAID))
        self.assertEqual(bot.members.get_tier(BOB), TIER_PAID)
        # 来源记为 purchase（区别于管理员手动）
        self.assertEqual(bot.members.get_all()[BOB]["source"], "purchase")


class GatingPureTests(unittest.TestCase):
    def test_gate_rank_order(self):
        self.assertLess(gate_rank(TIER_FREE), gate_rank(TIER_PAID))
        self.assertLess(gate_rank(TIER_PAID), gate_rank(TIER_CREATOR))
        self.assertLess(gate_rank(TIER_CREATOR), gate_rank(GATE_ADMIN))
        self.assertEqual(gate_rank("junk"), 0)

    def test_parse_gates_validates(self):
        content = {"gates": {
            "ai_chat": "paid",        # ok
            "knowledge": "diamond",   # 非法门槛 → 丢
            "bogus_cap": "paid",      # 非法能力 → 丢
            "workflow_run": "admin",  # ok
        }}
        out = parse_gates(content)
        self.assertEqual(out, {"ai_chat": "paid", "workflow_run": "admin"})

    def test_gating_store_defaults_and_override(self):
        fake = FakeClient(CTRL)
        store = GatingStore(fake, "#cosmac-ctrl:guduu.local", ttl=0)
        # 默认：ai_chat 免费、workflow_run 仅管理员
        self.assertEqual(store.required("ai_chat"), TIER_FREE)
        self.assertEqual(store.required("workflow_run"), GATE_ADMIN)
        # 覆盖后生效
        fake._state[GATING_EVENT_TYPE] = {"gates": {"ai_chat": "creator"}}
        self.assertEqual(store.required("ai_chat"), TIER_CREATOR)


class GateDecisionTests(unittest.TestCase):
    def test_free_gate_allows_everyone(self):
        bot = _bot(gates={"knowledge": "free"})
        self.assertTrue(bot._gate_allows(ALICE, "knowledge"))

    def test_paid_gate_blocks_free_user(self):
        bot = _bot(gates={"knowledge": "paid"})
        self.assertFalse(bot._gate_allows(ALICE, "knowledge"))  # ALICE 默认免费
        bot.members.grant(ALICE, TIER_PAID)
        self.assertTrue(bot._gate_allows(ALICE, "knowledge"))

    def test_creator_gate_needs_creator(self):
        bot = _bot(gates={"create_room": "creator"})
        bot.members.grant(ALICE, TIER_PAID)
        self.assertFalse(bot._gate_allows(ALICE, "create_room"))  # 付费 < 创作者
        bot.members.grant(ALICE, TIER_CREATOR)
        self.assertTrue(bot._gate_allows(ALICE, "create_room"))

    def test_platform_admin_bypasses_tier_gate(self):
        bot = _bot(gates={"knowledge": "creator"})
        # ADMIN 是平台管理员(power 50)，即便没有会员等级也放行
        self.assertTrue(bot._gate_allows(ADMIN, "knowledge"))

    def test_admin_gate_only_platform_admin(self):
        bot = _bot(gates={"workflow_run": "admin"})
        self.assertTrue(bot._gate_allows(ADMIN, "workflow_run"))
        bot.members.grant(ALICE, TIER_CREATOR)  # 即便创作者也过不了 admin 门
        self.assertFalse(bot._gate_allows(ALICE, "workflow_run"))

    def test_tool_gate_check_maps_and_denies(self):
        bot = _bot(gates={"create_room": "paid"})
        # 免费用户被工具门控拦下（返回拒绝文案）
        denial = bot._tool_gate_check(ALICE, "create_room")
        self.assertIsNotNone(denial)
        self.assertIn("付费会员", denial)
        # 不在映射表里的工具不门控
        self.assertIsNone(bot._tool_gate_check(ALICE, "list_room_members"))
        # 付费后放行
        bot.members.grant(ALICE, TIER_PAID)
        self.assertIsNone(bot._tool_gate_check(ALICE, "create_room"))

    def test_kb_command_gated(self):
        bot = _bot(gates={"knowledge": "paid"})
        out = bot._run_kb_command(CTRL, ALICE, "知识 列表")
        self.assertIn("付费会员", out)  # 免费用户被门控拦下、给升级提示


if __name__ == "__main__":
    unittest.main()
