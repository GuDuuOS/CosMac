"""工作流运行记录的数据访问（模块3）。

只负责把每次连接器运行落库 + 查最近记录；连接器**定义**不在 DB（走 state event）。
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from datetime import datetime, timedelta

from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import Session

from cosmac.db.models import WorkflowRun

# processing 超过这个时长仍没结清 → 视为上次处理半途崩了，允许后续回调重抢（崩溃恢复，#2）
_STALE_PROCESSING_SECONDS = 300

_MAX_STORE = 4000  # 入库的输入/输出截断，避免超长


def record_run(
    session: Session,
    *,
    slug: str,
    platform: str,
    room_id: str,
    sender: str,
    user_input: str,
    result: Dict[str, Any],
) -> WorkflowRun:
    """把一次运行结果落库，返回记录对象。"""
    run = WorkflowRun(
        slug=slug,
        platform=platform or "webhook",
        room_id=room_id,
        sender=sender,
        input=(user_input or "")[:_MAX_STORE],
        status="ok" if result.get("ok") else "error",
        output=str(result.get("output") or "")[:_MAX_STORE],
        error=str(result.get("error") or "")[:_MAX_STORE],
    )
    session.add(run)
    session.flush()
    return run


def recent_runs(session: Session, *, slug: str = "", limit: int = 10) -> List[WorkflowRun]:
    """查最近的运行记录（可按 slug 过滤），按时间倒序。"""
    stmt = select(WorkflowRun)
    if slug:
        stmt = stmt.where(WorkflowRun.slug == slug)
    stmt = stmt.order_by(WorkflowRun.id.desc()).limit(limit)
    return list(session.scalars(stmt).all())


# —— 异步回调（长任务）——

def create_pending(
    session: Session, *, slug: str, platform: str, room_id: str,
    sender: str, user_input: str, token: str,
) -> WorkflowRun:
    """登记一次"已提交、等平台回调"的运行（status=pending + 一次性 token）。"""
    run = WorkflowRun(
        slug=slug, platform=platform or "webhook", room_id=room_id, sender=sender,
        input=(user_input or "")[:_MAX_STORE], status="pending", token=token,
    )
    session.add(run)
    session.flush()
    return run


def reclaim_orphans(session: Session) -> List[Tuple[int, str, str]]:
    """启动时收口"上次进程遗留的"未完成运行（pending/processing）。

    异步提交/ComfyUI 轮询都跑在**进程内**线程池里，进程重启即全部消失——这些运行再也
    等不到完成、会永久卡在 pending（#2）。单实例部署下，启动瞬间所有 pending/processing
    必是上次的遗孤：标记为 error 并返回 ``(run_id, slug, room_id)`` 列表，供调用方通知用户
    "因重启中断、请重试"。已落库后返回。
    """
    rows = (
        session.execute(
            select(WorkflowRun).where(
                WorkflowRun.status.in_(("pending", "processing"))
            )
        )
        .scalars()
        .all()
    )
    out: List[Tuple[int, str, str]] = []
    for r in rows:
        r.status = "error"
        r.error = "服务重启，运行中断"
        r.token = ""  # 一次性 token 作废
        out.append((r.id, r.slug, r.room_id))
    session.flush()
    return out


def get_run(session: Session, run_id: int) -> "WorkflowRun | None":
    """按 id 取运行记录。"""
    return session.get(WorkflowRun, run_id)


def claim_pending(session: Session, run_id: int) -> bool:
    """**原子地**把一条运行抢占成 processing。抢到返回 True。

    两类可抢（都靠 ``UPDATE...WHERE`` 由 DB 原子保证只有一个成功）：
      - status='pending'：正常并发回调，只有一个能抢到（#3 防重复发）。
      - status='processing' 且 ``updated_at`` 已超 5 分钟：上次处理半途崩了（send 抛异常/
        DB 失败/进程重启），允许重抢（#2 防永久卡在 processing、结果丢失）。
    显式刷新 ``updated_at``（Core update 不触发 ORM 的 onupdate），让刚抢到的不会立刻被重抢。
    """
    cutoff = datetime.utcnow() - timedelta(seconds=_STALE_PROCESSING_SECONDS)
    res = session.execute(
        update(WorkflowRun)
        .where(
            WorkflowRun.id == run_id,
            or_(
                WorkflowRun.status == "pending",
                and_(
                    WorkflowRun.status == "processing",
                    WorkflowRun.updated_at < cutoff,
                ),
            ),
        )
        .values(status="processing", updated_at=datetime.utcnow())
    )
    session.flush()
    return (res.rowcount or 0) == 1


def revert_to_pending(session: Session, run_id: int) -> None:
    """processing → pending（回调发消息失败时回滚，留给平台重试，#6）。"""
    session.execute(
        update(WorkflowRun)
        .where(WorkflowRun.id == run_id, WorkflowRun.status == "processing")
        .values(status="pending")
    )
    session.flush()


def complete_run(
    session: Session, run_id: int, *, output: str = "", error: str = ""
) -> bool:
    """把进行中的运行标记完成（成功填 output，失败填 error），并清空 token。

    对 pending/processing 的记录生效（防回调被重放/重复结算）。完成返回 True。
    """
    run = session.get(WorkflowRun, run_id)
    if run is None or run.status not in ("pending", "processing"):
        return False
    run.status = "error" if error else "ok"
    run.output = (output or "")[:_MAX_STORE]
    run.error = (error or "")[:_MAX_STORE]
    run.token = ""  # 一次性，用过即废
    session.flush()
    return True
