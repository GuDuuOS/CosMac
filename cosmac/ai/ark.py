"""火山引擎 方舟（Ark）模型后端 —— 用于接入 DeepSeek 等。

方舟接口是 OpenAI 兼容的，所以直接复用通用的 `OpenAICompatProvider`，只是把
base_url 指向方舟、api_key 从 ARK_API_KEY 读。key 只走服务端环境变量/Secret
Manager，管理后台**不下发 key**（只选 provider/模型）。

环境变量：
  ARK_API_KEY   方舟 API Key（方舟控制台「API Key 管理」获取）。
  ARK_BASE_URL  可选，默认 https://ark.cn-beijing.volces.com/api/v3
模型 id（COSMAC_LLM_MODEL）：方舟的 Model ID 或推理接入点 Endpoint ID（ep-...）。
"""

from __future__ import annotations

import os

from cosmac.ai.openai_compat import OpenAICompatProvider

# 方舟北京区默认入口；其它区域用 ARK_BASE_URL 覆盖
DEFAULT_ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
# 默认接 DeepSeek；按方舟账号实际 Model ID / Endpoint ID 用 COSMAC_LLM_MODEL 覆盖
DEFAULT_ARK_MODEL = "deepseek-v3.2"


class ArkProvider(OpenAICompatProvider):
    """方舟后端：OpenAICompatProvider + 方舟默认 base_url / 模型 / 从 ARK_API_KEY 取 key。"""

    name = "ark"

    def __init__(self, model: str = "", system_prompt: str = ""):
        super().__init__(
            api_key=os.environ.get("ARK_API_KEY", ""),
            model=model or DEFAULT_ARK_MODEL,
            system_prompt=system_prompt,
            base_url=os.environ.get("ARK_BASE_URL", DEFAULT_ARK_BASE_URL),
        )
