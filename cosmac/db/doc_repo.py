"""文档教学频道（类云文档）的数据访问。

一个文档频道(room_id) = 一棵可多层嵌套的页面树。这里只管"页面"的增删改查与排序/移动；
权限（读=房间成员、写=房间 power≥50）在 bot HTTP 端点那层服务端强制，不在这判。

设计取舍（单实例「够用即止」，同 task_repo 口径）：
  · 树不在 DB 里递归查，一次性把某房间所有页面捞出来，在 Python 里拼成树——单房间页面数
    量级很小（几十~几百），简单可靠，避免 SQL 递归 CTE 的跨库（SQLite/PG）差异。
  · 删除采用**级联删子树**（删一页连同其所有后代），符合云文档直觉。
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from cosmac.db.models import DocPage

_MAX_TITLE = 500
_MAX_CONTENT = 200_000   # 单页正文上限（~200KB，防异常超大写入）
_MAX_PAGES_PER_ROOM = 1000  # 单频道页面数量上限，防失控


def list_pages(session: Session, room_id: str) -> List[DocPage]:
    """列出某文档频道的**全部页面**（按 parent_id, sort, id 排序，便于上层拼树）。"""
    if not room_id:
        return []
    return list(
        session.execute(
            select(DocPage)
            .where(DocPage.room_id == room_id)
            .order_by(DocPage.parent_id.asc(), DocPage.sort.asc(), DocPage.id.asc())
        ).scalars().all()
    )


def get_page(session: Session, page_id: int) -> Optional[DocPage]:
    """按 id 取单页（含正文）。不存在返回 None。"""
    return session.execute(
        select(DocPage).where(DocPage.id == page_id)
    ).scalars().first()


def _count_in_room(session: Session, room_id: str) -> int:
    return int(
        session.execute(
            select(func.count()).select_from(DocPage).where(DocPage.room_id == room_id)
        ).scalar() or 0
    )


def _next_sort(session: Session, room_id: str, parent_id: Optional[int]) -> int:
    """同一父级下的下一个排序值（追加到末尾）。"""
    cur = session.execute(
        select(func.max(DocPage.sort)).where(
            DocPage.room_id == room_id,
            DocPage.parent_id.is_(parent_id) if parent_id is None
            else DocPage.parent_id == parent_id,
        )
    ).scalar()
    return int(cur) + 1 if cur is not None else 0


def create_page(
    session: Session,
    *,
    room_id: str,
    title: str,
    parent_id: Optional[int] = None,
    content_md: str = "",
    cover: str = "",
    updated_by: str = "",
) -> Optional[DocPage]:
    """新建一页。返回创建的 DocPage；超量/非法父级返回 None。

    parent_id 给了就校验它确属本房间（防把页面挂到别的频道树上）。
    """
    if not room_id:
        return None
    if _count_in_room(session, room_id) >= _MAX_PAGES_PER_ROOM:
        return None
    pid = _norm_parent(parent_id)
    if pid is not None:
        parent = get_page(session, pid)
        if parent is None or parent.room_id != room_id:
            return None  # 父页面不存在或不在同一频道
    page = DocPage(
        room_id=room_id,
        parent_id=pid,
        title=str(title or "").strip()[:_MAX_TITLE] or "未命名页面",
        cover=str(cover or "").strip()[:_MAX_TITLE],
        content_md=str(content_md or "")[:_MAX_CONTENT],
        sort=_next_sort(session, room_id, pid),
        updated_by=updated_by or "",
    )
    session.add(page)
    session.flush()
    return page


def update_page(
    session: Session,
    page_id: int,
    *,
    title: Optional[str] = None,
    content_md: Optional[str] = None,
    cover: Optional[str] = None,
    updated_by: str = "",
) -> Optional[DocPage]:
    """改页面标题/正文/封面。返回更新后的页面；不存在返回 None。"""
    page = get_page(session, page_id)
    if page is None:
        return None
    if title is not None:
        page.title = str(title).strip()[:_MAX_TITLE] or "未命名页面"
    if content_md is not None:
        page.content_md = str(content_md)[:_MAX_CONTENT]
    if cover is not None:
        page.cover = str(cover).strip()[:_MAX_TITLE]
    if updated_by:
        page.updated_by = updated_by
    page.updated_at = _utcnow()
    session.flush()
    return page


def delete_page(session: Session, page_id: int) -> List[int]:
    """删一页**及其整棵子树**（级联）。返回被删的页面 id 列表（供上层同步清知识库）。"""
    page = get_page(session, page_id)
    if page is None:
        return []
    # 在内存里按 parent 关系收集整棵子树（页面量小，够用）。
    all_pages = list_pages(session, page.room_id)
    children: Dict[Optional[int], List[int]] = {}
    for p in all_pages:
        children.setdefault(p.parent_id, []).append(p.id)
    to_delete: List[int] = []
    stack = [page_id]
    while stack:
        cur = stack.pop()
        to_delete.append(cur)
        stack.extend(children.get(cur, []))
    for p in all_pages:
        if p.id in to_delete:
            session.delete(p)
    session.flush()
    return to_delete


def move_page(
    session: Session,
    page_id: int,
    *,
    parent_id: Optional[int] = None,
    sort: Optional[int] = None,
) -> Optional[DocPage]:
    """移动页面到新父级 / 改排序（拖拽用）。防环：不能把页面挂到它自己的子孙下。"""
    page = get_page(session, page_id)
    if page is None:
        return None
    new_parent = _norm_parent(parent_id)
    if new_parent is not None:
        parent = get_page(session, new_parent)
        if parent is None or parent.room_id != page.room_id:
            return None
        # 防环：new_parent 不能是 page 自身或其后代
        if new_parent == page_id or _is_descendant(session, page.room_id, new_parent, page_id):
            return None
    page.parent_id = new_parent
    if sort is not None:
        try:
            page.sort = int(sort)
        except (TypeError, ValueError):
            pass
    else:
        page.sort = _next_sort(session, page.room_id, new_parent)
    page.updated_at = _utcnow()
    session.flush()
    return page


def _is_descendant(
    session: Session, room_id: str, candidate_id: int, ancestor_id: int
) -> bool:
    """candidate_id 是否是 ancestor_id 的后代（顺着 parent 往上找到 ancestor 即是）。"""
    all_pages = {p.id: p.parent_id for p in list_pages(session, room_id)}
    cur: Optional[int] = candidate_id
    seen = set()
    while cur is not None and cur not in seen:
        seen.add(cur)
        parent = all_pages.get(cur)
        if parent == ancestor_id:
            return True
        cur = parent
    return False


def page_to_dict(page: DocPage, *, with_content: bool = False) -> Dict[str, Any]:
    """页面转给前端的字典。树/列表不带正文(省流量)，读单页才带。

    列表/卡片(类公众号)展示用：附 ``excerpt``(正文前若干字、去 markdown 符号的摘要) 和
    ``updated_ts``(最后更新 unix 秒)，前台只读视图据此渲染文章卡。
    """
    d: Dict[str, Any] = {
        "id": page.id,
        "parent_id": page.parent_id,
        "title": page.title,
        "cover": page.cover or "",
        "sort": page.sort,
        "updated_by": page.updated_by,
        "excerpt": _excerpt(page.content_md),
        "updated_ts": int(page.updated_at.timestamp()) if page.updated_at else 0,
    }
    if with_content:
        d["content_md"] = page.content_md
    return d


def _excerpt(md: str, limit: int = 80) -> str:
    """从 Markdown 正文里抽一段纯文本摘要(给列表卡片显示)：去掉常见标记符、压空白、截断。"""
    import re
    s = md or ""
    s = re.sub(r"```[\s\S]*?```", " ", s)          # 去代码块
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", s)     # 去图片
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)  # 链接只留文字
    s = re.sub(r"[#>*`~\-]+", " ", s)               # 去标题/强调/列表等符号
    s = re.sub(r"\s+", " ", s).strip()
    return s[:limit]


def _norm_parent(parent_id: Optional[int]) -> Optional[int]:
    """把 0/""/None 都归一成 None（顶层）；其余转 int。"""
    if parent_id in (None, 0, "", "0"):
        return None
    try:
        return int(parent_id)
    except (TypeError, ValueError):
        return None


def _utcnow():
    # 包一层便于测试/统一；onupdate 已会刷新，但显式写一次更直观。
    from datetime import datetime
    return datetime.utcfromtimestamp(int(time.time()))
