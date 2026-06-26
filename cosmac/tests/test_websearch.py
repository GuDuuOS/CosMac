"""联网搜索抽象单元测试（mock HTTP，不联网、不需要 key）。

验证：provider 选择、无 key 降级、各家响应解析、错误兜底。
运行：.venv/bin/python -m unittest cosmac.tests.test_websearch
"""

from __future__ import annotations

import os
import unittest
from unittest import mock

from cosmac.ai import websearch
from cosmac.ai.websearch import (
    BraveSearcher,
    DisabledSearcher,
    TavilySearcher,
    get_searcher,
)


class _Resp:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


def _clear_keys() -> None:
    for k in (
        "COSMAC_SEARCH_PROVIDER", "COSMAC_SEARCH_API_KEY",
        "TAVILY_API_KEY", "BRAVE_API_KEY",
    ):
        os.environ.pop(k, None)


class TestGetSearcher(unittest.TestCase):
    def setUp(self) -> None:
        p = mock.patch.dict(os.environ, {}, clear=False)
        p.start()
        self.addCleanup(p.stop)
        _clear_keys()

    def test_no_key_degrades_disabled(self) -> None:
        s = get_searcher()
        self.assertIsInstance(s, DisabledSearcher)
        self.assertFalse(s.available)
        self.assertEqual(s.search("x"), [])  # 降级器搜不出东西

    def test_tavily_when_key_present(self) -> None:
        os.environ["TAVILY_API_KEY"] = "tvly-xxx"
        s = get_searcher()
        self.assertIsInstance(s, TavilySearcher)
        self.assertTrue(s.available)

    def test_brave_when_provider_and_key(self) -> None:
        os.environ["COSMAC_SEARCH_PROVIDER"] = "brave"
        os.environ["BRAVE_API_KEY"] = "brave-xxx"
        self.assertIsInstance(get_searcher(), BraveSearcher)

    def test_brave_without_key_degrades(self) -> None:
        os.environ["COSMAC_SEARCH_PROVIDER"] = "brave"  # 选了 brave 但没给 key
        self.assertIsInstance(get_searcher(), DisabledSearcher)

    def test_generic_key_works_for_provider(self) -> None:
        # 通用 COSMAC_SEARCH_API_KEY 也应被各家认到
        os.environ["COSMAC_SEARCH_API_KEY"] = "generic"
        self.assertIsInstance(get_searcher(), TavilySearcher)


class TestTavilyParsing(unittest.TestCase):
    def test_parses_results(self) -> None:
        payload = {"results": [
            {"title": "标题A", "url": "https://a.com", "content": "摘要A"},
            {"title": "标题B", "url": "https://b.com", "content": "摘要B"},
        ]}
        with mock.patch.object(websearch, "_timeout", return_value=5):
            with mock.patch("requests.post", return_value=_Resp(200, payload)):
                hits = TavilySearcher("k").search("查询", k=5)
        self.assertEqual(len(hits), 2)
        self.assertEqual(hits[0], {"title": "标题A", "url": "https://a.com", "snippet": "摘要A"})

    def test_http_error_returns_empty(self) -> None:
        with mock.patch("requests.post", return_value=_Resp(403, {})):
            self.assertEqual(TavilySearcher("k").search("x"), [])

    def test_network_exception_returns_empty(self) -> None:
        with mock.patch("requests.post", side_effect=RuntimeError("boom")):
            self.assertEqual(TavilySearcher("k").search("x"), [])


class TestBraveParsing(unittest.TestCase):
    def test_parses_results(self) -> None:
        payload = {"web": {"results": [
            {"title": "T", "url": "https://t.com", "description": "desc"},
        ]}}
        with mock.patch("requests.get", return_value=_Resp(200, payload)):
            hits = BraveSearcher("k").search("查询")
        self.assertEqual(hits[0], {"title": "T", "url": "https://t.com", "snippet": "desc"})

    def test_missing_web_key_returns_empty(self) -> None:
        with mock.patch("requests.get", return_value=_Resp(200, {})):
            self.assertEqual(BraveSearcher("k").search("x"), [])


if __name__ == "__main__":
    unittest.main()
