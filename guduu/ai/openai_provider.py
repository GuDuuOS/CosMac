"""OpenAI (GPT) 模型后端。

用官方 openai SDK 调用 GPT。API key 不写在代码里 ——
SDK 自动从环境变量 OPENAI_API_KEY 读取（部署到服务器时配进去即可）。

与 ClaudeProvider 实现同一个 LLMProvider 接口，可在配置里随时切换。
"""

from __future__ import annotations

import logging
from typing import List

from guduu.ai.base import LLMProvider, Message

logger = logging.getLogger("guduu.ai.openai")

# 默认模型；可在配置里用 GUDUU_LLM_MODEL 覆盖
DEFAULT_OPENAI_MODEL = "gpt-4o"


class OpenAIProvider(LLMProvider):
    """调用 OpenAI Chat Completions 的后端实现。"""

    name = "openai"

    def __init__(self, model: str = "", system_prompt: str = ""):
        # 延迟导入：只有真正用 OpenAI 时才依赖 openai 包
        from openai import OpenAI

        self.model = model or DEFAULT_OPENAI_MODEL
        self.system_prompt = system_prompt
        # OpenAI() 会自动从环境变量 OPENAI_API_KEY 取 key
        self._client = OpenAI()

    def complete(self, messages: List[Message]) -> str:
        # OpenAI 允许 system 直接放在消息数组开头
        convo = []
        if self.system_prompt:
            convo.append({"role": "system", "content": self.system_prompt})
        for msg in messages:
            convo.append({"role": msg.role, "content": msg.content})

        resp = self._client.chat.completions.create(
            model=self.model,
            messages=convo,
        )
        return (resp.choices[0].message.content or "").strip()
