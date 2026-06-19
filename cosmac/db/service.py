"""把数据层的 Skill/Agent 翻译成「喂给主 AI 的提示」。

这层是 DB 与主 AI 之间的薄胶水：纯函数、好测，不连 Matrix、不碰 bot。
bot 每处理一条消息，按 (房间, 发起人) 算出「当前生效的技能说明」，作为 system
addendum 临时拼进这一轮对话——不改 Agent 的常驻人设。

作用域优先级（后面的更具体、排在更后面，让模型更重视）：
    global（全平台）→ room（本群）→ user（本人）
"""

from __future__ import annotations

from typing import List

from sqlalchemy.orm import Session

from cosmac.db import repo
from cosmac.db.models import SCOPE_GLOBAL, SCOPE_ROOM, SCOPE_USER, Skill

# 单一来源：渲染总长度上限定义在 skills_text，这里 re-export 兼容旧引用（含测试）。
from cosmac.skills_text import MAX_TOTAL_PROMPT_CHARS  # noqa: F401


def effective_skills(
    session: Session, *, room_id: str = "", user_id: str = ""
) -> List[Skill]:
    """汇总在「当前房间 + 发起人」下**启用**的技能。

    顺序：全局 → 本群 → 本人。去重不做（不同作用域可同 slug，语义上各自独立）。
    """
    out: List[Skill] = list(
        repo.list_skills(session, scope=SCOPE_GLOBAL, scope_id="", enabled_only=True)
    )
    if room_id:
        out += repo.list_skills(
            session, scope=SCOPE_ROOM, scope_id=room_id, enabled_only=True
        )
    if user_id:
        out += repo.list_skills(
            session, scope=SCOPE_USER, scope_id=user_id, enabled_only=True
        )
    return out


def render_skill_prompt(skills: List[Skill]) -> str:
    """把若干技能渲染成一段 system 提示文本；没有技能返回空串。

    渲染逻辑（含总长度上限、首条也截断、脏数据不崩）统一走 `skills_text.render_skills`，
    这里只把 ORM Skill 转成它认的字典——避免两份渲染各自实现、各自踩同一个坑。
    """
    from cosmac.skills_text import render_skills

    return render_skills(
        [
            {
                "slug": sk.slug,
                "name": sk.name,
                "description": sk.description,
                "instructions": sk.instructions,
            }
            for sk in skills
        ]
    )


def effective_skill_prompt(
    session: Session, *, room_id: str = "", user_id: str = ""
) -> str:
    """便捷组合：算出生效技能并渲染成提示文本（bot 直接用这个）。"""
    return render_skill_prompt(
        effective_skills(session, room_id=room_id, user_id=user_id)
    )
