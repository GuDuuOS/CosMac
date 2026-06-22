"""会员套餐定义（控制室 ``cosmac.plans`` state event 的解析 + 校验）。

套餐是管理员在后台配的权威配置（同 workflows/gating 套路走 state event）。这里把外部可写、
不可信的内容**强校验**成干净的 :class:`Plan` 列表，供下单时取价/取时长/取目标等级。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from cosmac.members import DEFAULT_TIER, is_valid_tier, normalize_tier


@dataclass
class Plan:
    """一个会员套餐：买它 → 获得 ``tier`` 等级、有效期 ``period_days`` 天。

    prices：货币(小写,如 "usd"/"cny"/"usdt") → **最小货币单位整数**(美分/分；USDT 用最小单位)。
    """

    slug: str
    name: str
    tier: str
    period_days: int
    prices: Dict[str, int] = field(default_factory=dict)
    enabled: bool = True

    def price_cents(self, currency: str) -> Optional[int]:
        """该套餐在某货币下的价格（分）；未定价返回 None。"""
        return self.prices.get((currency or "").lower())

    def currencies(self) -> List[str]:
        """该套餐支持的货币列表。"""
        return list(self.prices.keys())


def _parse_prices(raw: Any) -> Dict[str, int]:
    """校验 prices：货币 key 转小写、值必须是 > 0 的整数分；脏的丢弃。"""
    out: Dict[str, int] = {}
    if not isinstance(raw, dict):
        return out
    for cur, cents in raw.items():
        if not isinstance(cur, str):
            continue
        try:
            c = int(cents)
        except (TypeError, ValueError):
            continue
        if c > 0:
            out[cur.strip().lower()] = c
    return out


def parse_plans(content: Optional[Dict[str, Any]]) -> List[Plan]:
    """把 ``cosmac.plans`` 内容解析成 Plan 列表，强校验兜脏数据。

    只收：slug 非空、tier 合法且非免费（免费不用买）、period_days 为正整数、prices 至少一项。
    """
    out: List[Plan] = []
    if not isinstance(content, dict):
        return out
    plans = content.get("plans")
    if not isinstance(plans, list):
        return out
    seen: set = set()
    for p in plans:
        if not isinstance(p, dict):
            continue
        slug = str(p.get("slug") or "").strip()
        if not slug or slug in seen:
            continue
        tier = normalize_tier(p.get("tier"))
        if not is_valid_tier(tier) or tier == DEFAULT_TIER:
            continue  # 免费等级没有"购买"一说
        try:
            period = int(p.get("period_days"))
        except (TypeError, ValueError):
            continue
        if period <= 0:
            continue
        prices = _parse_prices(p.get("prices"))
        if not prices:
            continue  # 没有任何定价的套餐无法下单
        seen.add(slug)
        out.append(
            Plan(
                slug=slug,
                name=str(p.get("name") or slug),
                tier=tier,
                period_days=period,
                prices=prices,
                enabled=p.get("enabled") is not False,
            )
        )
    return out


def find_plan(plans: List[Plan], slug: str) -> Optional[Plan]:
    """按 slug 找套餐（仅启用的）。"""
    for p in plans:
        if p.slug == slug and p.enabled:
            return p
    return None
