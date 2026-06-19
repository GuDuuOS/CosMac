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
class CosmacConfig:
    """CosMac Star 主 AI Bot 的全部配置。

    字段说明：
        homeserver_url:  Synapse 的 HTTP 地址，bot 通过它发消息/加入房间。
        server_name:     Synapse 的 server_name（用户 id 的域名部分）。
        bot_user_id:     主 AI 的完整用户 id，例如 @guduu:guduu.local。
        as_token:        appservice token —— bot 调用 Synapse 时用它证明身份。
        hs_token:        homeserver token —— Synapse 推事件给我们时带上它，用于校验来源。
        listen_host/port: bot 自己的 HTTP 服务监听地址（Synapse 往这里推事件）。
        llm_provider:    使用哪个 AI 模型后端（见 cosmac.ai）。可选 "echo"/"claude"/"openai"。
        llm_model:       具体模型 id（留空则用各 provider 的默认值）。
        system_prompt:   主 AI 的人设/系统提示（喂给大模型的 system）。
    """

    homeserver_url: str = "http://127.0.0.1:8008"
    # ⚠️ 这两项是**和线上 bot 账号强耦合**的标识，要改得连同服务器侧迁移一起做（见 stage2 runbook）：
    # 把 @guduu 重注册成 @cosmac、重邀进所有房间、改 registration 的 sender_localpart。
    # 在那之前保持 guduu，否则前端/后端会去找一个不存在的账号、AI 进不了群。
    server_name: str = "guduu.local"
    bot_user_id: str = "@guduu:guduu.local"

    # —— appservice 密钥：绝不硬编码进代码（会随 git 泄露）——
    # 默认空串；真实值由 from_env() 按优先级注入：
    #   1) 环境变量 COSMAC_AS_TOKEN / COSMAC_HS_TOKEN（旧 GUDUU_* 仍兼容；生产用 Secret Manager 注入）
    #   2) appservice 注册文件 run/synapse/guduu-bot.yaml（本地开发用，该文件已 gitignore）
    # 两者都拿不到则保持空串，启动时 require_tokens() 会报错而不是静默用泄露的旧 key。
    as_token: str = ""
    hs_token: str = ""

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

    # —— 运行时 AI 配置（管理后台「AI 配置」用）——
    # 控制室别名：管理后台把 AI 配置写进这个房间的 state event，bot 运行时来读。
    # 留空则在 from_env 里按 server_name 自动推出 #cosmac-ctrl:<server_name>。
    # 读不到（房间不存在/未加入/网络错）一律回退到上面的启动配置，零回归。
    control_room_alias: str = ""

    # —— CosMac Star 自己的数据库（模块2 起：Skill/Agent/知识库/记忆等）——
    # 见 CLAUDE.md §3「数据存储分层」。Synapse 已存的（聊天记录/成员/房间状态）不在这里重存。
    # 留空 = 由 cosmac.db 用默认：生产读环境变量 COSMAC_DATABASE_URL（指向独立 Postgres），
    # 本地开发回退 SQLite 文件 run/cosmac.db（零基建即可跑）。
    database_url: str = ""

    @staticmethod
    def from_env() -> "CosmacConfig":
        """从环境变量读取配置，未设置的项用上面的开发默认值。

        appservice 密钥（as_token/hs_token）特殊处理：环境变量优先；环境变量没给时，
        回退去读 appservice 注册文件（本地开发用，文件已 gitignore，不会泄露）。
        """
        defaults = CosmacConfig()
        # 密钥按优先级解析：环境变量 → 注册文件。两者都空就保持空（启动时报错）。
        reg = _load_registration_tokens()
        as_token = _env("AS_TOKEN") or reg.get("as_token", "")
        hs_token = _env("HS_TOKEN") or reg.get("hs_token", "")
        server_name = _env("SERVER_NAME", defaults.server_name)
        return CosmacConfig(
            homeserver_url=_env("HS_URL", defaults.homeserver_url),
            server_name=server_name,
            bot_user_id=_env("BOT_USER_ID", defaults.bot_user_id),
            as_token=as_token,
            hs_token=hs_token,
            listen_host=_env("LISTEN_HOST", defaults.listen_host),
            listen_port=int(_env("LISTEN_PORT", str(defaults.listen_port))),
            llm_provider=_env("LLM_PROVIDER", defaults.llm_provider),
            llm_model=_env("LLM_MODEL", defaults.llm_model),
            system_prompt=_env("SYSTEM_PROMPT", defaults.system_prompt),
            bot_displayname=_env("BOT_DISPLAYNAME", defaults.bot_displayname),
            control_room_alias=_env(
                "CONTROL_ROOM_ALIAS",
                # 默认按 server_name 推：#cosmac-ctrl:<server_name>
                f"#cosmac-ctrl:{server_name}",
            ),
            # 留空交给 cosmac.db 决定默认（生产 env / 本地 SQLite）
            database_url=_env("DATABASE_URL", defaults.database_url),
        )

    def require_tokens(self) -> None:
        """启动前校验：appservice 密钥必须存在，否则直接报错（而不是带空 token 静默连不上）。

        给出明确指引，避免把泄露的旧 key 当默认值用。生产用环境变量注入，
        本地把密钥放进 run/synapse/guduu-bot.yaml（已 gitignore）。
        """
        missing = [
            name
            for name, val in (("as_token", self.as_token), ("hs_token", self.hs_token))
            if not val
        ]
        if missing:
            raise RuntimeError(
                f"缺少 appservice 密钥 {missing}：请设环境变量 COSMAC_AS_TOKEN/COSMAC_HS_TOKEN，"
                "或在 appservice 注册文件里配置。密钥不再硬编码进代码。"
            )


