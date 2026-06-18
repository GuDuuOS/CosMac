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

# 注入主 AI 的技能提示**总长度**上限：即便单条已限长，启用的技能多了也会撑爆上下文，
# 这里再兜一层——超预算就停止注入剩余技能并给出提示（不静默截断）。
MAX_TOTAL_PROMPT_CHARS = 6000


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

    总长度有上限（MAX_TOTAL_PROMPT_CHARS）：超预算就停止注入剩余技能、附一句提示，
    避免技能一多就把模型上下文/费用撑爆。
    """
    if not skills:
        return ""
    header = "你已装载以下技能，按需运用："
    lines = [header]
    total = len(header)
    used = 0
    for sk in skills:
        title = sk.name or sk.slug
        head = f"## 技能：{title}"
        if sk.description:
            head += f"（{sk.description}）"
        block = head + (f"\n{sk.instructions}" if sk.instructions else "")
        if total + len(block) + 1 > MAX_TOTAL_PROMPT_CHARS and used > 0:
            lines.append(f"（另有 {len(skills) - used} 个技能因超出长度预算未注入）")
            break
        lines.append(block)
        total += len(block) + 1
        used += 1
    return "\n".join(lines)


def effective_skill_prompt(
    session: Session, *, room_id: str = "", user_id: str = ""
) -> str:
    """便捷组合：算出生效技能并渲染成提示文本（bot 直接用这个）。"""
    return render_skill_prompt(
        effective_skills(session, room_id=room_id, user_id=user_id)
    )
