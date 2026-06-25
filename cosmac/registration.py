"""自建「邮箱验证码」注册。

为什么自建（而不是用 Synapse 原生邮箱注册）：
  Synapse 原生的邮箱注册发的是**验证链接**（点链接验证 3pid）；负责人要的是**验证码**体验
  （邮件里给 6 位码、用户在 app 里输）。Synapse 不原生支持验证码，故自建这一层：
    1) 前端填邮箱 → POST /cosmac/register/request-code → 这里生成 6 位码、用 SMTP（Lark）发信。
    2) 前端填用户名+密码+码 → POST /cosmac/register/verify → 这里验码 → 用
       registration_shared_secret 向 Synapse `/_synapse/admin/v1/register` 建号
       （该端点是给程序化建号用的，**不受 enable_registration 开关影响**——所以建完号后
        服务端应把开放注册关掉，强制所有注册都走我们的邮箱验证）。

安全 / 健壮（单实例「够用即止」，与 wf 同口径）：
  · 验证码存**内存**（带 TTL + 线程锁）——单 bot 实例足够；将来多实例再迁 DB。
  · 限频：同邮箱发码有冷却 + 每小时上限；验码有尝试次数上限（防爆破）。
  · 真密钥（SMTP 密码 / registration_shared_secret）只从**服务端 env** 读，绝不进代码/前端/Matrix。

涉及的 env（生产用 systemd Environment / Secret Manager 注入；本地不配则注册不可用、优雅报错）：
  COSMAC_SMTP_HOST / COSMAC_SMTP_PORT(默认465) / COSMAC_SMTP_USER / COSMAC_SMTP_PASSWORD /
  COSMAC_SMTP_FROM(发件地址，如 noreply@guduu.co) / COSMAC_SMTP_FROM_NAME(可选，显示名) /
  COSMAC_REGISTRATION_SHARED_SECRET(= homeserver.yaml 里的 registration_shared_secret)
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
import smtplib
import ssl
import threading
import time
from email.message import EmailMessage
from email.utils import formataddr
from typing import Any, Callable, Dict, Optional, Tuple

import requests

from cosmac.config import _env

logger = logging.getLogger("cosmac.registration")

# ── 可调参数（够用即止，不做成配置项）────────────────────────────
_CODE_TTL = 10 * 60          # 验证码有效期（秒）
_RESEND_COOLDOWN = 60        # 同邮箱两次发码的最小间隔（秒）
_MAX_SENDS_PER_HOUR = 5      # 同邮箱每小时最多发码次数（防刷爆 Lark 配额）
_MAX_VERIFY_ATTEMPTS = 5     # 单个码最多验错几次（防爆破）
_HS_TIMEOUT = 15            # 调 Synapse 的超时（秒）

# 邮箱 / 用户名 / 密码 的基本校验
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_USERNAME_RE = re.compile(r"^[a-z0-9._=\-/+]+$")  # Matrix localpart 允许的安全子集（小写）


class _PendingCode:
    """某邮箱待验证的码 + 限频计数（仅内存）。"""

    __slots__ = ("code", "expires", "attempts", "last_sent", "sent_times")

    def __init__(self) -> None:
        self.code: str = ""
        self.expires: float = 0.0
        self.attempts: int = 0
        self.last_sent: float = 0.0
        self.sent_times: list[float] = []  # 最近一小时的发码时间戳（滑窗限频）


# key（"用途:邮箱小写"）→ _PendingCode；多线程 HTTP server，必须加锁。
# 用「用途」前缀把注册码和找回密码码分开存——注册码不能拿去重置密码，反之亦然。
_store: Dict[str, _PendingCode] = {}
_lock = threading.Lock()


def _key(purpose: str, email: str) -> str:
    return f"{purpose}:{email}"


def _gen_code() -> str:
    """生成 6 位数字验证码（用密码学安全随机，避免可预测）。"""
    import secrets
    return f"{secrets.randbelow(1_000_000):06d}"


def _smtp_conf() -> Optional[Dict[str, Any]]:
    """读 SMTP 配置；缺关键项则返回 None（注册功能视为未启用）。"""
    host = _env("SMTP_HOST")
    user = _env("SMTP_USER")
    password = _env("SMTP_PASSWORD")
    sender = _env("SMTP_FROM") or user
    if not (host and user and password and sender):
        return None
    try:
        port = int(_env("SMTP_PORT", "465"))
    except ValueError:
        port = 465
    return {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "from": sender,
        "from_name": _env("SMTP_FROM_NAME", "CosMac Star"),
    }


def registration_enabled() -> bool:
    """SMTP 与共享密钥都配齐才算「自建注册」可用。"""
    return _smtp_conf() is not None and bool(_env("REGISTRATION_SHARED_SECRET"))


def reset_enabled() -> bool:
    """SMTP 与管理员令牌都配齐才算「找回密码」可用（重置密码要管理员权限）。"""
    return _smtp_conf() is not None and bool(_env("ADMIN_TOKEN"))


def _build_email(code: str, kind: str = "register") -> Tuple[str, str, str]:
    """构造验证码邮件，返回 (主题, 纯文本, HTML)。kind: register（注册）/ reset（找回密码）。

    HTML 用「邮件安全」写法：表格布局 + 全内联样式（Gmail/Outlook 会剥离 <style>、不支持
    flex/grid）。抬头用**纯文字标识**（不外链图片）——邮件客户端默认不加载远程图、且跨域
    外链图会拉低投递评分（更易进垃圾箱），所以不放 logo 图。
    """
    mins = _CODE_TTL // 60
    if kind == "reset":
        subject = f"【CosMac Star】重置密码验证码 {code}"
        heading = "重置你的密码"
        intro = "你正在重置 CosMac Star 的登录密码。请在页面输入下面的验证码："
        plain = (
            f"你正在重置 CosMac Star 的登录密码。\n\n"
            f"验证码：{code}\n\n"
            f"{mins} 分钟内有效。如果这不是你本人的操作，忽略本邮件即可，密码不会被更改。"
        )
        note = "如果这不是你本人的操作，忽略本邮件即可，你的密码不会被更改。"
    else:
        subject = f"【CosMac Star】注册验证码 {code}"
        heading = "验证你的邮箱"
        intro = "你正在注册 CosMac Star。请在页面输入下面的验证码完成注册："
        plain = (
            f"你正在注册 CosMac Star。\n\n"
            f"验证码：{code}\n\n"
            f"{mins} 分钟内有效。如果这不是你本人的操作，忽略本邮件即可，账号不会有任何变化。"
        )
        note = "如果这不是你本人的操作，忽略本邮件即可，你的账号不会有任何变化。"
    html = f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"></head>
<body style="margin:0;background:#f1efe9;font-family:-apple-system,'PingFang SC',sans-serif;">
<div style="padding:32px 16px;">
<table role="presentation" cellpadding="0" cellspacing="0" border="0" align="center" style="width:100%;max-width:480px;margin:0 auto;background:#ffffff;border-radius:16px;border:1px solid #eae6df;">
<tr><td style="padding:30px 36px 8px;">
<div style="font-size:19px;font-weight:600;color:#2c2a26;letter-spacing:.3px;"><span style="color:#c96442;">✦</span>&nbsp;CosMac&nbsp;<span style="color:#c96442;">Star</span></div>
</td></tr>
<tr><td style="padding:14px 36px 0;">
<div style="font-size:20px;font-weight:600;color:#2c2a26;">{heading}</div>
<div style="font-size:14px;line-height:1.7;color:#6b665e;margin-top:10px;">{intro}</div>
</td></tr>
<tr><td style="padding:22px 36px 6px;">
<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="width:100%;background:#faece7;border:1px solid #f0d8cd;border-radius:12px;">
<tr><td align="center" style="padding:20px 12px;">
<div style="font-size:32px;font-weight:700;letter-spacing:10px;color:#993c1d;padding-left:10px;">{code}</div>
</td></tr></table>
<div style="font-size:12px;color:#8a8378;margin-top:10px;text-align:center;">验证码 {mins} 分钟内有效</div>
</td></tr>
<tr><td style="padding:14px 36px 0;">
<div style="font-size:13px;line-height:1.7;color:#8a8378;">{note}</div>
</td></tr>
<tr><td style="padding:22px 36px 28px;">
<div style="border-top:1px solid #eee9e1;padding-top:14px;font-size:12px;color:#ada699;line-height:1.6;">此邮件由系统自动发送，请勿直接回复。<br>© CosMac Star</div>
</td></tr>
</table>
</div>
</body></html>"""
    return subject, plain, html


