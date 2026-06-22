"""支付渠道抽象（模块4）—— 像多模型 AI 那样把各支付平台做成可插拔 adapter。

业务层（OrderService）只跟 :class:`PaymentProvider` 打交道，不关心是 Stripe 还是支付宝。
每个渠道 adapter 实现两件事：
  1. :meth:`create_checkout` —— 为一笔订单生成"去支付"的方式（跳转 URL / 二维码 / 收款地址）。
  2. :meth:`parse_callback` —— 收到平台 webhook 时**验签**并归一化成 :class:`PaymentEvent`。

**铁律**：渠道密钥只从服务端环境变量读，绝不进代码/Matrix/订单数据（同 LLM key 策略）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class CheckoutResult:
    """create_checkout 的产物：告诉前端"怎么去付这笔钱"。

    kind：``redirect``（跳 URL）/ ``address``（加密货币收款地址）/ ``manual``（人工/测试确认）。
    """

    kind: str
    url: str = ""                       # redirect：支付平台收银台 URL
    address: str = ""                   # address：收款地址（USDT 等）
    extra: Dict[str, Any] = field(default_factory=dict)  # 渠道附加信息（二维码串、备注等）


@dataclass
class PaymentEvent:
    """从平台 webhook 验签后归一化出来的支付事件。

    order_no：本平台回调里对应的我方订单号（adapter 负责从 payload 取出）。
    paid：本次是否表示"已成功收款"。provider_ref：平台侧凭证 id（session/intent/txhash）。
    """

    order_no: str
    paid: bool
    provider_ref: str = ""
    amount_cents: Optional[int] = None   # 平台回传的实收金额（可用于二次校验，None=不校验）
    currency: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)


class PaymentProvider:
    """支付渠道接口。各渠道 adapter 继承并实现下面两个方法。"""

    name: str = "base"

    def create_checkout(
        self, *, order_no: str, amount_cents: int, currency: str,
        title: str, return_url: str = "",
    ) -> CheckoutResult:
        """为订单生成支付方式。子类实现；这里不可直接用。"""
        raise NotImplementedError

    def parse_callback(
        self, *, headers: Dict[str, str], body: bytes
    ) -> PaymentEvent:
        """验签平台 webhook 并归一化成 PaymentEvent。验签失败应抛异常（绝不当成功处理）。"""
        raise NotImplementedError
