"""自建邮箱验证码注册的核心逻辑单测。

不发真邮件、不调真 Synapse：把 `_send_email` 和 `_synapse_register` 打桩，
聚焦验证「发码→验码→建号」的状态机、限频、错码/过期/尝试上限等分支。
"""

from __future__ import annotations

import unittest

from cosmac import registration as reg


class RegistrationTest(unittest.TestCase):
    def setUp(self) -> None:
        # 每个用例独立的内存态 + 打桩
        reg._store.clear()
        self._sent: list[tuple[str, str]] = []
        reg._send_email = lambda to, code: self._sent.append((to, code))  # type: ignore
        # 让 registration_enabled() 为真（绕过 env 检查）
        reg.registration_enabled = lambda: True  # type: ignore
        # 建号成功桩：回 200 + 假 user_id
        reg._synapse_register = lambda hs, u, p: (  # type: ignore
            200, {"user_id": f"@{u}:test", "access_token": "tok"})

    def _last_code(self) -> str:
        return self._sent[-1][1]

    def test_happy_path(self) -> None:
        code, body = reg.request_code("a@b.com")
        self.assertEqual(code, 200)
        self.assertEqual(len(self._sent), 1)
        # 用收到的码验证 + 建号
        st, payload = reg.verify_and_register(
            "a@b.com", self._last_code(), "alice", "Test1234!", hs_url="http://hs")
        self.assertEqual(st, 200)
        self.assertEqual(payload["user_id"], "@alice:test")

    def test_wrong_code_rejected(self) -> None:
        reg.request_code("a@b.com")
        st, payload = reg.verify_and_register(
            "a@b.com", "000000", "alice", "Test1234!", hs_url="http://hs")
        self.assertEqual(st, 400)
        self.assertIn("验证码", payload["error"])

    def test_code_is_single_use(self) -> None:
        reg.request_code("a@b.com")
        c = self._last_code()
        reg.verify_and_register("a@b.com", c, "alice", "Test1234!", hs_url="http://hs")
        # 同一个码再用一次应失败（已作废）
        st, _ = reg.verify_and_register("a@b.com", c, "bob", "Test1234!", hs_url="http://hs")
        self.assertEqual(st, 400)

    def test_resend_cooldown(self) -> None:
        reg.request_code("a@b.com")
        st, payload = reg.request_code("a@b.com")  # 立刻再发 → 命中冷却
        self.assertEqual(st, 429)
        self.assertIn("cooldown", payload)

    def test_bad_email_rejected(self) -> None:
        st, _ = reg.request_code("not-an-email")
        self.assertEqual(st, 400)

    def test_weak_password_rejected(self) -> None:
        reg.request_code("a@b.com")
        st, payload = reg.verify_and_register(
            "a@b.com", self._last_code(), "alice", "123", hs_url="http://hs")
        self.assertEqual(st, 400)
        self.assertIn("密码", payload["error"])

    def test_bad_username_rejected(self) -> None:
        reg.request_code("a@b.com")
        st, payload = reg.verify_and_register(
            "a@b.com", self._last_code(), "Alice Space", "Test1234!", hs_url="http://hs")
        self.assertEqual(st, 400)
        self.assertIn("用户名", payload["error"])


class PasswordResetTest(unittest.TestCase):
    def setUp(self) -> None:
        reg._store.clear()
        self._sent: list[tuple[str, str]] = []
        self._reset_calls: list[tuple[str, str]] = []  # (user_id, new_password)
        reg.reset_enabled = lambda: True  # type: ignore
        reg._send_reset_email = lambda to, code: self._sent.append((to, code))  # type: ignore
        # 只有 a@b.com 注册过 → 映射到 alice
        reg._lookup_username = lambda email: "alice" if email == "a@b.com" else None  # type: ignore
        reg._admin_reset_password = lambda hs, uid, pw: (  # type: ignore
            self._reset_calls.append((uid, pw)) or (200, {"ok": True}))

    def _last_code(self) -> str:
        return self._sent[-1][1]

    def test_registered_email_sends_code(self) -> None:
        st, _ = reg.reset_request_code("a@b.com")
        self.assertEqual(st, 200)
        self.assertEqual(len(self._sent), 1)

    def test_unknown_email_no_send_but_ok(self) -> None:
        # 防枚举：未注册邮箱也回 200，但不真发信
        st, _ = reg.reset_request_code("nope@x.com")
        self.assertEqual(st, 200)
        self.assertEqual(len(self._sent), 0)

    def test_reset_happy_path(self) -> None:
        reg.reset_request_code("a@b.com")
        st, payload = reg.reset_verify(
            "a@b.com", self._last_code(), "NewPass123!", hs_url="http://hs", server_name="cosmac.cc")
        self.assertEqual(st, 200)
        # 确认拿正确的 user_id + 新密码去调了重置
        self.assertEqual(self._reset_calls, [("@alice:cosmac.cc", "NewPass123!")])

    def test_reset_wrong_code(self) -> None:
        reg.reset_request_code("a@b.com")
        st, _ = reg.reset_verify(
            "a@b.com", "000000", "NewPass123!", hs_url="http://hs", server_name="cosmac.cc")
        self.assertEqual(st, 400)
        self.assertEqual(self._reset_calls, [])  # 没验过码就不该调重置

    def test_reset_weak_password(self) -> None:
        reg.reset_request_code("a@b.com")
        st, payload = reg.reset_verify(
            "a@b.com", self._last_code(), "123", hs_url="http://hs", server_name="cosmac.cc")
        self.assertEqual(st, 400)
        self.assertIn("密码", payload["error"])

    def test_register_code_cannot_reset(self) -> None:
        # 注册码和找回码分桶：注册码不能拿去重置
        reg.registration_enabled = lambda: True  # type: ignore
        reg._send_email = lambda to, code: self._sent.append((to, code))  # type: ignore
        reg.request_code("a@b.com")          # 注册码
        reg_code = self._last_code()
        st, _ = reg.reset_verify(
            "a@b.com", reg_code, "NewPass123!", hs_url="http://hs", server_name="cosmac.cc")
        self.assertEqual(st, 400)  # reset 桶里没这个码


if __name__ == "__main__":
    unittest.main()