def _smtp_send(to_addr: str, subject: str, plain: str, html: str) -> None:
    """用 SMTP（SSL/465 优先）发一封 HTML+纯文本邮件；失败抛异常由调用方兜底。"""
    conf = _smtp_conf()
    if not conf:
        raise RuntimeError("SMTP 未配置")
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((conf["from_name"], conf["from"]))
    msg["To"] = to_addr
    msg.set_content(plain)                       # 纯文本兜底（老客户端 / 不渲染 HTML 时显示）
    msg.add_alternative(html, subtype="html")    # 品牌化 HTML 正文（现代客户端显示这个）
    ctx = ssl.create_default_context()
    # 465=SSL 直连；587=STARTTLS。Lark 两个都给，这里按端口择一。
    if conf["port"] == 587:
        with smtplib.SMTP(conf["host"], conf["port"], timeout=20) as s:
            s.starttls(context=ctx)
            s.login(conf["user"], conf["password"])
            s.send_message(msg)
    else:
        with smtplib.SMTP_SSL(conf["host"], conf["port"], context=ctx, timeout=20) as s:
            s.login(conf["user"], conf["password"])
            s.send_message(msg)


def _send_email(to_addr: str, code: str) -> None:
    """发**注册**验证码邮件。"""
    _smtp_send(to_addr, *_build_email(code, "register"))


