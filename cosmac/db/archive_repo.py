"""专班归档记录的数据访问（AI 任务编排 · 收尾环节）。

专班所有任务节点完成、主 AI 审核通过后，把整盘项目（总目标 + 各任务快照 + 收尾摘要）
落成一条 :class:`ProjectArchive`。归档后该频道的滚动长期记忆可以清掉、提示关闭频道——
项目复盘/审计仍可回查这条记录。一个房间可能多次归档（极少），按 id 倒序取最新一条。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from cosmac.db.models import ProjectArchive

_MAX_SUMMARY = 8000


def create_archive(
    session: Session,
    *,
    room_id: str,
    goal: str = "",
    summary: str = "",
    tasks: Optional[List[Dict[str, Any]]] = None,
    done_count: int = 0,
    total_count: int = 0,
    archived_by: str = "",
) -> ProjectArchive:
    """落一条归档记录。tasks 是任务快照列表（title/status/result/executor 等）。"""
    row = ProjectArchive(
        room_id=(room_id or "")[:255],
        goal=str(goal or "")[:2000],
        summary=str(summary or "")[:_MAX_SUMMARY],
        tasks=list(tasks or []),
        done_count=max(0, int(done_count or 0)),
        total_count=max(0, int(total_count or 0)),
        archived_by=(archived_by or "")[:255],
    )
    session.add(row)
    session.flush()
    return row


def list_archives(
    session: Session,
    *,
    room_ids: Optional[List[str]] = None,
    limit: int = 100,
) -> List[ProjectArchive]:
    """列归档（按 id 倒序，新归档在前）。

    越权防护同 task_repo：传了 room_ids 就只返回这些房间的归档；传空列表返回空；
    None 才返回全部（仅内部/管理员统计用，别拿用户的空作用域来调）。
    """
    stmt = select(ProjectArchive)
    if room_ids is not None:
        if not room_ids:
            return []
        stmt = stmt.where(ProjectArchive.room_id.in_(room_ids))
    return list(
        session.execute(stmt.order_by(ProjectArchive.id.desc()).limit(limit)).scalars().all()
    )
