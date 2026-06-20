"""文本嵌入（embedding）抽象 —— 把文本转成向量，供知识库做语义检索。

与大模型一样**可插拔、可降级**：
- 有 OpenAI 兼容的 embedding key（``OPENAI_API_KEY`` / 方舟 ``ARK_API_KEY``）→ 用真嵌入
  （默认 ``text-embedding-3-small``），语义检索效果好。
- 没有 key → 自动降级到 **HashingEmbedder**（哈希词袋向量，确定性、零依赖、给词法相似度）。
  这样本地开发/测试零基建即可跑，延续项目「无 key 自动降级」的一贯做法。

接口很小：``Embedder.embed(texts) -> list[list[float]]``，返回 **L2 归一化** 后的向量，
所以检索侧只需点积即得余弦相似度。
"""

from __future__ import annotations

import hashlib
import math
import os
import re
from typing import List, Optional, Sequence


def _l2_normalize(vec: List[float]) -> List[float]:
    """把向量归一化到单位长度（全零则原样返回，避免除零）。"""
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0:
        return vec
    return [x / norm for x in vec]


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """两个向量的余弦相似度。约定传入的已 L2 归一化，但这里仍按通式算、稳妥。"""
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    dot = sum(a[i] * b[i] for i in range(n))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class Embedder:
    """嵌入器接口。"""

    name = "base"
    dim = 0

    @property
    def tag(self) -> str:
        """**向量空间标识**：不同 (provider/模型/维度) 产出的向量绝不能混在一起比相似度。
        入库时把它和向量一起存，检索时只比同 tag 的分块——避免换 embedder 后旧向量污染检索。
        """
        return self.name

    def embed(self, texts: List[str]) -> List[List[float]]:
        raise NotImplementedError

    def embed_one(self, text: str) -> List[float]:
        return self.embed([text])[0]


# 中文按字、英文/数字按词来切 token——给哈希词袋用。
_TOKEN_RE = re.compile(r"[a-zA-Z0-9]+|[一-鿿]")


class HashingEmbedder(Embedder):
    """零依赖的哈希词袋嵌入：把 token 哈希进固定维度并计数，再 L2 归一化。

    不是语义模型，但能给**词法重合度**——没配 embedding key 时的可用兜底，
    且**确定性**（同输入恒同输出），方便测试。
    """

    name = "hashing"

    def __init__(self, dim: int = 256):
        self.dim = dim

    @property
    def tag(self) -> str:
        return f"hash:{self.dim}"

    def _tokens(self, text: str) -> List[str]:
        toks = _TOKEN_RE.findall((text or "").lower())
        # 中文相邻字再组个 bigram，增强短语区分度
        bigrams = [toks[i] + toks[i + 1] for i in range(len(toks) - 1)]
        return toks + bigrams

    def embed(self, texts: List[str]) -> List[List[float]]:
        out: List[List[float]] = []
        for t in texts:
            vec = [0.0] * self.dim
            for tok in self._tokens(t):
                h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
                vec[h % self.dim] += 1.0
            out.append(_l2_normalize(vec))
        return out


class OpenAICompatEmbedder(Embedder):
    """走 OpenAI 兼容 embeddings 接口（OpenAI 官方 / 方舟等）。"""

    name = "openai"

    def __init__(self, api_key: str, model: str, base_url: Optional[str] = None):
        # 延迟导入：没装 openai 也不影响 HashingEmbedder 路径
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)
        self.model = model
        self.base_url = base_url

    @property
    def tag(self) -> str:
        # 端点 + 模型一起标识向量空间（同模型不同端点也算不同空间，稳妥）
        return f"oai:{self.base_url or 'openai'}:{self.model}"

    def embed(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        resp = self._client.embeddings.create(model=self.model, input=texts)
        # 真嵌入一般已接近单位长度，这里仍归一化，保证检索侧点积=余弦
        return [_l2_normalize(list(d.embedding)) for d in resp.data]


def _env(*names: str) -> str:
    """按顺序取第一个非空环境变量（COSMAC_ 优先、兼容旧 GUDUU_）。"""
    for n in names:
        v = os.environ.get(n)
        if v:
            return v
    return ""


# 方舟（火山引擎）OpenAI 兼容端点默认地址——给"误配 ark key 没给 base_url"兜底用。
_DEFAULT_ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"


def get_embedder() -> Embedder:
    """按环境挑嵌入器：**显式配了嵌入 key** 才用真嵌入，否则降级哈希词袋。

    认这些环境变量：
        COSMAC_EMBED_API_KEY  —— 专用嵌入 key（配它时建议同时给 MODEL/BASE_URL）
        OPENAI_API_KEY        —— 用 OpenAI 官方嵌入（默认 text-embedding-3-small 就是它家的）
        COSMAC_EMBED_MODEL    —— 模型（默认 text-embedding-3-small）
        COSMAC_EMBED_BASE_URL —— OpenAI 兼容端点（如方舟/自建）

    **故意不挪用 ``ARK_API_KEY``**：它是给 LLM(deepseek/方舟) 用的，方舟的嵌入是另一套
    模型 id（不存在 text-embedding-3-small），自动拿来当嵌入只会报错、拖垮知识库。
    要在方舟上做嵌入，请显式配 COSMAC_EMBED_API_KEY + COSMAC_EMBED_BASE_URL + COSMAC_EMBED_MODEL。
    """
    key = _env("COSMAC_EMBED_API_KEY", "OPENAI_API_KEY")
    if not key:
        return HashingEmbedder()
    model = _env("COSMAC_EMBED_MODEL") or "text-embedding-3-small"
    base_url = _env("COSMAC_EMBED_BASE_URL") or None
    # #1 安全兜底：若有人把方舟 key（形如 ark-…）配进 EMBED key 却没给 base_url，
    # 默认 base_url=None → OpenAI 客户端会连 api.openai.com，等于把方舟 key 送给 OpenAI。
    # 这里强制指向方舟端点，绝不把 ark 开头的 key 发去 OpenAI。
    if base_url is None and key.startswith("ark-"):
        base_url = _DEFAULT_ARK_BASE_URL
    try:
        return OpenAICompatEmbedder(api_key=key, model=model, base_url=base_url)
    except Exception:
        # openai 没装/初始化失败 → 别让知识库瘫，降级哈希
        return HashingEmbedder()
