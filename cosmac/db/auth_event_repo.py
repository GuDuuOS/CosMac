"""认证审计事件的读写（登录/注册/找回的每次尝试）——安全增强阶段0。

写：`record()` 在登录/注册/找回收口后的后端逐次调用（best-effort，绝不因记日志失败影响主流程）。
读：`recent_by_subject()` / `recent_success_ips()` 供后续「异地登录检测」判断"这个 IP 以前见过没"。
只存判定所需最小字段，**绝不**写密码/验证码/token（见 AuthEvent 模型注释）。
"""

from __future__ import annotations

from typing import List

from sqlalchemy import select

from cosmac.db.models import AuthEvent


def record(
    session, *, kind: str, subject: str = "", ip: str = "", ok: bool = False,
    detail: str = "",
) -> None:
    """记一条认证事件。subject 统一小写（username localpart 或邮箱），便于按主体聚合。"""
    session.add(AuthEvent(
        kind=(kind or "").strip()[:16],
        subject=(subject or "").strip().lower()[:320],
        ip=(ip or "").strip()[:64],
        ok=bool(ok),
        detail=(detail or "").strip()[:128],
    ))


def recent_by_subject(session, subject: str, limit: int = 20) -> List[AuthEvent]:
    """按主体取最近 N 条事件（最新在前）。给异地检测/风控读历史用。"""
    subject = (subject or "").strip().lower()
    if not subject:
        return []
    rows = session.execute(
        select(AuthEvent)
        .where(AuthEvent.subject == subject)
        .order_by(AuthEvent.id.desc())
        .limit(max(1, min(limit, 200)))
    ).scalars().all()
    return list(rows)


def recent_success_ips(session, subject: str, limit: int = 50) -> List[str]:
    """某主体最近**成功登录**用过的 IP 去重列表——异地检测的核心：本次 IP 不在其中=可疑。"""
    subject = (subject or "").strip().lower()
    if not subject:
        return []
    rows = session.execute(
        select(AuthEvent.ip)
        .where(AuthEvent.subject == subject, AuthEvent.kind == "login", AuthEvent.ok.is_(True))
        .order_by(AuthEvent.id.desc())
        .limit(max(1, min(limit, 500)))
    ).scalars().all()
    seen: List[str] = []
    for ip in rows:
        if ip and ip not in seen:
            seen.append(ip)
    return seen
