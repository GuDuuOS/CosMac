"""工作流连接器引擎单元测试（mock HTTP，不联网）。

运行：.venv/bin/python -m unittest cosmac.tests.test_wf
"""

from __future__ import annotations

import os
import unittest
from unittest import mock

import requests

from cosmac import wf


class FakeResp:
    def __init__(self, status_code=200, json_data=None, text="", content=b"", headers=None):
        self.status_code = status_code
        self._json = json_data
        self.text = text
        self.content = content
        self.headers = headers or {}

    # _fetch 走 stream=True：这两个让假响应兼容（iter_content 给内容、close 空操作）
    def iter_content(self, _n=8192):
        if self.content:
            yield self.content

    def close(self):
        pass

    def json(self):
        if self._json is None:
            raise ValueError("no json")
        return self._json


class FakeMxClient:
    """假 MatrixClient：记录 upload/send 次数，给 ComfyUI 测试用。"""

    def __init__(self):
        self.uploads = 0
        self.sends = 0

    def upload_media(self, data, mime, fname):
        self.uploads += 1
        return "mxc://h/" + fname

    def send_image(self, room, mxc, fname, info=None):
        self.sends += 1
        return "$e"


class TestWfEngine(unittest.TestCase):
    def setUp(self) -> None:
        # 这些用例验证"请求/解析逻辑"，URL 用 mock 主机（h/host 不可解析）。
        # SSRF 校验单独在 TestSsrfGuard 里验，这里放行它，专注请求逻辑。
        p = mock.patch.object(wf, "check_outbound_url", return_value="")
        p.start()
        self.addCleanup(p.stop)

    def test_credential_from_env(self) -> None:
        with mock.patch.dict(os.environ, {"COSMAC_WF_N8N_MAIN": "secret-123"}):
            self.assertEqual(wf.resolve_credential("n8n_main"), "secret-123")
        self.assertEqual(wf.resolve_credential(""), "")

    def test_webhook_success_extracts_output_field(self) -> None:
        conn = {"slug": "x", "url": "https://h/wh", "platform": "webhook"}
        with mock.patch.object(
            wf.requests, "request",
            return_value=FakeResp(200, {"output": "搞定啦"}),
        ) as m:
            r = wf.run_connector(conn, "做点事")
        self.assertTrue(r["ok"])
        self.assertEqual(r["output"], "搞定啦")
        # 校验:POST、带 input、JSON
        _, kwargs = m.call_args
        self.assertEqual(kwargs["json"]["input"], "做点事")

    def test_webhook_sends_bearer_when_cred_set(self) -> None:
        conn = {"slug": "x", "url": "https://h/wh", "cred": "n8n_main"}
        with mock.patch.dict(os.environ, {
            "COSMAC_WF_N8N_MAIN": "tok", "COSMAC_WF_N8N_MAIN_HOST": "h",  # #1 绑定域名
        }), mock.patch.object(
            wf.requests, "request", return_value=FakeResp(200, {"result": "ok"})
        ) as m:
            wf.run_connector(conn, "hi")
        _, kwargs = m.call_args
        self.assertEqual(kwargs["headers"].get("Authorization"), "Bearer tok")

    def test_webhook_refuses_unbound_credential(self) -> None:
        # #1：凭据有 secret 但没绑定域名 → 拒绝外发密钥（防凭据被导出到任意 URL）
        conn = {"url": "https://attacker.test/wh", "cred": "n8n_main"}
        with mock.patch.dict(os.environ, {"COSMAC_WF_N8N_MAIN": "tok"}, clear=False):
            os.environ.pop("COSMAC_WF_N8N_MAIN_HOST", None)
            r = wf.run_connector(conn, "hi")
        self.assertFalse(r["ok"])
        self.assertIn("未绑定域名", r["error"])

    def test_webhook_refuses_http_for_credential(self) -> None:
        # #3：带密钥不能走明文 HTTP（会被网络窃取）；开内网开关才放行
        conn = {"url": "http://n8n.mycorp.com/wh", "cred": "n8n_main"}
        env = {"COSMAC_WF_N8N_MAIN": "tok", "COSMAC_WF_N8N_MAIN_HOST": "n8n.mycorp.com"}
        with mock.patch.dict(os.environ, env, clear=False):
            os.environ.pop("COSMAC_WF_ALLOW_INTERNAL", None)
            r = wf.run_connector(conn, "hi")
        self.assertFalse(r["ok"])
        self.assertIn("HTTP", r["error"])
        # 开了内网开关 → 放行
        with mock.patch.dict(os.environ, {**env, "COSMAC_WF_ALLOW_INTERNAL": "1"}), \
             mock.patch.object(wf.requests, "request",
                               return_value=FakeResp(200, {"output": "ok"})):
            r2 = wf.run_connector(conn, "hi")
        self.assertTrue(r2["ok"])

    def test_webhook_refuses_credential_host_mismatch(self) -> None:
        # #1：URL 主机 != 绑定域名 → 拒绝
        conn = {"url": "https://attacker.test/wh", "cred": "n8n_main"}
        with mock.patch.dict(os.environ, {
            "COSMAC_WF_N8N_MAIN": "tok", "COSMAC_WF_N8N_MAIN_HOST": "n8n.mycorp.com",
        }):
            r = wf.run_connector(conn, "hi")
        self.assertFalse(r["ok"])
        self.assertIn("只允许发往", r["error"])

    def test_webhook_non_2xx_is_error(self) -> None:
        conn = {"url": "https://h/wh"}
        with mock.patch.object(wf.requests, "request", return_value=FakeResp(500, text="boom")):
            r = wf.run_connector(conn, "x")
        self.assertFalse(r["ok"])
        self.assertIn("500", r["error"])

    def test_network_error_is_caught(self) -> None:
        conn = {"url": "https://h/wh"}
        with mock.patch.object(wf.requests, "request", side_effect=requests.RequestException("down")):
            r = wf.run_connector(conn, "x")
        self.assertFalse(r["ok"])
        self.assertIn("请求失败", r["error"])

    def test_missing_url(self) -> None:
        r = wf.run_connector({"slug": "x"}, "y")
        self.assertFalse(r["ok"])
        self.assertIn("URL", r["error"])

    def test_non_json_response_uses_text(self) -> None:
        conn = {"url": "https://h/wh"}
        with mock.patch.object(wf.requests, "request", return_value=FakeResp(200, None, text="纯文本结果")):
            r = wf.run_connector(conn, "x")
        self.assertTrue(r["ok"])
        self.assertEqual(r["output"], "纯文本结果")

    def test_unknown_platform(self) -> None:
        r = wf.run_connector({"url": "u", "platform": "zapier"}, "x")
        self.assertFalse(r["ok"])
        self.assertIn("暂不支持", r["error"])

    # —— Dify ——
    def test_dify_workflow_success(self) -> None:
        conn = {"platform": "dify", "url": "https://api.dify.ai", "cred": "d", "mode": "workflow"}
        with mock.patch.dict(os.environ, {"COSMAC_WF_D": "k", "COSMAC_WF_D_HOST": "api.dify.ai"}), \
             mock.patch.object(wf.requests, "request",
                               return_value=FakeResp(200, {"data": {"outputs": {"text": "结果X"}}})) as m:
            r = wf.run_connector(conn, "做封面")
        self.assertTrue(r["ok"])
        self.assertEqual(r["output"], "结果X")
        _, kw = m.call_args
        self.assertEqual(kw["json"]["inputs"]["input"], "做封面")
        self.assertEqual(kw["headers"]["Authorization"], "Bearer k")

    def test_dify_chat_mode(self) -> None:
        conn = {"platform": "dify", "cred": "d", "mode": "chat"}
        with mock.patch.dict(os.environ, {"COSMAC_WF_D": "k", "COSMAC_WF_D_HOST": "api.dify.ai"}), \
             mock.patch.object(wf.requests, "request", return_value=FakeResp(200, {"answer": "答X"})) as m:
            r = wf.run_connector(conn, "问题")
        self.assertEqual(r["output"], "答X")
        # _fetch 走 requests.request(method, url, ...)：url 是第 2 个位置参数
        self.assertTrue(m.call_args[0][1].endswith("/v1/chat-messages"))

    def test_dify_no_cred(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("COSMAC_WF_D", None)
            r = wf.run_connector({"platform": "dify", "cred": "d"}, "x")
        self.assertFalse(r["ok"])
        self.assertIn("凭据", r["error"])

    # —— Coze ——
    def test_coze_success(self) -> None:
        conn = {"platform": "coze", "cred": "c", "ref_id": "wf123"}
        with mock.patch.dict(os.environ, {"COSMAC_WF_C": "tok", "COSMAC_WF_C_HOST": "api.coze.cn"}), \
             mock.patch.object(wf.requests, "request",
                               return_value=FakeResp(200, {"code": 0, "data": "结果Y"})) as m:
            r = wf.run_connector(conn, "跑")
        self.assertTrue(r["ok"])
        self.assertEqual(r["output"], "结果Y")
        self.assertEqual(m.call_args[1]["json"]["workflow_id"], "wf123")

    def test_coze_needs_workflow_id(self) -> None:
        with mock.patch.dict(os.environ, {"COSMAC_WF_C": "tok", "COSMAC_WF_C_HOST": "api.coze.cn"}):
            r = wf.run_connector({"platform": "coze", "cred": "c"}, "x")
        self.assertFalse(r["ok"])
        self.assertIn("workflow_id", r["error"])

    def test_coze_business_error(self) -> None:
        conn = {"platform": "coze", "cred": "c", "ref_id": "w"}
        with mock.patch.dict(os.environ, {"COSMAC_WF_C": "tok", "COSMAC_WF_C_HOST": "api.coze.cn"}), \
             mock.patch.object(wf.requests, "request",
                               return_value=FakeResp(200, {"code": 700, "msg": "参数错"})):
            r = wf.run_connector(conn, "x")
        self.assertFalse(r["ok"])
        self.assertIn("参数错", r["error"])

    # —— ComfyUI ——
    def test_comfyui_full_flow(self) -> None:
        conn = {"platform": "comfyui", "url": "http://comfy:8188",
                "graph": '{"6":{"inputs":{"text":"{{input}}"}}}'}

        def fake_request(method, url, **kw):
            # _fetch 统一走 requests.request(method, url, ...)：按方法/路径分派假响应
            if method == "POST":  # 提交
                return FakeResp(200, {"prompt_id": "p1"})
            if "/history/" in url:
                return FakeResp(200, {"p1": {"outputs": {"9": {"images": [
                    {"filename": "out.png", "subfolder": "", "type": "output"}]}}}})
            return FakeResp(200, content=b"PNGDATA")  # /view

        client = FakeMxClient()
        with mock.patch.object(wf.requests, "request", side_effect=fake_request), \
             mock.patch.object(wf.time, "sleep", lambda *_a, **_k: None):
            r = wf.run_connector(conn, "画只猫", client=client, room_id="!r:h")
        self.assertTrue(r["ok"], r.get("error"))
        self.assertEqual(client.uploads, 1)
        self.assertEqual(client.sends, 1)
        self.assertIn("已生成", r["output"])

    def test_comfyui_needs_room(self) -> None:
        r = wf.run_connector({"platform": "comfyui", "url": "u", "graph": "{}"}, "x")
        self.assertFalse(r["ok"])
        self.assertIn("群里触发", r["error"])

    def test_comfyui_bad_graph(self) -> None:
        r = wf.run_connector(
            {"platform": "comfyui", "url": "http://c", "graph": "{not json"},
            "x", client=FakeMxClient(), room_id="!r:h",
        )
        self.assertFalse(r["ok"])
        self.assertIn("JSON", r["error"])


class TestSsrfGuard(unittest.TestCase):
    """SSRF 防护：check_outbound_url 必须挡住内网/环回/云元数据。"""

    def test_blocks_loopback_and_metadata(self) -> None:
        for url in (
            "http://127.0.0.1/x",
            "http://localhost/x",
            "http://169.254.169.254/latest/meta-data/",  # 云 metadata
            "http://[::1]/x",
        ):
            self.assertNotEqual(wf.check_outbound_url(url), "", f"应拒绝 {url}")

    def test_blocks_private_ranges(self) -> None:
        for url in ("http://10.0.0.5/x", "http://192.168.1.1/x", "http://172.16.0.1/x"):
            self.assertNotEqual(wf.check_outbound_url(url), "", f"应拒绝 {url}")

    def test_rejects_non_http_scheme(self) -> None:
        self.assertNotEqual(wf.check_outbound_url("file:///etc/passwd"), "")
        self.assertNotEqual(wf.check_outbound_url("gopher://x/"), "")

    def test_allows_public_ip(self) -> None:
        # 公网 IP 直接放行（不依赖外部 DNS）
        self.assertEqual(wf.check_outbound_url("https://1.1.1.1/x"), "")

    def test_allow_internal_env_opens_private(self) -> None:
        with mock.patch.dict(os.environ, {"COSMAC_WF_ALLOW_INTERNAL": "1"}):
            self.assertEqual(wf.check_outbound_url("http://192.168.1.1/x"), "")
        # 但链路本地(云元数据)即便放开内网也**永远**拒绝
        with mock.patch.dict(os.environ, {"COSMAC_WF_ALLOW_INTERNAL": "1"}):
            self.assertNotEqual(wf.check_outbound_url("http://169.254.169.254/"), "")


if __name__ == "__main__":
    unittest.main()
