"""数据层 ORM 模型（SQLAlchemy 2.0 typed declarative）。

第一批表：**Skill**（技能定义）与 **Agent**（智能体定义）——模块2「群级 记忆/知识库/
Rule/Skill」最先要的两类结构化数据。知识库（pgvector）、群级记忆、Rule 是后续切片。

**作用域（scope）模型**：每条 Skill/Agent 都挂在一个作用域上，覆盖你提到的
「每账号配置 + 群级智能」两种需求：
    - ``user``   ：属于某个账号，scope_id = 用户 id（如 ``@alice:cosmac.cc``）
    - ``room``   ：属于某个群/频道，scope_id = room_id（群级技能/智能体）
    - ``global`` ：全平台共享，scope_id = ``""``
(scope, scope_id, slug) 三元组唯一——同一作用域内 slug 不重复，不同作用域可重名。
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# —— 作用域取值（别散落字符串字面量，统一引用这几个常量）——
SCOPE_USER = "user"
SCOPE_ROOM = "room"
SCOPE_GLOBAL = "global"


class Base(DeclarativeBase):
    """所有 cosmac 数据表的声明基类。"""


class TimestampMixin:
    """统一的「创建时间 / 更新时间」两列，给所有业务表复用。"""

    # 用 Python 端 default/onupdate（跨 SQLite/PG 行为一致），存 UTC。
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class Skill(Base, TimestampMixin):
    """技能定义：一段可复用的能力/提示，挂在某账号或某群下，供主 AID 调度时启用。

    字段：
        scope/scope_id: 作用域（见模块 docstring）。
        slug:           作用域内唯一的短标识（如 ``weekly-report``），程序按它引用。
        name:           展示名（给人看）。
        description:    一句话说明这个技能干嘛。
        instructions:   技能正文——喂给大模型的提示/步骤说明，可以较长。
        enabled:        是否启用（停用而不删除，保留历史）。
    """

    __tablename__ = "cosmac_skill"
    __table_args__ = (
        UniqueConstraint("scope", "scope_id", "slug", name="uq_skill_scope_slug"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scope: Mapped[str] = mapped_column(String(16), nullable=False, default=SCOPE_GLOBAL)
    scope_id: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    slug: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    instructions: Mapped[str] = mapped_column(Text, nullable=False, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    def __repr__(self) -> str:  # 方便日志/调试
        return f"<Skill {self.scope}:{self.scope_id or '*'}/{self.slug}>"


class Agent(Base, TimestampMixin):
    """智能体定义：一个带人设的 AI 角色，可绑定若干技能，挂在某账号或某群下。

    字段：
        scope/scope_id: 作用域（见模块 docstring）。
        slug:           作用域内唯一短标识。
        name:           展示名。
        description:    一句话说明。
        system_prompt:  人设/系统提示。
        model:          模型覆盖（空 = 跟随全局 AI 配置；非空 = 这个 Agent 单独用某模型）。
        skill_slugs:    绑定的技能 slug 列表（JSON）。先用列表简化，避免一上来就建多对多
                        关联表；以后真有「跨作用域共享技能」需求再升级成关联表。
        enabled:        是否启用。
    """

    __tablename__ = "cosmac_agent"
    __table_args__ = (
        UniqueConstraint("scope", "scope_id", "slug", name="uq_agent_scope_slug"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scope: Mapped[str] = mapped_column(String(16), nullable=False, default=SCOPE_GLOBAL)
    scope_id: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    slug: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    model: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    skill_slugs: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    def __repr__(self) -> str:
        return f"<Agent {self.scope}:{self.scope_id or '*'}/{self.slug}>"


class KnowledgeDoc(Base, TimestampMixin):
    """知识库里的一篇文档（入库后被切成若干 KnowledgeChunk 做向量检索）。

    挂在作用域上（room=本群知识库 / user=个人 / global=全平台）。
    source 记来源（文件名/URL/"chat"等），便于回溯与去重。
    """

    __tablename__ = "cosmac_kb_doc"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scope: Mapped[str] = mapped_column(String(16), nullable=False, default=SCOPE_ROOM)
    scope_id: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    title: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    source: Mapped[str] = mapped_column(String(512), nullable=False, default="")

    chunks: Mapped[List["KnowledgeChunk"]] = relationship(
        "KnowledgeChunk",
        back_populates="doc",
        cascade="all, delete-orphan",  # 删文档连带删它的分块
        order_by="KnowledgeChunk.ordinal",
    )

    def __repr__(self) -> str:
        return f"<KnowledgeDoc {self.scope}:{self.scope_id or '*'} #{self.id} {self.title!r}>"


class KnowledgeChunk(Base):
    """文档分块 + 它的向量表示。

    embedding 存成 JSON 浮点数组——**跨 SQLite/PG 通用**；v1 检索在 Python 里算余弦
    相似度（两种后端都能跑）。规模化后可在 Postgres 上换成 pgvector 列 + 近邻索引
    （见 CLAUDE.md §3：pgvector 是 Postgres 专属，缺它时优雅降级）。
    冗余存 scope/scope_id：检索时可直接按作用域过滤分块，不必每次 join 文档。
    """

    __tablename__ = "cosmac_kb_chunk"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doc_id: Mapped[int] = mapped_column(
        ForeignKey("cosmac_kb_doc.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scope: Mapped[str] = mapped_column(String(16), nullable=False, default=SCOPE_ROOM)
    scope_id: Mapped[str] = mapped_column(String(255), nullable=False, default="", index=True)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 在文档内的次序
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    embedding: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # 向量空间标识（embedder.tag，如 "hash:256"/"oai:openai:text-embedding-3-small"）。
    # 检索只比**同 tag** 的分块——换 embedder 后旧向量不会再混进来产生乱序/失真结果。
    embed_tag: Mapped[str] = mapped_column(
        String(64), nullable=False, default="", index=True
    )

    doc: Mapped["KnowledgeDoc"] = relationship("KnowledgeDoc", back_populates="chunks")

    def __repr__(self) -> str:
        return f"<KnowledgeChunk doc={self.doc_id} #{self.ordinal}>"


class WorkflowRun(Base, TimestampMixin):
    """一次外部工作流连接器的运行记录（模块3）。

    连接器**定义**走控制室 state event（后台编排，浏览器够不到 DB）；这里只存**运行记录**
    （派生/关系型数据，可追溯）。room_id/sender 记触发来源；status=ok/error。
    """

    __tablename__ = "cosmac_workflow_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False, default="webhook")
    room_id: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    sender: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    input: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # status: ok / error / queued（等待本机worker）/ pending（已开始外呼）/ processing（处理回调）
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ok")
    output: Mapped[str] = mapped_column(Text, nullable=False, default="")
    error: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # 异步回调的一次性令牌：平台带它回调，bot 据此校验；queued/pending/processing 期间保留。
    token: Mapped[str] = mapped_column(String(64), nullable=False, default="", index=True)

    def __repr__(self) -> str:
        return f"<WorkflowRun {self.slug} {self.status} #{self.id}>"


class SeenTxn(Base, TimestampMixin):
    """appservice 事务的**处理状态**，用于原子去重 + 崩溃恢复（#2/#3）。

    内存去重重启即丢、且无界增长；这里持久化处理状态，重启后 Synapse 重放也能识别。
    两阶段抢占（见 db/dedup.py）：
      - 新事务：原子 INSERT 一行（``done=False``、``claimed_at=now``）占住处理权；
        主键冲突 = 已有人在处理/已处理，绝不重复触发付费工作流。
      - ``done=True``：已处理完，重放直接跳过。
      - ``done=False`` 且 ``claimed_at`` 过期：上次处理中途崩了的残留，可被原子重新抢占
        （at-least-once，避免"先标记后处理"在崩溃时永久丢一整批事务）。
    旧记录按时间清理控制表大小。
    """

    __tablename__ = "cosmac_seen_txn"

    txn_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    # 是否处理完成。False=抢占中(processing)；True=已完成(done)
    done: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # 最近一次抢占时间——判断 processing 是否为"崩溃残留"(过期可重抢)的依据
    claimed_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )


class Order(Base, TimestampMixin):
    """一笔会员购买订单（模块4 交易系统）。

    会员**套餐定义**走控制室 state event（`cosmac.plans`，后台配）；这里只存**订单**这种
    关系型、要对账、要审计的交易数据。下单即建一行(status=created)，支付平台 webhook 验签
    成功后置 paid 并据 ``period_days`` 给用户开/续会员（写 ``cosmac.member`` state event）。

    幂等：``order_no`` 唯一；webhook 可能重复回调，靠 status 的原子 CAS(created→paid)保证
    只开通一次会员（见 db/order_repo.mark_paid）。金额用**最小货币单位整数**(分/cent)，不用浮点。
    """

    __tablename__ = "cosmac_order"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 对外订单号（唯一）；也用作支付平台回调里定位订单的业务标识
    order_no: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    # 下单时对套餐的快照（套餐定义以后可能改，订单要记下"当时买的是什么"）
    plan_slug: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    tier: Mapped[str] = mapped_column(String(16), nullable=False, default="paid")
    period_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="usd")
    # 支付渠道（manual/stripe/paypal/usdt/alipay/wechat）+ 渠道侧引用 id（session/intent/txhash）
    provider: Mapped[str] = mapped_column(String(16), nullable=False, default="manual")
    provider_ref: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    # created（已下单待支付）/ paid（已支付已开通）/ failed / canceled / refunded
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="created", index=True)
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # 支付成功后实际给会员开到的到期 unix 秒（审计：这笔订单把会员续到了哪天）
    granted_expires_ts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    def __repr__(self) -> str:
        return f"<Order {self.order_no} {self.status} {self.user_id} {self.tier}>"