def _send_reset_email(to_addr: str, code: str) -> None:
    """发**找回密码**验证码邮件。"""
    _smtp_send(to_addr, *_build_email(code, "reset"))


def _issue_code(key: str, send: Callable[[str], None]) -> Tuple[int, Dict[str, Any]]:
    """通用「发码」：限频 + 存码 + 发信。注册/找回密码共用。send(code) 负责真正发信。"""
    now = time.time()
    with _lock:
        pc = _store.get(key) or _PendingCode()
        # 滑窗：清掉一小时前的发码记录，再判每小时上限
        pc.sent_times = [t for t in pc.sent_times if now - t < 3600]
        if pc.last_sent and now - pc.last_sent < _RESEND_COOLDOWN:
            wait = int(_RESEND_COOLDOWN - (now - pc.last_sent))
            return 429, {"error": f"发送太频繁，请 {wait} 秒后再试", "cooldown": wait}
        if len(pc.sent_times) >= _MAX_SENDS_PER_HOUR:
            return 429, {"error": "请求过于频繁，请稍后再试"}
        code = _gen_code()
        pc.code = code
        pc.expires = now + _CODE_TTL
        pc.attempts = 0
        pc.last_sent = now
        pc.sent_times.append(now)
        _store[key] = pc

    # 发信放锁外（网络 IO 可能慢，别占着锁）
    try:
        send(code)
    except Exception:
        logger.exception("发送验证码邮件失败: %s", key)
        # 发失败就把这次的码作废，避免用户拿不到码却被限频
        with _lock:
            cur = _store.get(key)
            if cur and cur.code == code:
                cur.code = ""
                if cur.sent_times:
                    cur.sent_times.pop()
                cur.last_sent = 0.0
        return 502, {"error": "验证码邮件发送失败，请稍后重试"}

    return 200, {"ok": True, "cooldown": _RESEND_COOLDOWN}


