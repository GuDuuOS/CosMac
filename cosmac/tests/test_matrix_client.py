"""MatrixClient 的鉴权方式回归测试。

重点守住一条安全红线：高权限的 appservice as_token **绝不能出现在 URL 查询参数里**
（否则会进 nginx/代理/错误日志），必须走 Authorization: Bearer 请求头。
"""

from __future__ import annotations

import unittest

from cosmac.bots.matrix_client import MatrixClient


class TestMatrixClientAuth(unittest.TestCase):
    def setUp(self) -> None:
        self.token = "SECRET_AS_TOKEN_should_never_leak"
        self.client = MatrixClient(
            homeserver_url="http://hs:8008",
            as_token=self.token,
            bot_user_id="@guduu:hs",
        )

    def test_token_not_in_url(self) -> None:
        # 任意路径拼出来的 URL 都不能含 token；user_id（身份标识，非密钥）仍保留
        for path in (
            "/_matrix/client/v3/rooms/!r/join",
            "/_matrix/client/v3/createRoom",
            "/_matrix/client/v3/directory/room/%23a%3Ahs",
        ):
            url = self.client._url(path)
            self.assertNotIn(self.token, url, f"token 泄进了 URL: {url}")
            self.assertIn("user_id=", url)

    def test_token_in_bearer_header(self) -> None:
        # token 走 Authorization: Bearer 头，且挂在复用的 Session 上
        self.assertEqual(
            self.client._session.headers.get("Authorization"),
            f"Bearer {self.token}",
        )


if __name__ == "__main__":
    unittest.main()
