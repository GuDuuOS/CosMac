"""CosMac Star AI 层 —— 主 AI 的大脑 + 多模型抽象。

这里定义统一的 LLM 接口（base.py），并按配置提供具体实现：
  - echo   ：占位回显，用于打通骨架（无需任何 key）
  - claude ：Anthropic Claude（需 ANTHROPIC_API_KEY）
  - openai ：OpenAI GPT（需 OPENAI_API_KEY）

业务代码只依赖统一接口，绝不直接调用某家厂商的 SDK，方便随时切换模型后端。
未装对应 SDK 或未配置 API key 时，会自动优雅降级到 echo，保证 bot 始终能跑。
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from cosmac.ai.base import LLMProvider, Message
from cosmac.ai.echo import EchoProvider

if TYPE_CHECKING:
    from cosmac.config import CosmacConfig

logger = logging.getLogger("cosmac.ai")


def get_provider(config: "CosmacConfig") -> LLMProvider:
    """按配置返回一个 LLM 后端实例。

    根据 config.llm_provider 选择后端；若所需 SDK 缺失或 API key 未配置，
    打印告警并降级为 EchoProvider（保证 bot 不会因为缺 key 而起不来）。
    """
    name = (config.llm_provider or "echo").lower()

    if name == "echo":
        return EchoProvider()

    if name == "claude":
        if not os.environ.get("ANTHROPIC_API_KEY"):
            logger.warning("未设置 ANTHROPIC_API_KEY，主 AI 暂时降级为 echo 占位。")
            return EchoProvider()
        try:
            from cosmac.ai.claude import ClaudeProvider
        except ImportError:
            logger.warning("未安装 anthropic SDK，主 AI 暂时降级为 echo 占位。")
            return EchoProvider()
        return ClaudeProvider(model=config.llm_model, system_prompt=config.system_prompt)

    if name == "openai":
        if not os.environ.get("OPENAI_API_KEY"):
            logger.warning("未设置 OPENAI_API_KEY，主 AI 暂时降级为 echo 占位。")
            return EchoProvider()
        try:
            from cosmac.ai.openai_provider import OpenAIProvider
        except ImportError:
            logger.warning("未安装 openai SDK，主 AI 暂时降级为 echo 占位。")
            return EchoProvider()
        return OpenAIProvider(model=config.llm_model, system_prompt=config.system_prompt)

    raise ValueError(f"未知的 LLM provider: {name!r}（可选 echo/claude/openai）")


__all__ = ["LLMProvider", "Message", "EchoProvider", "get_provider"]
