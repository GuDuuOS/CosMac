"""数据库连接 / 会话管理（同步 SQLAlchemy）。

为什么这么设计：
- **同步**：主 AI bot 是同步的（``ThreadingHTTPServer`` + ``requests``），数据层也保持
  同步，不引入 async 的复杂度。
- **连接来源**：``COSMAC_DATABASE_URL`` 环境变量优先（旧 ``GUDUU_DATABASE_URL`` 仍兼容；生产用它指向独立 PostgreSQL）；
  没设就回退到本地 SQLite 文件 ``run/cosmac.db``——本地开发/跑测试零基建即可。
- **懒初始化**：第一次用到时才建 engine（``get_session`` 会自动 ``init_engine``），
  测试可以先用内存库显式 ``init_engine("sqlite://")`` 覆盖默认。

注意：知识库的 pgvector 是 Postgres 专属能力，本地 SQLite 跑不了向量检索——
相关功能要能在缺 pgvector 时优雅降级（见 CLAUDE.md §3）。
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator, Optional

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from cosmac.db.models import Base

# —— 模块级单例：进程内共享一个 engine / sessionmaker ——
# bot 多线程（每个 HTTP 请求一个线程），engine 的连接池本身线程安全；
# session 不跨线程共享——每次用 get_session()/session_scope() 现取现用。
_engine: Optional[Engine] = None
_Session: Optional[sessionmaker] = None


def database_url() -> str:
    """解析要连的数据库 URL。

    优先级：环境变量 COSMAC_DATABASE_URL（旧 GUDUU_DATABASE_URL 仍兼容）> 本地默认
    SQLite（run/cosmac.db）。本地默认用绝对路径，避免「从不同工作目录启动」时 SQLite
    落在不同文件。
    """
    url = os.environ.get("COSMAC_DATABASE_URL") or os.environ.get("GUDUU_DATABASE_URL")
    if url:
        return url
    # 仓库根：cosmac/db/engine.py → 上三级。本地产物统一放 run/（已 gitignore）。
    repo_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    run_dir = os.path.join(repo_root, "run")
    os.makedirs(run_dir, exist_ok=True)
    return f"sqlite:///{os.path.join(run_dir, 'cosmac.db')}"


def init_engine(url: Optional[str] = None, *, create_all: bool = True) -> Engine:
    """（重新）初始化进程内的 engine 与 sessionmaker。

    参数：
        url:        要连的数据库；不传则用 ``database_url()`` 解析。
        create_all: 是否顺手按 models 建表（greenfield 阶段够用；以后上 alembic 迁移再关掉）。

    返回建好的 engine。测试里可传 ``"sqlite://"`` 用纯内存库。
    """
    global _engine, _Session
    resolved = url or database_url()
    # SQLite 内存库（"sqlite://"）必须用 StaticPool 才能在同一连接里保留建好的表，
    # 否则每次取连接都是新的空库；文件库则正常用默认池。
    connect_args = {}
    engine_kwargs = {"future": True}
    if resolved.startswith("sqlite"):
        # 允许跨线程使用同一连接（bot 多线程）。
        connect_args["check_same_thread"] = False
        if ":memory:" in resolved or resolved in ("sqlite://", "sqlite:///:memory:"):
            from sqlalchemy.pool import StaticPool

            engine_kwargs["poolclass"] = StaticPool
    _engine = create_engine(resolved, connect_args=connect_args, **engine_kwargs)
    _Session = sessionmaker(bind=_engine, future=True, expire_on_commit=False)
    if create_all:
        Base.metadata.create_all(_engine)
    return _engine


def get_engine() -> Engine:
    """拿到当前 engine（没初始化就用默认配置懒初始化）。"""
    if _engine is None:
        init_engine()
    assert _engine is not None  # 给类型检查器看：init_engine 必然已赋值
    return _engine


def get_session() -> Session:
    """开一个新的 ORM 会话（用完记得 close；推荐用 ``session_scope()`` 自动管理）。"""
    if _Session is None:
        init_engine()
    assert _Session is not None
    return _Session()


@contextmanager
def session_scope() -> Iterator[Session]:
    """事务作用域：正常结束自动 commit，出异常自动 rollback，最后一定 close。

    用法：
        with session_scope() as s:
            s.add(obj)
        # 离开 with 块时已提交
    """
    session = get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
