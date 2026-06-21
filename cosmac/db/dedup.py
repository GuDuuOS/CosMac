"""appservice 事务去重的**持久化 + 原子抢占**（#2/#3）。

为什么不能"先 txn_seen() 再 mark_txn()"：两个并发的同 txn 都会先查到"不存在"，随后各自
标记并各自处理一次——重复触发付费工作流。这里改成**一次原子写决定归属**。

为什么不能"先标记 done 再处理"：DB 标记成功后、事件处理前进程崩溃，Synapse 重试会被当成
"已完成"直接跳过，整批消息永久丢失（明确的 at-most-once 风险）。这里改成两阶段：
先抢占成 processing → 处理 → 标记 done；崩在中间留下的 processing 过期后可被**重新抢占**，
退化为 at-least-once（宁可极端情况下重处理一次，也不永久丢消息）。

供 bot 以"尽力而为"方式调用：DB 不可用时 bot 退回内存去重，不阻断收消息。
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import delete, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from cosmac.db.models import SeenTxn

_RETAIN_DAYS = 7  # 去重记录保留天数（够覆盖任何事务重放窗口）
# processing 超过这么久视为"崩溃残留"，可被重新抢占。
# 取值远大于一次事务处理耗时（处理本身只需秒级——慢的工作流早已丢后台），
# 以免把"正在合法处理中"的事务误判为崩溃而重复处理。
_STALE_SECONDS = 120

# claim_txn 的三种结果
CLAIMED = "claimed"     # 本次抢到处理权，应处理
DONE = "done"           # 已处理完，跳过
INFLIGHT = "inflight"   # 正被另一处理中（未过期），上游应稍后重试


def claim_txn(session: Session, txn_id: str) -> str:
    """**原子**抢占一个事务的处理权（#2/#3）。返回 CLAIMED / DONE / INFLIGHT。

    全程靠"原子 INSERT(主键冲突即让位)"和"带条件的原子 UPDATE(rowcount 判定)"决定归属，
    不存在"查不到→各自插入→重复处理"的竞态。
    """
    now = datetime.utcnow()
    cutoff = now - timedelta(seconds=_STALE_SECONDS)
    # 1) 全新事务：原子 INSERT 抢占。主键冲突 = 已有人，落到 (2)(3) 判断。
    sp = session.begin_nested()  # SAVEPOINT：冲突只回滚这一步，不毁外层事务
    try:
        session.add(SeenTxn(txn_id=txn_id, done=False, claimed_at=now))
        session.flush()
        sp.commit()
        return CLAIMED
    except IntegrityError:
        sp.rollback()
    # 2) 已存在且已完成 → 跳过
    row = session.get(SeenTxn, txn_id)
    if row is not None and row.done:
        return DONE
    # 3) processing 中：仅当 claimed_at 过期（崩溃残留）才原子重新抢占（续约 claimed_at）。
    #    用带条件的 UPDATE + rowcount 保证只有一个并发者抢到。
    res = session.execute(
        update(SeenTxn)
        .where(
            SeenTxn.txn_id == txn_id,
            SeenTxn.done.is_(False),
            SeenTxn.claimed_at < cutoff,
        )
        .values(claimed_at=now)
    )
    session.flush()
    return CLAIMED if res.rowcount == 1 else INFLIGHT


def finish_txn(session: Session, txn_id: str) -> None:
    """处理成功后标记 done（幂等）。崩在处理中途则不会走到这里 → 留 processing 待重抢。"""
    session.execute(
        update(SeenTxn).where(SeenTxn.txn_id == txn_id).values(done=True)
    )
    session.flush()


def prune_old(session: Session) -> None:
    """删掉过期的去重记录，控制表大小。"""
    cutoff = datetime.utcnow() - timedelta(days=_RETAIN_DAYS)
    session.execute(delete(SeenTxn).where(SeenTxn.created_at < cutoff))
    session.flush()
