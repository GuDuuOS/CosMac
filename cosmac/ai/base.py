"""LLM 统一接口定义。

所有 AI 模型后端（Claude / OpenAI / 本地模型 / 占位 echo）都实现同一个
``LLMProvider`` 接口。这样上层"主 AI"逻辑只面向接口编程，
换模型只是换一个实现类，业务代码一行都不用改。
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import List


@dataclass
class Message:
    """一条对话消息。

    role: 角色，约定取值 "system" / "user" / "assistant"，与主流大模型一致。
    content: 文本内容。
    """

    role: str
    content: str


class LLMProvider(abc.ABC):
    """大模型后端的抽象基类。

    具体实现（如 ClaudeProvider）只需实现 ``complete``：
    输入一串对话消息，返回模型生成的回复文本。
    """

    #: 后端名字（用于日志/配置识别），子类覆盖。
    name: str = "base"

    @abc.abstractmethod
    def complete(self, messages: List[Message]) -> str:
        """根据对话历史生成一条回复文本。

        参数:
            messages: 按时间顺序排列的对话消息列表。
        返回:
            模型生成的回复（纯文本）。
        """
        raise NotImplementedError
