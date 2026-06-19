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


def render_skills(items: List[Dict]) -> str:
    """把若干技能字典渲染成一段 system 提示；没有技能返回空串。"""
    if not items:
        return ""
    header = "你已装载以下技能，按需运用："
    lines = [header]
    total = len(header)
    used = 0
    for it in items:
        title = (it.get("name") or it.get("slug") or "").strip()
        if not title:
            continue
        head = f"## 技能：{title}"
        desc = (it.get("description") or "").strip()
        if desc:
            head += f"（{desc}）"
        instr = (it.get("instructions") or "").strip()
        block = head + (f"\n{instr}" if instr else "")
        # 超预算且已注入过至少一条：停下并说明还剩多少没注入
        if total + len(block) + 1 > MAX_TOTAL_PROMPT_CHARS and used > 0:
            lines.append(f"（另有 {len(items) - used} 个技能因超出长度预算未注入）")
            break
        lines.append(block)
        total += len(block) + 1
        used += 1
    return "\n".join(lines)
