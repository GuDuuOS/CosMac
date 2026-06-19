"""provider 选择 + EchoProvider 的基础单元测试。

不依赖运行中的 Synapse，也不需要任何 API key，纯逻辑验证，跑得快。
运行：.venv/bin/python -m unittest cosmac.tests.test_echo_provider
"""

from __future__ import annotations

import os
import unittest
from dataclasses import replace

from cosmac.ai import Message, get_provider
from cosmac.ai.echo import EchoProvider
from cosmac.config import CosmacConfig


class TestEchoProvider(unittest.TestCase):
    def test_get_provider_echo(self) -> None:
        # provider=echo 时拿到 EchoProvider
        cfg = replace(CosmacConfig(), llm_provider="echo")
        self.assertIsInstance(get_provider(cfg), EchoProvider)

    def test_unknown_provider_raises(self) -> None:
        cfg = replace(CosmacConfig(), llm_provider="不存在的模型")
        with self.assertRaises(ValueError):
            get_provider(cfg)

    def test_claude_without_key_falls_back_to_echo(self) -> None:
        # 没配 ANTHROPIC_API_KEY 时，claude 应优雅降级为 echo（保证 bot 能跑）
        cfg = replace(CosmacConfig(), llm_provider="claude")
        saved = os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            self.assertIsInstance(get_provider(cfg), EchoProvider)
        finally:
            if saved is not None:
                os.environ["ANTHROPIC_API_KEY"] = saved

    def test_openai_without_key_falls_back_to_echo(self) -> None:
        cfg = replace(CosmacConfig(), llm_provider="openai")
        saved = os.environ.pop("OPENAI_API_KEY", None)
        try:
            self.assertIsInstance(get_provider(cfg), EchoProvider)
        finally:
            if saved is not None:
                os.environ["OPENAI_API_KEY"] = saved

    def test_echo_contains_user_text(self) -> None:
        # 回复里应包含用户原话，证明"看到了并能复述"
        reply = EchoProvider().complete([Message(role="user", content="你好世界")])
        self.assertIn("你好世界", reply)


if __name__ == "__main__":
    unittest.main()