def request_code(email: str) -> Tuple[int, Dict[str, Any]]:
    """发**注册**验证码到邮箱。返回 (http状态, 响应体)。"""
    if not registration_enabled():
        return 503, {"error": "服务器未开启邮箱注册"}
    email = (email or "").strip().lower()
    if not _EMAIL_RE.match(email):
        return 400, {"error": "邮箱格式不正确"}
    return _issue_code(_key("register", email), lambda c: _send_email(email, c))


def _check_code(email: str, code: str, purpose: str = "register") -> Tuple[bool, Optional[str]]:
    """校验邮箱+码（按用途分桶）；通过返回 (True, None)，否则 (False, 错误文案)。通过即作废。"""
    code = (code or "").strip()
    with _lock:
        pc = _store.get(_key(purpose, email))
        if not pc or not pc.code:
            return False, "请先获取验证码"
        if time.time() > pc.expires:
            pc.code = ""
            return False, "验证码已过期，请重新获取"
        if pc.attempts >= _MAX_VERIFY_ATTEMPTS:
            pc.code = ""
            return False, "验证码错误次数过多，请重新获取"
        if not hmac.compare_digest(pc.code, code):
            pc.attempts += 1
            return False, "验证码不正确"
        # 验过即作废（一次性）
        pc.code = ""
        return True, None


def _synapse_register(hs_url: str, username: str, password: str) -> Tuple[int, Dict[str, Any]]:
    """用 registration_shared_secret 向 Synapse 建号（HMAC nonce 流程）。

    /_synapse/admin/v1/register：先 GET 拿 nonce，再用 HMAC-SHA1 算 mac 后 POST。
    该端点不受 enable_registration 影响，专供程序化建号。
    """
    secret = _env("REGISTRATION_SHARED_SECRET")
    if not secret:
        return 503, {"error": "服务器未配置注册密钥"}
    base = hs_url.rstrip("/")
    url = f"{base}/_synapse/admin/v1/register"
    try:
        r = requests.get(url, timeout=_HS_TIMEOUT)
        nonce = r.json().get("nonce")
        if not nonce:
            return 502, {"error": "注册服务暂不可用"}
        # mac = HMAC_SHA1(secret, nonce \0 user \0 password \0 notadmin)
        mac = hmac.new(secret.encode("utf-8"), digestmod=hashlib.sha1)
        mac.update(b"\x00".join([
            nonce.encode("utf-8"),
            username.encode("utf-8"),
            password.encode("utf-8"),
            b"notadmin",
        ]))
        body = {
            "nonce": nonce,
            "username": username,
            "password": password,
            "admin": False,
            "mac": mac.hexdigest(),
        }
        rr = requests.post(url, json=body, timeout=_HS_TIMEOUT)
        if rr.status_code == 200:
            return 200, rr.json()
        # Synapse 把"用户名已占用"等错误放在 body.error
        err = ""
        try:
            err = rr.json().get("error", "")
        except Exception:
            pass
        if "in use" in err.lower() or rr.status_code == 400 and "exist" in err.lower():
            return 409, {"error": "该用户名已被占用，请换一个"}
        return rr.status_code if rr.status_code >= 400 else 502, {"error": err or "注册失败"}
    except requests.RequestException:
        logger.exception("调用 Synapse 共享密钥注册失败")
        return 502, {"error": "注册服务暂不可用，请稍后重试"}


def verify_and_register(
    email: str, code: str, username: str, password: str, *, hs_url: str
) -> Tuple[int, Dict[str, Any]]:
    """验码 → 建号。成功返回 (200, {user_id, access_token...})。"""
    if not registration_enabled():
        return 503, {"error": "服务器未开启邮箱注册"}
    email = (email or "").strip().lower()
    username = (username or "").strip().lower()
    if not _EMAIL_RE.match(email):
        return 400, {"error": "邮箱格式不正确"}
    if not username or not _USERNAME_RE.match(username):
        return 400, {"error": "用户名只能用小写字母/数字/._-=+/"}
    if len(password or "") < 8:
        return 400, {"error": "密码至少 8 位"}

    ok, msg = _check_code(email, code, purpose="register")
    if not ok:
        return 400, {"error": msg}

    status, payload = _synapse_register(hs_url, username, password)
    # 建号成功 → 登记「邮箱→用户名」映射，供以后找回密码按邮箱定位账号。失败不阻断注册。
    if status == 200:
        try:
            from cosmac.db import session_scope
            from cosmac.db.email_repo import set_email
            with session_scope() as s:
                set_email(s, email=email, username=username)
        except Exception:
            logger.warning("登记邮箱→用户名映射失败（不影响注册）", exc_info=True)
    # 建号失败时不还原码（已一次性作废）——让用户重新走流程，避免码被复用
    return status, payload


