"""会员等级（账号权限分层）—— 定义 + 校验 + 控制室读写。

这是什么
--------
在「服务器管理员」（Synapse 原生 admin 标志，管后台用）之外，给**普通用户**再叠一层
**会员身份**：免费 / 付费 / 创作者。两套是**正交**的——一个人既可以是服务器管理员，
又可以是任意会员等级（管理员身份 ≠ 会员身份，见 CLAUDE.md 路线图「账号权限」决策）。

为什么放这里
------------
- **枚举/标签/校验**是纯逻辑，前后端都要用同一套口径，集中在这一处避免飘移。
- **存储**走控制室的 ``cosmac.members`` state event（见 config.MEMBERS_EVENT_TYPE 的长注释：
  权威数据、用户不可自改、只有管理员/bot 能写）。这里提供一个薄封装 :class:`MembersStore`，
  把「读当前 map / 查某人等级 / 授予 / 撤销」收口成几个方法，供 bot 调用。

谁来写
------
1. **管理后台**（管理员浏览器）：手动调整——直接走 Matrix 写 state event（前端 client.ts）。
2. **未来模块4（交易系统）支付成功**：服务端调 :meth:`MembersStore.grant` —— 这就是本期
   预留给「购买获得会员」的服务端接口。本期不接真实支付，只把接口和数据模型立起来。

注意：本模块**只依赖** MatrixClient 的 ``resolve_alias`` / ``get_state_event`` /
``set_state_event`` 三个方法，不引入任何额外依赖，方便单测用假 client 注入。
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from cosmac.config import GATING_EVENT_TYPE, MEMBERS_EVENT_TYPE

logger = logging.getLogger("cosmac.members")

# —— 会员等级枚举（slug 是机器用的稳定标识，绝不改；label 是给人看的中文，可随品牌改）——
TIER_FREE = "free"        # 免费会员（默认；未在 cosmac.members 里列出的用户都算这个）
TIER_PAID = "paid"        # 付费会员（购买/管理员授予）
TIER_CREATOR = "creator"  # 创作者会员（购买/管理员授予；面向内容创作者的身份）

# 默认等级：任何没有显式记录的用户都视为免费会员。
DEFAULT_TIER = TIER_FREE

# 等级目录：slug → 中文标签 + level（数值仅用于「至少 X 级」这类比较；不代表创作者一定
# 比付费"高级"，只是给门控一个可排序的口径）。顺序即前端下拉展示顺序。
MEMBER_TIERS: List[Dict[str, Any]] = [
    {"slug": TIER_FREE, "label": "免费会员", "level": 0},
    {"slug": TIER_PAID, "label": "付费会员", "level": 10},
    {"slug": TIER_CREATOR, "label": "创作者会员", "level": 20},
]

# 便捷映射（由上面的目录派生，避免两处手写不一致）
_TIER_BY_SLUG: Dict[str, Dict[str, Any]] = {t["slug"]: t for t in MEMBER_TIERS}


def is_valid_tier(tier: str) -> bool:
    """tier 是否是已知等级 slug。"""
    return tier in _TIER_BY_SLUG


def normalize_tier(tier: Optional[str]) -> str:
    """把任意输入规整成合法等级 slug；空/未知一律回落到默认（免费）。

    脏数据兜底：控制室 state event 是外部可写的，读出来的 tier 不可信，统一过这一关。
    """
    t = (tier or "").strip()
    return t if t in _TIER_BY_SLUG else DEFAULT_TIER


def tier_label(tier: Optional[str]) -> str:
    """等级 slug → 中文标签（未知回落到「免费会员」）。"""
    return _TIER_BY_SLUG[normalize_tier(tier)]["label"]


def tier_level(tier: Optional[str]) -> int:
    """等级 slug → 数值档位（供门控做「至少付费」这类比较）。"""
    return int(_TIER_BY_SLUG[normalize_tier(tier)]["level"])


def parse_members(content: Optional[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """把 ``cosmac.members`` state event 的内容解析成 {user_id: {tier, source, updated_ts}}。

    强校验 + 兜脏数据（state event 外部可写，绝不信任）：
      - 只收 ``members`` 是 dict 的；
      - key 必须是 ``@..:..`` 形状的 user_id（粗判，挡明显垃圾）；
      - tier 经 normalize_tier 规整；**等于默认(免费)的直接丢弃**——免费是隐含默认，
        不必显式存，也保证 map 里只有"非免费"的覆盖。
    """
    out: Dict[str, Dict[str, Any]] = {}
    if not isinstance(content, dict):
        return out
    members = content.get("members")
    if not isinstance(members, dict):
        return out
    for uid, rec in members.items():
        if not isinstance(uid, str) or not uid.startswith("@") or ":" not in uid:
            continue
        rec = rec if isinstance(rec, dict) else {}
        tier = normalize_tier(rec.get("tier"))
        if tier == DEFAULT_TIER:
            continue  # 免费是默认，不显式保留
        out[uid] = {
            "tier": tier,
            "source": str(rec.get("source") or "admin"),
            "updated_ts": rec.get("updated_ts"),
        }
    return out


class MembersStore:
    """控制室 ``cosmac.members`` 的薄封装：读当前 map / 查等级 / 授予 / 撤销。

    所有写操作都是「读改写」整份 map（state event 没有部分更新语义），并发写极少（管理员
    手动调整 + 偶发支付回调），冲突概率可忽略；真出现也只是最后写赢，不致命。

    构造参数：
        client:               提供 resolve_alias/get_state_event/set_state_event 的 MatrixClient。
        control_room_alias:   控制室别名（#cosmac-ctrl:<server>）。
    """

    def __init__(self, client: Any, control_room_alias: str):
        self._client = client
        self._alias = control_room_alias

    def _ctrl_room(self) -> Optional[str]:
        """解析控制室 room_id；解析不到返回 None（控制室还没建）。"""
        try:
            return self._client.resolve_alias(self._alias)
        except Exception as e:
            logger.debug("解析控制室别名失败（会员）：%s", e)
            return None

    def get_all(self) -> Dict[str, Dict[str, Any]]:
        """读控制室会员 map（{user_id: {tier, source, updated_ts}}）。失败/无数据返回空。

        **注意**：此方法对只读查询友好（读失败回落空=按免费处理，不致命）。但**写操作
        （grant）绝不能用它**——读失败回空会导致整份 map 被覆盖、清空其他会员。写路径用
        :meth:`_read_all_strict`（读失败抛异常）。
        """
        room = self._ctrl_room()
        if not room:
            return {}
        try:
            ev = self._client.get_state_event(room, MEMBERS_EVENT_TYPE)
            return parse_members(ev)
        except Exception as e:
            logger.debug("读取会员等级失败（忽略）：%s", e)
            return {}

    def _read_all_strict(self, room: str) -> Dict[str, Dict[str, Any]]:
        """读会员 map，**读失败抛异常**（区别于"读到空"）——给写操作用（#2）。

        get_state_event 语义：404→None（确实还没写过，合法空）；403/网络/5xx→抛异常。
        所以这里只有"事件不存在"才返回空 map，瞬时读失败会向上抛、让 grant 放弃写入，
        绝不拿一份（因读失败而）空的 map 去覆盖、清空其他会员。
        """
        ev = self._client.get_state_event(room, MEMBERS_EVENT_TYPE)
        return parse_members(ev)

    def get_tier(self, user_id: str) -> str:
        """查某用户的会员等级 slug；未记录 → 默认（免费）。"""
        rec = self.get_all().get(user_id)
        return normalize_tier(rec.get("tier")) if rec else DEFAULT_TIER

    def grant(
        self,
        user_id: str,
        tier: str,
        source: str = "admin",
        now_ts: Optional[int] = None,
    ) -> bool:
        """授予/调整某用户的会员等级（**预留给模块4支付的服务端入口**，也用于 bot 命令）。

        - tier 经校验：非法直接拒（返回 False），不写脏数据进控制室。
        - tier == 免费 等价于「撤销」（从 map 里删掉该用户，回落默认）。
        - source 记录来源（"admin"/"purchase"/…），便于以后审计「这级是怎么来的」。
        成功写入返回 True；控制室不存在/写失败返回 False（调用方据此提示）。
        """
        if not is_valid_tier(tier):
            logger.warning("授予会员失败：未知等级 %r", tier)
            return False
        room = self._ctrl_room()
        if not room:
            logger.warning("授予会员失败：控制室不存在（还没建）")
            return False
        # #2：**先严格读**当前 map——读失败抛异常→放弃写入，绝不拿空表覆盖、清空其他会员。
        try:
            current = self._read_all_strict(room)
        except Exception:
            logger.exception(
                "授予会员失败：读当前会员出错，放弃写入（避免清空其他会员）user=%s", user_id
            )
            return False
        # 读成功后再改写整份 map 写回
        if tier == DEFAULT_TIER:
            current.pop(user_id, None)  # 免费=撤销=移出 map
        else:
            current[user_id] = {
                "tier": tier,
                "source": source,
                "updated_ts": int(now_ts if now_ts is not None else time.time()),
            }
        try:
            return bool(
                self._client.set_state_event(
                    room, MEMBERS_EVENT_TYPE, {"members": current}
                )
            )
        except Exception:
            logger.exception("授予会员等级失败 user=%s tier=%s", user_id, tier)
            return False

    def revoke(self, user_id: str) -> bool:
        """撤销某用户的会员（回落到免费）。等价 grant(user_id, free)。"""
        return self.grant(user_id, TIER_FREE)


# =====================================================================
#  功能门控（按会员等级限制能力）
# =====================================================================
#
# 设计：管理员在后台把「每个能力」配一个**最低门槛**，bot 在执行点**服务端强制**。
# 门槛是一条 4 级阶梯：免费 < 付费 < 创作者 < 仅管理员。
#   - tier 门槛（free/paid/creator）：用户会员等级 ≥ 门槛即放行；**平台管理员永远放行**
#     （staff 能用一切，免得给自己开会员）。
#   - 特殊门槛 admin（「仅管理员」）：只有平台管理员放行（用于共享付费凭据这类高危能力）。
# 默认未配置的能力取 GATE_CATALOG 里各自的 default：多数 free（不限制），保证零回归。

GATE_ADMIN = "admin"  # 特殊门槛：仅平台管理员

# 门槛阶梯的排序值（越大越严）。tier 部分与 tier_level 对齐；admin 居顶。
_GATE_RANK: Dict[str, int] = {
    TIER_FREE: 0,
    TIER_PAID: 10,
    TIER_CREATOR: 20,
    GATE_ADMIN: 1000,
}

# 后台门控下拉可选的「门槛」目录（slug + 标签）。即上面阶梯的人类可读版。
GATE_LEVELS: List[Dict[str, str]] = [
    {"slug": TIER_FREE, "label": "免费（不限制）"},
    {"slug": TIER_PAID, "label": "付费会员及以上"},
    {"slug": TIER_CREATOR, "label": "创作者会员"},
    {"slug": GATE_ADMIN, "label": "仅平台管理员"},
]

# 可门控的能力目录：key=能力标识（与 bot 执行点一致，**稳定别改**），label=后台显示，
# default=未配置时的默认门槛。**新增功能就往这里加一条**（前后端各加，见 client.ts GATE_CATALOG）。
GATE_CATALOG: List[Dict[str, str]] = [
    {"key": "ai_chat", "label": "基础 AI 对话（@中枢AI / 私聊回复）", "default": TIER_FREE},
    {"key": "knowledge", "label": "知识库（RAG 检索 + 知识命令）", "default": TIER_FREE},
    {"key": "create_room", "label": "建群 / 开专班", "default": TIER_FREE},
    {"key": "workflow_run", "label": "跑工作流（外部/付费、共享凭据）", "default": GATE_ADMIN},
]

# 由目录派生的便捷映射
_GATE_DEFAULTS: Dict[str, str] = {g["key"]: g["default"] for g in GATE_CATALOG}
_GATE_LABELS: Dict[str, str] = {g["key"]: g["label"] for g in GATE_CATALOG}
_GATE_LEVEL_SLUGS = {lv["slug"] for lv in GATE_LEVELS}


def gate_rank(value: Optional[str]) -> int:
    """门槛 slug → 排序值（未知按免费=0）。"""
    return _GATE_RANK.get((value or "").strip(), 0)


def normalize_gate(value: Optional[str], default: str = TIER_FREE) -> str:
    """把门槛输入规整成合法 slug（free/paid/creator/admin）；非法回落到 default。"""
    v = (value or "").strip()
    return v if v in _GATE_LEVEL_SLUGS else default


def gate_capability_label(key: str) -> str:
    """能力 key → 中文标签（未知回落到 key 本身）。"""
    return _GATE_LABELS.get(key, key)


def parse_gates(content: Optional[Dict[str, Any]]) -> Dict[str, str]:
    """解析 ``cosmac.gating`` 内容 → {能力key: 门槛slug}。只收已知能力 + 合法门槛，兜脏数据。"""
    out: Dict[str, str] = {}
    if not isinstance(content, dict):
        return out
    gates = content.get("gates")
    if not isinstance(gates, dict):
        return out
    for key, val in gates.items():
        if key in _GATE_DEFAULTS and isinstance(val, str) and val in _GATE_LEVEL_SLUGS:
            out[key] = val
    return out


class GatingStore:
    """控制室 ``cosmac.gating`` 的薄封装：读门控策略。

    读多写少：bot 频繁读（每条消息可能查几次），故带一个**短 TTL 缓存**避免每次打服务器；
    写由管理后台浏览器直接走 Matrix（bot 不写门控）。读失败保留上次成功值（不失效开放）。
    """

    def __init__(self, client: Any, control_room_alias: str, ttl: float = 15.0):
        self._client = client
        self._alias = control_room_alias
        self._ttl = ttl
        self._cache: Dict[str, str] = {}
        self._cache_ts: float = float("-inf")

    def get_all(self) -> Dict[str, str]:
        """返回**合并默认后**的完整门控映射 {能力key: 门槛slug}（带 TTL 缓存）。"""
        now = time.monotonic()
        if now - self._cache_ts < self._ttl and self._cache:
            return self._cache
        merged = dict(_GATE_DEFAULTS)  # 先铺默认
        try:
            room = self._client.resolve_alias(self._alias)
            if room:
                ev = self._client.get_state_event(room, GATING_EVENT_TYPE)
                merged.update(parse_gates(ev))
            self._cache = merged
            self._cache_ts = now
            return merged
        except Exception as e:
            # 读失败：有上次成功值就沿用（不因抖动突然放开/锁死）。
            # #3：**不刷新 cache_ts**——否则把"失败"缓存一个 TTL，会延长付费门控被绕过的
            # 窗口。这里让下次调用立即重试，尽快拿到真实策略。若**从未**读成功过（无缓存），
            # 只能暂用默认（多为 free）——靠启动 warm() 把这个窗口压到极小（见 warm 注释）。
            if self._cache:
                logger.warning("读取门控策略失败，沿用上次成功值，将尽快重试：%s", e)
            else:
                logger.warning(
                    "门控策略首次读取失败、暂用内置默认（部分能力默认免费，付费门控本窗口可能"
                    "被绕过），将每次调用重试直到读到真实策略：%s", e
                )
            return self._cache or merged

    def warm(self) -> bool:
        """启动时预热一次（best-effort）：尽快建立"上次成功值"缓存，把"首读失败→暂用默认
        →付费门控被绕过"的窗口压到极小（#3）。读到真实策略返回 True，否则 False（不抛、不阻断启动）。"""
        try:
            self.get_all()
            return bool(self._cache)
        except Exception:
            return False

    def required(self, capability: str) -> str:
        """某能力的最低门槛 slug（未在目录里的能力按免费=不限制）。"""
        return self.get_all().get(capability, _GATE_DEFAULTS.get(capability, TIER_FREE))