def _env(suffix: str, default: str = "") -> str:
    """读环境变量：优先新前缀 ``COSMAC_``，回退旧前缀 ``GUDUU_``（向后兼容、不破生产）。

    例：``_env("LLM_PROVIDER")`` 依次查 ``COSMAC_LLM_PROVIDER`` → ``GUDUU_LLM_PROVIDER``。
    迁移期生产 systemd 里旧的 ``GUDUU_*`` 仍生效；改成 ``COSMAC_*`` 后旧的可删。
    """
    return (
        os.environ.get(f"COSMAC_{suffix}")
        or os.environ.get(f"GUDUU_{suffix}")
        or default
    )


# appservice 注册文件路径：默认本机开发布局 run/synapse/guduu-bot.yaml，可用环境变量覆盖。
# （文件名属 stage2 迁移项，连同 bot 账号一起改名；现在保持以匹配本地已有文件。）
_REGISTRATION_YAML = _env(
    "REGISTRATION_YAML",
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "run",
        "synapse",
        "guduu-bot.yaml",
    ),
)


def _load_registration_tokens() -> dict:
    """从 appservice 注册 yaml 读 as_token/hs_token（本地开发回退用）。

    文件不存在/读不出就返回空 dict——交给 require_tokens() 报错。
    解析失败绝不抛异常拖垮启动（环境变量路径仍可用）。
    """
    try:
        import yaml  # synapse 运行环境必带，按需导入避免无谓依赖

        with open(_REGISTRATION_YAML, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return {
            "as_token": str(data.get("as_token", "")),
            "hs_token": str(data.get("hs_token", "")),
        }
    except Exception:
        return {}


# 管理后台写、bot 读的"AI 配置"state event 类型（cosmac.* 命名空间，不与协议 m.* 冲突）
AI_CONFIG_EVENT_TYPE = "cosmac.ai.config"

# 管理后台写「期望的服务器管理员集」、主 AI(bot)据此对齐控制室成员的 state event 类型。
# 浏览器只提交期望（管理员 power=50 够写 state）；真正的"降权/踢出非管理员"由拥有
# power=100 的 bot 执行——因为 Matrix 里同级(50)用户互相无法降权/踢出。
CONTROL_ADMINS_EVENT_TYPE = "cosmac.ctrl.admins"

# 管理后台写、bot 读的「全局技能」state event 类型（存在控制室，应用于所有群）。
# 内容形如 {"skills": [{"slug","name","description","instructions","enabled"}, ...]}。
# 走 Matrix state event 而非 DB，是因为浏览器只能通过 Matrix 跟后端通信、够不到 cosmac
# 的 DB——与 AI 配置同一套路（见 CLAUDE.md §3 数据存储分层）。群级/个人技能仍在 DB
# （聊天命令管理），bot 注入时把两边合并。
SKILLS_EVENT_TYPE = "cosmac.skills"
