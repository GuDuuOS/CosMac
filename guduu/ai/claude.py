"""Claude (Anthropic) 模型后端。

用官方 anthropic SDK 调用 Claude。API key 不写在代码里 ——
SDK 自动从环境变量 ANTHROPIC_API_KEY 读取（部署到服务器时配进去即可）。

默认用最强的 claude-opus-4-8，并开启 adaptive thinking（让模型自己决定思考深度），
系统提示用 prompt caching 缓存，降低重复请求的成本与延迟。
"""

from __future__ import annotations

import logging
from typing import List

from guduu.ai.base import LLMProvider, Message

logger = logging.getLogger("guduu.ai.claude")

# 默认模型：Claude Opus 4.8（最强；如需更便宜可在配置里换成 claude-sonnet-4-6）
DEFAULT_CLAUDE_MODEL = "claude-opus-4-8"


class ClaudeProvider(LLMProvider):
    """调用 Anthropic Claude 的后端实现。"""

    name = "claude"

    def __init__(self, model: str = "", system_prompt: str = ""):
        # 延迟导入：只有真正用 Claude 时才依赖 anthropic 包
        from anthropic import Anthropic

        self.model = model or DEFAULT_CLAUDE_MODEL
        self.system_prompt = system_prompt
        # Anthropic() 会自动从环境变量 ANTHROPIC_API_KEY 取 key
        self._client = Anthropic()

    def complete(self, messages: List[Message]) -> str:
        # 把消息分成两类：system 单独传，user/assistant 放进 messages。
        # （Claude 的 API 要求 system 提示作为独立参数，而非混在对话里。）
        system_chunks: List[str] = []
        if self.system_prompt:
            system_chunks.append(self.system_prompt)

        convo = []
        for msg in messages:
            if msg.role == "system":
                system_chunks.append(msg.content)
            else:
                # 角色只允许 user / assistant
                role = "assistant" if msg.role == "assistant" else "user"
                convo.append({"role": role, "content": msg.content})

        # system 提示做成可缓存的块（内容稳定，命中缓存可省钱省时）
        system_param = [
            {
                "type": "text",
                "text": "\n\n".join(system_chunks),
                "cache_control": {"type": "ephemeral"},
            }
        ] if system_chunks else None

        resp = self._client.messages.create(
            model=self.model,
            max_tokens=4096,
            thinking={"type": "adaptive"},  # 让模型自适应决定要不要思考
            system=system_param,
            messages=convo,
        )

        # 响应是内容块列表，只取文本块拼起来（thinking 块默认无文本，忽略）
        parts = [block.text for block in resp.content if block.type == "text"]
        return "".join(parts).strip()
