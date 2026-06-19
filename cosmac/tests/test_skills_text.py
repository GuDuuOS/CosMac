"""skills_text.render_skills 的健壮性测试。

守两条线：
  - #1 脏数据（非字符串字段）也绝不抛异常（否则 bot 会因此不回复）；
  - #2 总长度上限对**第一条**也生效（单条超长会被截断，不会绕过预算）。
"""

from __future__ import annotations

import unittest

from cosmac.skills_text import MAX_TOTAL_PROMPT_CHARS, render_skills


class TestRenderSkills(unittest.TestCase):
    def test_empty(self) -> None:
        self.assertEqual(render_skills([]), "")

    def test_dirty_types_do_not_crash(self) -> None:
        # name 是数字、description 是 None、整项不是 dict —— 都不能抛
        items = [
            {"name": 123, "instructions": 456},
            {"slug": "ok", "description": None, "instructions": "正文"},
            "我不是字典",  # type: ignore[list-item]
        ]
        out = render_skills(items)  # 不抛异常即通过
        self.assertIn("123", out)  # 数字被转成字符串渲染
        self.assertIn("正文", out)

    def test_single_oversized_skill_is_truncated(self) -> None:
        # 单条 12000 字 —— 必须被截断，总长度 ≤ 上限（+一点提示余量）
        big = "字" * 12000
        out = render_skills([{"name": "巨技能", "instructions": big}])
        self.assertLessEqual(len(out), MAX_TOTAL_PROMPT_CHARS + 30)
        self.assertIn("已截断", out)

    def test_total_budget_across_many(self) -> None:
        big = "字" * 1500
        items = [{"name": f"技能{i}", "instructions": big} for i in range(20)]
        out = render_skills(items)
        self.assertLessEqual(len(out), MAX_TOTAL_PROMPT_CHARS + 30)
        self.assertIn("未注入", out)


if __name__ == "__main__":
    unittest.main()
