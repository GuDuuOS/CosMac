"""手动/测试支付渠道（模块4 P1）。

没有任何真实支付平台时用它把**整条业务链跑通**：下单 → 拿到一个"待人工确认"的占位 →
管理员/测试用一个签名 token 触发回调 → 订单 paid → 开会员。

回调用 HMAC(订单号, COSMAC_PAY_MANUAL_SECRET) 验签，避免任何人裸 POST 就能白嫖开会员。
真实渠道(Stripe 等)上线后，这个 provider 只保留给测试/线下转账人工确认用。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from typing import Dict

from cosmac.trading.base import CheckoutResult, PaymentEvent, PaymentProvider


def _secret() -> str:
    """人工确认的验签密钥（只从服务端 env 读）。未配则用固定占位（仅本地测试可用）。"""
    return os.environ.get("COSMAC_PAY_MANUAL_SECRET", "") or "cosmac-manual-dev-secret"


def manual_sign(order_no: str) -> str:
    """对订单号做 HMAC 签名——人工确认回调要带上它才算数。"""
    return hmac.new(
        _secret().encode("utf-8"), (order_no or "").encode("utf-8"), hashlib.sha256
    ).hexdigest()


class ManualProvider(PaymentProvider):
    """人工/测试确认渠道：create_checkout 返回"待确认"占位；parse_callback 校验 HMAC。"""

    name = "manual"

    def create_checkout(
        self, *, order_no: str, amount_cents: int, currency: str,
        title: str, return_url: str = "",
    ) -> CheckoutResult:
        # 没有真实收银台，返回一个"待人工/测试确认"的占位，附上本单签名便于线下确认。
        return CheckoutResult(
            kind="manual",
            extra={
                "order_no": order_no,
                "note": "等待人工/测试确认收款后开通",
                "confirm_token": manual_sign(order_no),
            },
        )

    def parse_callback(
        self, *, headers: Dict[str, str], body: bytes
    ) -> PaymentEvent:
        """回调体形如 {"order_no": "...", "token": "<hmac>"}；token 不符即抛异常。"""
        data = json.loads(body.decode("utf-8") or "{}")
        order_no = str(data.get("order_no") or "")
        token = str(data.get("token") or "")
        if not order_no or not hmac.compare_digest(token, manual_sign(order_no)):
            raise ValueError("人工确认签名不符，拒绝")  # 验签失败绝不当成功
        return PaymentEvent(order_no=order_no, paid=True, provider_ref="manual")
