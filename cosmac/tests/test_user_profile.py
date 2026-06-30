"""用户「个人偏好画像」(About me / Outputs) 单元测试：repo + 渲染 + bot 端点 + 注入。

内存 SQLite、零 key。运行：.venv/bin/python -m unittest cosmac.tests.test_user_profile
"""

from __future__ import annotations

import unittest

from cosmac.db import init_engine, session_scope
from cosmac.db.user_profile_repo import (
    get_profile,
    render_profile_text,
    to_dict,
    upsert_profile,
)


class TestUserProfileRepo(unittest.TestCase):
    def setUp(self) -> None:
        init_engine("sqlite://", create_all=True)

    def test_upsert_get_unique(self) -> None:
        with session_scope() as s:
            upsert_profile(s, user_id="@a:h", about="我是导演", style="简短直接")
        # 同一用户再写 = 更新、不新增
        with session_scope() as s:
            upsert_profile(s, user_id="@a:h", about="我是制片", style="用中文")
        with session_scope() as s:
            p = get_profile(s, "@a:h")
            self.assertIsNotNone(p)
            self.assertEqual(p.about, "我是制片")
            self.assertEqual(p.style, "用中文")

    def test_truncate_and_empty_user(self) -> None:
        with session_scope() as s:
            p = upsert_profile(s, user_id="@a:h", about="x" * 5000)
            self.assertEqual(len(p.about), 2000)  # 被截断
        with session_scope() as s:
            with self.assertRaises(ValueError):
                upsert_profile(s, user_id="  ")

    def test_to_dict_default(self) -> None:
        d = to_dict(None)
        self.assertEqual(d, {"about": "", "style": "", "extra": "", "enabled": True})

    def test_render(self) -> None:
        with session_scope() as s:
            p = upsert_profile(s, user_id="@a:h", about="导演", style="简短")
            txt = render_profile_text(p)
        self.assertIn("导演", txt)
        self.assertIn("简短", txt)
        self.assertIn("优先级最低", txt)  # 防注入：显式声明优先级
        # 停用 → 空串
        with session_scope() as s:
            p = upsert_profile(s, user_id="@a:h", about="导演", enabled=False)
            self.assertEqual(render_profile_text(p), "")
        # 全空 → 空串
        with session_scope() as s:
            p = upsert_profile(s, user_id="@b:h")
            self.assertEqual(render_profile_text(p), "")
        # None → 空串
        self.assertEqual(render_profile_text(None), "")


def _bot():
    from cosmac.bots.appservice_bot import CosmacBot
    from cosmac.config import CosmacConfig

    return CosmacBot(CosmacConfig(llm_provider="echo"))


class TestUserProfileEndpoints(unittest.TestCase):
    def setUp(self) -> None:
        init_engine("sqlite://", create_all=True)

    def test_save_read_and_auth(self) -> None:
        bot = _bot()
        bot.client.whoami = lambda t: "@alice:h" if t == "ok" else None  # type: ignore
        # 未登录
        self.assertEqual(bot.handle_profile_mine("")[0], 401)
        self.assertEqual(bot.handle_profile_save("", {"about": "x"})[0], 401)
        # 没设过 → 空白默认
        code, payload = bot.handle_profile_mine("ok")
        self.assertEqual(code, 200)
        self.assertEqual(payload["profile"]["about"], "")
        self.assertTrue(payload["profile"]["enabled"])
        # 保存
        code, payload = bot.handle_profile_save(
            "ok", {"about": "我是博主", "style": "用 emoji", "enabled": True}
        )
        self.assertEqual(code, 200)
        self.assertEqual(payload["profile"]["about"], "我是博主")
        # 再读回
        _, payload = bot.handle_profile_mine("ok")
        self.assertEqual(payload["profile"]["style"], "用 emoji")

    def test_injection_into_addendum(self) -> None:
        """画像应注入主 AI 的 system addendum；停用后不注入；只对发起人本人生效。"""
        bot = _bot()
        # 隔离掉会触网的来源（控制室别名/状态事件），只留用户画像这一路
        bot.client.resolve_alias = lambda a: None  # type: ignore
        bot.client.get_state_event = lambda *a, **k: None  # type: ignore
        bot.client.get_room_state = lambda r: []  # type: ignore
        with session_scope() as s:
            upsert_profile(s, user_id="@alice:h", about="我是纪录片导演")
        # _user_profile_text 直接读
        self.assertIn("纪录片导演", bot._user_profile_text("@alice:h"))
        # 别的用户读不到 alice 的（跟人走、隔离）
        self.assertEqual(bot._user_profile_text("@bob:h"), "")
        # 进 _skill_addendum（其余来源缺省都为空，不影响）
        add = bot._skill_addendum("!room:h", "@alice:h")
        self.assertIn("纪录片导演", add)
        # 停用后不再注入
        with session_scope() as s:
            upsert_profile(s, user_id="@alice:h", about="我是纪录片导演", enabled=False)
        self.assertNotIn("纪录片导演", bot._skill_addendum("!room:h", "@alice:h"))


if __name__ == "__main__":
    unittest.main()
