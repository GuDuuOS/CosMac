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
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data
        self.text = text

    def json(self):
        if self._json is None:
            raise ValueError("no json")
        return self._json


class TestWfEngine(unittest.TestCase):
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
        with mock.patch.dict(os.environ, {"COSMAC_WF_N8N_MAIN": "tok"}), \
             mock.patch.object(wf.requests, "request", return_value=FakeResp(200, {"result": "ok"})) as m:
            wf.run_connector(conn, "hi")
        _, kwargs = m.call_args
        self.assertEqual(kwargs["headers"].get("Authorization"), "Bearer tok")

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
        r = wf.run_connector({"url": "u", "platform": "comfyui"}, "x")
        self.assertFalse(r["ok"])
        self.assertIn("暂不支持", r["error"])

    # —— Dify ——
    def test_dify_workflow_success(self) -> None:
        conn = {"platform": "dify", "url": "https://api.dify.ai", "cred": "d", "mode": "workflow"}
        with mock.patch.dict(os.environ, {"COSMAC_WF_D": "k"}), \
             mock.patch.object(wf.requests, "post",
                               return_value=FakeResp(200, {"data": {"outputs": {"text": "结果X"}}})) as m:
            r = wf.run_connector(conn, "做封面")
        self.assertTrue(r["ok"])
        self.assertEqual(r["output"], "结果X")
        _, kw = m.call_args
        self.assertEqual(kw["json"]["inputs"]["input"], "做封面")
        self.assertEqual(kw["headers"]["Authorization"], "Bearer k")

    def test_dify_chat_mode(self) -> None:
        conn = {"platform": "dify", "cred": "d", "mode": "chat"}
        with mock.patch.dict(os.environ, {"COSMAC_WF_D": "k"}), \
             mock.patch.object(wf.requests, "post", return_value=FakeResp(200, {"answer": "答X"})) as m:
            r = wf.run_connector(conn, "问题")
        self.assertEqual(r["output"], "答X")
        self.assertTrue(m.call_args[0][0].endswith("/v1/chat-messages"))

    def test_dify_no_cred(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("COSMAC_WF_D", None)
            r = wf.run_connector({"platform": "dify", "cred": "d"}, "x")
        self.assertFalse(r["ok"])
        self.assertIn("凭据", r["error"])

    # —— Coze ——
    def test_coze_success(self) -> None:
        conn = {"platform": "coze", "cred": "c", "ref_id": "wf123"}
        with mock.patch.dict(os.environ, {"COSMAC_WF_C": "tok"}), \
             mock.patch.object(wf.requests, "post",
                               return_value=FakeResp(200, {"code": 0, "data": "结果Y"})) as m:
            r = wf.run_connector(conn, "跑")
        self.assertTrue(r["ok"])
        self.assertEqual(r["output"], "结果Y")
        self.assertEqual(m.call_args[1]["json"]["workflow_id"], "wf123")

    def test_coze_needs_workflow_id(self) -> None:
        with mock.patch.dict(os.environ, {"COSMAC_WF_C": "tok"}):
            r = wf.run_connector({"platform": "coze", "cred": "c"}, "x")
        self.assertFalse(r["ok"])
        self.assertIn("workflow_id", r["error"])

    def test_coze_business_error(self) -> None:
        conn = {"platform": "coze", "cred": "c", "ref_id": "w"}
        with mock.patch.dict(os.environ, {"COSMAC_WF_C": "tok"}), \
             mock.patch.object(wf.requests, "post",
                               return_value=FakeResp(200, {"code": 700, "msg": "参数错"})):
            r = wf.run_connector(conn, "x")
        self.assertFalse(r["ok"])
        self.assertIn("参数错", r["error"])


if __name__ == "__main__":
    unittest.main()
