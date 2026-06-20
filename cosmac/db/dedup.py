"""appservice 事务去重的**持久化**（#2）。

内存去重重启即丢，Synapse 重放同一事务会再次触发（含付费工作流）。这里把处理过的
txn id 落库，重启后也能识别并跳过。只保留最近若干天（覆盖任何重放窗口），不无限增长。

全程供 bot 以"尽力而为"方式调用：DB 不可用时 bot 退回内存去重，不阻断收消息。
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.orm import Session

from cosmac.db.models import SeenTxn

_RETAIN_DAYS = 7  # 去重记录保留天数（够覆盖任何事务重放窗口）


def txn_seen(session: Session, txn_id: str) -> bool:
    """该事务 id 是否已持久化记录过（处理过）。"""
    return session.get(SeenTxn, txn_id) is not None


def mark_txn(session: Session, txn_id: str) -> None:
    """记下该事务 id 已处理（幂等）。"""
    if session.get(SeenTxn, txn_id) is None:
        session.add(SeenTxn(txn_id=txn_id))
        session.flush()


def prune_old(session: Session) -> None:
    """删掉过期的去重记录，控制表大小。"""
    cutoff = datetime.utcnow() - timedelta(days=_RETAIN_DAYS)
    session.execute(delete(SeenTxn).where(SeenTxn.created_at < cutoff))
    session.flush()
