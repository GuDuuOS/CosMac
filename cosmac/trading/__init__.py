"""交易系统（模块4）—— 会员订阅/充值。

分层（与项目既有套路一致）：
- **套餐定义** 走控制室 state event ``cosmac.plans``（后台配，``plans.py`` 解析）。
- **支付渠道** 抽象成可插拔的 :class:`PaymentProvider`（``base.py``），各渠道 adapter
  （manual/stripe/paypal/usdt/alipay/wechat）；**密钥只进服务端 env，绝不进代码/Matrix**。
- **订单生命周期** 由 :class:`OrderService`（``service.py``）编排：下单→（跳支付）→平台回调
  验签→订单置 paid→按套餐时长给用户开/续会员（写 ``cosmac.member`` state event）。
- **订单数据** 进 DB（``cosmac_order``，见 db/order_repo）。

本期(P1)只落地"地基 + 手动/mock 支付"，真实渠道(Stripe 等) adapter 后续分期加。
"""
