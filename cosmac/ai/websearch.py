"""联网搜索（web search）抽象 —— 给主 AI 一个"会上网查"的工具。

与大模型/嵌入一样**可插拔、无 key 自动降级**（延续项目一贯做法）：
- 配了搜索服务 key（Tavily / Brave）→ 真联网检索，返回标题+链接+摘要。
- 没配 key → 降级成 ``DisabledSearcher``（available=False），工具会明确告诉模型
  "联网搜索未配置"，绝不报错、不阻断对话。

为什么做成抽象：搜索服务商各有各的 API 形状，业务层不该散落某一家的细节。新增一家
（Bing/SerpAPI 等）只需加一个 ``WebSearcher`` 子类 + 在 ``get_searcher`` 里挂上。

环境变量（COSMAC_ 优先、兼容旧 GUDUU_）：
    COSMAC_SEARCH_PROVIDER   —— tavily（默认） / brave
    COSMAC_SEARCH_API_KEY    —— 通用 key（也认各家专用：TAVILY_API_KEY / BRAVE_API_KEY）
    COSMAC_SEARCH_TIMEOUT    —— 单次请求超时秒数（默认 10，最低 3）
"""

from __future__ import annotations

import logging
import os
from typing import Dict, List

logger = logging.getLogger("cosmac.ai.websearch")


def _env(*names: str) -> str:
    """按顺序取第一个非空环境变量（COSMAC_ 优先、兼容旧 GUDUU_）。"""
    for n in names:
        v = os.environ.get(n)
        if v:
            return v
    return ""


def _timeout() -> float:
    """单次搜索请求超时（秒）。默认 10，最低 3，非法值回退默认——别让搜索拖死 Agent/事务。"""
    try:
        return max(3.0, float(os.environ.get("COSMAC_SEARCH_TIMEOUT", "10")))
    except (TypeError, ValueError):
        return 10.0


class WebSearcher:
    """联网搜索器接口。子类实现 :meth:`search`；``available`` 标记是否真能用。"""

    name = "base"
    available = False

    def search(self, query: str, k: int = 5) -> List[Dict[str, str]]:
        """返回 [{title, url, snippet}, ...]。任何错误都返回 []（不抛出，不拖垮对话）。"""
        return []


class DisabledSearcher(WebSearcher):
    """没配 key 时的占位：永远不可用、搜不出东西。"""

    name = "disabled"
    available = False


class TavilySearcher(WebSearcher):
    """Tavily Search API —— 专为 LLM Agent 设计，返回干净的摘要，最省事的默认选择。"""

    name = "tavily"
    available = True
    _ENDPOINT = "https://api.tavily.com/search"

    def __init__(self, api_key: str):
        self._key = api_key

    def search(self, query: str, k: int = 5) -> List[Dict[str, str]]:
        import requests  # 延迟导入：没装 requests 也不影响降级路径

        try:
            resp = requests.post(
                self._ENDPOINT,
                json={
                    "api_key": self._key,
                    "query": query,
                    "max_results": max(1, min(10, k)),
                    "search_depth": "basic",
                },
                timeout=_timeout(),
            )
            if resp.status_code != 200:
                logger.warning("Tavily 搜索 HTTP %s", resp.status_code)
                return []
            data = resp.json()
        except Exception as e:  # 网络/解析错误：搜不到就搜不到，绝不让 Agent 崩
            logger.warning("Tavily 搜索异常：%s", e)
            return []
        out: List[Dict[str, str]] = []
        for r in (data.get("results") or [])[:k]:
            if not isinstance(r, dict):
                continue
            out.append({
                "title": str(r.get("title") or "").strip(),
                "url": str(r.get("url") or "").strip(),
                "snippet": str(r.get("content") or "").strip(),
            })
        return out


class BraveSearcher(WebSearcher):
    """Brave Search API —— 独立索引、隐私友好；走 X-Subscription-Token 头鉴权。"""

    name = "brave"
    available = True
    _ENDPOINT = "https://api.search.brave.com/res/v1/web/search"

    def __init__(self, api_key: str):
        self._key = api_key

    def search(self, query: str, k: int = 5) -> List[Dict[str, str]]:
        import requests

        try:
            resp = requests.get(
                self._ENDPOINT,
                params={"q": query, "count": max(1, min(10, k))},
                headers={
                    "X-Subscription-Token": self._key,
                    "Accept": "application/json",
                },
                timeout=_timeout(),
            )
            if resp.status_code != 200:
                logger.warning("Brave 搜索 HTTP %s", resp.status_code)
                return []
            data = resp.json()
        except Exception as e:
            logger.warning("Brave 搜索异常：%s", e)
            return []
        results = ((data.get("web") or {}).get("results")) or []
        out: List[Dict[str, str]] = []
        for r in results[:k]:
            if not isinstance(r, dict):
                continue
            out.append({
                "title": str(r.get("title") or "").strip(),
                "url": str(r.get("url") or "").strip(),
                "snippet": str(r.get("description") or "").strip(),
            })
        return out


def get_searcher() -> WebSearcher:
    """按环境挑搜索器：**显式配了搜索 key** 才联网，否则降级 Disabled（工具会说"未配置"）。

    provider 决定用哪家；key 先认通用 COSMAC_SEARCH_API_KEY，再认各家专用 key。
    构造失败（如没装 requests）也降级 Disabled，绝不让"会查"的能力反过来拖垮对话。
    """
    provider = (_env("COSMAC_SEARCH_PROVIDER") or "tavily").strip().lower()
    if provider == "brave":
        key = _env("COSMAC_SEARCH_API_KEY", "BRAVE_API_KEY")
        if not key:
            return DisabledSearcher()
        try:
            return BraveSearcher(key)
        except Exception:
            return DisabledSearcher()
    # 默认 tavily
    key = _env("COSMAC_SEARCH_API_KEY", "TAVILY_API_KEY")
    if not key:
        return DisabledSearcher()
    try:
        return TavilySearcher(key)
    except Exception:
        return DisabledSearcher()
