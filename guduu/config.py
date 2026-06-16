"""CosMac Star 运行配置。

集中管理所有可配置项（连哪个 Synapse、用哪些 token、bot 监听哪里、用哪个 AI 模型）。
所有值都可以用环境变量覆盖，方便在不同环境（本地/测试/生产）切换，
不把任何密钥硬编码散落到业务代码里。

开发默认值与 ``run/synapse/guduu-bot.yaml`` 里的 appservice 注册保持一致。
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class GuduuConfig:
    """CosMac Star 主 AI Bot 的全部配置。

    字段说明：
        homeserver_url:  Synapse 的 HTTP 地址，bot 通过它发消息/加入房间。
        server_name:     Synapse 的 server_name（用户 id 的域名部分）。
        bot_user_id:     主 AI 的完整用户 id，例如 @guduu:guduu.local。
        as_token:        appservice token —— bot 调用 Synapse 时用它证明身份。
        hs_token:        homeserver token —— Synapse 推事件给我们时带上它，用于校验来源。
        listen_host/port: bot 自己的 HTTP 服务监听地址（Synapse 往这里推事件）。
        llm_provider:    使用哪个 AI 模型后端（见 guduu.ai）。可选 "echo"/"claude"/"openai"。
        llm_model:       具体模型 id（留空则用各 provider 的默认值）。
        system_prompt:   主 AI 的人设/系统提示（喂给大模型的 system）。
    """

    homeserver_url: str = "http://127.0.0.1:8008"
    server_name: str = "guduu.local"
    bot_user_id: str = "@guduu:guduu.local"

    # —— 与 run/synapse/guduu-bot.yaml 中的值一致（开发用，生产务必更换）——
    as_token: str = "d9b3d04cf7ec509499c725019809ff3a89b391d60bee50708cd3f30fe2e328f8"
    hs_token: str = "6ff1df99b42d8de0839c4789e2a310988cd9d2d0edc5664843142c4f19b7ac8a"

    listen_host: str = "127.0.0.1"
    listen_port: int = 9000

    # AI 模型相关。API key 不放这里，由各 SDK 从环境变量读取
    # （Claude 读 ANTHROPIC_API_KEY，OpenAI 读 OPENAI_API_KEY）。
    llm_provider: str = "echo"
    llm_model: str = ""  # 空 = 用 provider 默认模型
    system_prompt: str = (
        "你是 CosMac Star —— 一个内置在 IM 群聊里的主 AI 助手。"
        "你能看到群里的消息并参与对话。"
        "回答要简洁、友好、直接、有帮助。用提问者使用的语言回复。"
    )
    # 主 AI 在群里显示的名字（用户看到的品牌名；与内部用户 id @guduu 无关）
    bot_displayname: str = "CosMac Star"

    @staticmethod
    def from_env() -> "GuduuConfig":
        """从环境变量读取配置，未设置的项用上面的开发默认值。"""
        defaults = GuduuConfig()
        return GuduuConfig(
            homeserver_url=os.environ.get("GUDUU_HS_URL", defaults.homeserver_url),
            server_name=os.environ.get("GUDUU_SERVER_NAME", defaults.server_name),
            bot_user_id=os.environ.get("GUDUU_BOT_USER_ID", defaults.bot_user_id),
            as_token=os.environ.get("GUDUU_AS_TOKEN", defaults.as_token),
            hs_token=os.environ.get("GUDUU_HS_TOKEN", defaults.hs_token),
            listen_host=os.environ.get("GUDUU_LISTEN_HOST", defaults.listen_host),
            listen_port=int(os.environ.get("GUDUU_LISTEN_PORT", defaults.listen_port)),
            llm_provider=os.environ.get("GUDUU_LLM_PROVIDER", defaults.llm_provider),
            llm_model=os.environ.get("GUDUU_LLM_MODEL", defaults.llm_model),
            system_prompt=os.environ.get("GUDUU_SYSTEM_PROMPT", defaults.system_prompt),
            bot_displayname=os.environ.get(
                "GUDUU_BOT_DISPLAYNAME", defaults.bot_displayname
            ),
        )