def _lookup_username(email: str) -> Optional[str]:
    """按邮箱反查用户名 localpart（找回密码用）。查不到/出错返回 None。"""
    try:
        from cosmac.db import session_scope
        from cosmac.db.email_repo import get_username_by_email
        with session_scope() as s:
            return get_username_by_email(s, email)
    except Exception:
        logger.debug("查邮箱→用户名映射失败", exc_info=True)
        return None


def _admin_reset_password(hs_url: str, user_id: str, new_password: str) -> Tuple[int, Dict[str, Any]]:
    """用管理员令牌调 Synapse 重置某账号密码（并登出其所有设备）。

    /_synapse/admin/v1/reset_password/<user_id>：需**服务器管理员** access token
    （env COSMAC_ADMIN_TOKEN）。as_token 权限不够，故单独配一个管理员令牌。
    """
    token = _env("ADMIN_TOKEN")
    if not token:
        return 503, {"error": "服务器未配置管理员令牌"}
    base = hs_url.rstrip("/")
    url = f"{base}/_synapse/admin/v1/reset_password/{user_id}"
    try:
        rr = requests.post(
            url,
            json={"new_password": new_password, "logout_devices": True},
            headers={"Authorization": f"Bearer {token}"},
            timeout=_HS_TIMEOUT,
        )
        if rr.status_code == 200:
            return 200, {"ok": True}
        logger.warning("重置密码失败 %s: %s", rr.status_code, rr.text[:200])
        return (rr.status_code if rr.status_code >= 400 else 502), {"error": "重置失败，请稍后重试"}
    except requests.RequestException:
        logger.exception("调用 Synapse 重置密码失败")
        return 502, {"error": "重置服务暂不可用，请稍后重试"}


def reset_request_code(email: str) -> Tuple[int, Dict[str, Any]]:
    """找回密码：发验证码到邮箱。

    防邮箱枚举：无论该邮箱是否注册都返回成功，只有**确实注册过**才真正发信。
    """
    if not reset_enabled():
        return 503, {"error": "服务器未开启密码找回"}
    email = (email or "").strip().lower()
    if not _EMAIL_RE.match(email):
        return 400, {"error": "邮箱格式不正确"}
    if not _lookup_username(email):
        # 不泄露"该邮箱有没有注册"，不发信但照样回成功
        return 200, {"ok": True, "cooldown": _RESEND_COOLDOWN}
    return _issue_code(_key("reset", email), lambda c: _send_reset_email(email, c))


def reset_verify(
    email: str, code: str, new_password: str, *, hs_url: str, server_name: str
) -> Tuple[int, Dict[str, Any]]:
    """找回密码：验码 → 重置该邮箱对应账号的密码。成功返回 (200, {ok})。"""
    if not reset_enabled():
        return 503, {"error": "服务器未开启密码找回"}
    email = (email or "").strip().lower()
    if not _EMAIL_RE.match(email):
        return 400, {"error": "邮箱格式不正确"}
    if len(new_password or "") < 8:
        return 400, {"error": "新密码至少 8 位"}

    ok, msg = _check_code(email, code, purpose="reset")
    if not ok:
        return 400, {"error": msg}

    username = _lookup_username(email)
    if not username:
        return 400, {"error": "该邮箱未注册"}
    user_id = f"@{username}:{server_name}"
    return _admin_reset_password(hs_url, user_id, new_password)
