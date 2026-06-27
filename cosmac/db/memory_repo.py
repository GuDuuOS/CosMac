"""群级长期记忆的数据访问（模块2增强④）。

只负责读/写 :class:`ConversationMemory` 这一份滚动摘要：
- 每轮回复读 :func:`get_summary` 注入 system（让 AI"记得"）。
- 每轮回复 :func:`bump_and_check` 推进计数器，到阈值就返回 due=True，让 bot 后台重摘要。
- 后台摘要完成后 :func:`save_summary` 覆盖写回。

摘要本身由 LLM 在 bot 侧算（这里不碰模型），保持数据层纯粹。
"""

from __future__ import annotations

from typing import Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from cosmac.db.models import SCOPE_ROOM, ConversationMemory

# 摘要文本入库上限（控 token、防异常超长）
_MAX_SUMMARY = 4000


def _get_or_create(session: Session, scope: str, scope_id: str) -> ConversationMemory:
    """取该作用域的记忆行，没有就建一条空的。"""
    row = session.scalars(
        select(ConversationMemory).where(
            ConversationMemory.scope == scope,
            ConversationMemory.scope_id == scope_id,
        ).limit(1)
    ).first()
    if row is None:
        row = ConversationMemory(scope=scope, scope_id=scope_id, summary="")
        session.add(row)
        session.flush()
    return row


def get_summary(session: Session, scope: str = SCOPE_ROOM, scope_id: str = "") -> str:
    """读当前生效的长期记忆摘要；无则返回空串。只读、不建行。"""
    sid = (scope_id or "").strip()
    if not sid:
        return ""
    row = session.scalars(
        select(ConversationMemory).where(
            ConversationMemory.scope == scope,
            ConversationMemory.scope_id == sid,
        ).limit(1)
    ).first()
    return (row.summary if row else "") or ""


def bump_and_check(
    session: Session, scope: str, scope_id: str, threshold: int
) -> Tuple[bool, str]:
    """推进一轮计数，返回 (是否该重摘要, 当前已有摘要)。

    到阈值时**当场清零** ``turns_since_summary``（原子在本事务里）——这样并发的多轮回复
    里只有跨过阈值的那一轮拿到 due=True，不会重复触发后台摘要。返回的旧摘要给摘要提示用。
    """
    sid = (scope_id or "").strip()
    if not sid:
        return (False, "")
    row = _get_or_create(session, scope, sid)
    row.turns_since_summary = (row.turns_since_summary or 0) + 1
    row.total_turns = (row.total_turns or 0) + 1
    prior = row.summary or ""
    if threshold > 0 and row.turns_since_summary >= threshold:
        row.turns_since_summary = 0  # 立刻清零，避免并发重复触发
        session.flush()
        return (True, prior)
    session.flush()
    return (False, prior)


def clear_summary(session: Session, scope: str, scope_id: str) -> int:
    """删除该作用域的长期记忆行（专班归档收尾用）。

    专班所有任务完成、成果已存进归档记录后，频道的滚动摘要就没必要再占着——
    清掉它，「不浪费 Agent 记忆」。返回删掉的行数（0 或 1）。
    """
    sid = (scope_id or "").strip()
    if not sid:
        return 0
    row = session.scalars(
        select(ConversationMemory).where(
            ConversationMemory.scope == scope,
            ConversationMemory.scope_id == sid,
        ).limit(1)
    ).first()
    if row is None:
        return 0
    session.delete(row)
    session.flush()
    return 1


def save_summary(
    session: Session, scope: str, scope_id: str, summary: str
) -> None:
    """后台摘要完成后覆盖写回当前摘要（截断到上限）。空摘要不覆盖（保留旧的）。"""
    sid = (scope_id or "").strip()
    text = (summary or "").strip()
    if not sid or not text:
        return
    row = _get_or_create(session, scope, sid)
    row.summary = text[:_MAX_SUMMARY]
    session.flush()
