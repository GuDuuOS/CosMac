"""把「技能」渲染成喂给主 AI 的 system 提示文本。

放在 cosmac 顶层、**不导入任何数据库/SQLAlchemy**——因为全局技能走 Matrix state
event（控制室），bot 读它时不需要 DB；服务器即便没装 SQLAlchemy 也能用全局技能。

输入是一串「技能字典」list[dict]，每项支持键：slug / name / description / instructions。
（DB 里的 ORM Skill 也可先转成同样的字典再渲染，见 cosmac.db.service。）
"""

from __future__ import annotations

from typing import Dict, List

# 注入主 AI 的技能提示**总长度**上限：即便单条限了长，启用的技能一多也会撑爆上下文/费用，
# 这里再兜一层——超预算就停止注入剩余技能并给出提示（不静默截断）。
MAX_TOTAL_PROMPT_CHARS = 6000


def _s(v: object) -> str:
    """把任意字段值安全转成字符串再去空白——脏数据（如 name 是数字/None）也不崩。"""
    return ("" if v is None else str(v)).strip()


def render_skills(items: List[Dict]) -> str:
    """把若干技能字典渲染成一段 system 提示；没有技能返回空串。

    健壮性：字段值不假设是字符串（脏数据 name:123 也只是被转成 "123"，绝不抛异常）；
    总长度有上限，**含第一条**——单条超长会被截断，不会因 used>0 而漏过预算。
    """
    if not items:
        return ""
    header = "你已装载以下技能，按需运用："
    lines = [header]
    total = len(header)
    used = 0
    for it in items:
        if not isinstance(it, dict):
            continue
        title = _s(it.get("name")) or _s(it.get("slug"))
        if not title:
            continue
        # 预算已用尽 → 停止注入剩余，给出提示（不静默吞）
        if total >= MAX_TOTAL_PROMPT_CHARS:
            lines.append(f"（另有 {len(items) - used} 个技能因超出长度预算未注入）")
            break
        head = f"## 技能：{title}"
        desc = _s(it.get("description"))
        if desc:
            head += f"（{desc}）"
        instr = _s(it.get("instructions"))
        block = head + (f"\n{instr}" if instr else "")
        # 单条若超出剩余预算就**截断这一条**（含第一条），保证总长度恒 ≤ 上限
        remaining = MAX_TOTAL_PROMPT_CHARS - total
        if len(block) + 1 > remaining:
            block = block[: max(0, remaining - 12)].rstrip() + "…（已截断）"
        lines.append(block)
        total += len(block) + 1
        used += 1
    return "\n".join(lines)
