"""转人工邮件通知服务

买家咨询被转接给人工客服时，通过 QQ 邮箱把通知发到商家的手机邮箱，
避免"AI 说了转人工、商家却不知道"导致客户干等。

设计要点：
* 纯标准库（smtplib / email），不引入新依赖，打包体积不变；
* 配置全部来自 config.json 的 ``notify`` 段，UI 里可改；
* 发送是同步阻塞的 HTTP/SMTP 调用，调用方必须放到工作线程
  （``asyncio.to_thread``），不要直接阻塞事件循环；
* 任何失败都只记日志、不抛异常——通知失败绝不能影响给买家的回复。
"""
from __future__ import annotations

import smtplib
import ssl
from datetime import datetime
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr
from typing import Any, Dict, List, Optional, Tuple

from config import config
from utils.logger_loguru import get_logger

logger = get_logger("TransferNotify")


# --------------------------------------------------------------------------
# 默认值：即使 config.json 里还没有 notify 段也能正常工作
# --------------------------------------------------------------------------
DEFAULTS: Dict[str, Any] = {
    "enabled": False,
    "smtp_host": "smtp.qq.com",
    "smtp_port": 465,
    "sender_email": "",
    "auth_code": "",
    "recipient_email": "",
    "include_customer_message": True,
    "timeout": 20,
}


def get_notify_config() -> Dict[str, Any]:
    """读取通知配置（config.json 没有 notify 段时回落到默认值）。"""
    raw = config.get("notify", {}) or {}
    if not isinstance(raw, dict):
        raw = {}
    merged = dict(DEFAULTS)
    merged.update({k: v for k, v in raw.items() if v is not None})
    return merged


def _split_recipients(value: str) -> List[str]:
    """接收邮箱支持写多个，用逗号 / 分号 / 空格分隔。"""
    if not value:
        return []
    out: List[str] = []
    for chunk in str(value).replace("；", ";").replace("，", ",").replace(";", ",").split(","):
        for part in chunk.split():
            part = part.strip()
            if part and part not in out:
                out.append(part)
    return out


def _missing_fields(cfg: Dict[str, Any]) -> List[str]:
    need = {
        "sender_email": "发件 QQ 邮箱",
        "auth_code": "QQ 邮箱授权码",
        "recipient_email": "接收通知的邮箱",
        "smtp_host": "SMTP 服务器",
    }
    return [label for key, label in need.items() if not str(cfg.get(key) or "").strip()]


# --------------------------------------------------------------------------
# 邮件正文
# --------------------------------------------------------------------------
def _render_body(
    *,
    reason: str,
    customer_message: str,
    shop_name: str,
    shop_id: Any,
    user_id: Any,
    session_id: str,
    trigger: str,
    customer_message_enabled: bool = True,
) -> str:
    lines = [
        "【需要人工接手】",
        "",
        f"时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"店铺：{shop_name or '（未知）'}"
        + (f"（{shop_id}）" if shop_id else ""),
        f"触发方式：{trigger}",
    ]
    if session_id:
        lines.append(f"会话：{session_id}")

    lines += [
        "",
        "─── AI 请求人工接管的原因 ───",
        (reason or "（AI 没有给出文字说明，只发起了转接）").strip(),
    ]

    if customer_message_enabled:
        lines += [
            "",
            "─── 客户最后说的话 ───",
            (customer_message or "（未取到客户消息）").strip(),
        ]

    lines += [
        "",
        "─────────────────────────",
        "请尽快到拼多多商家后台接待该客户。",
        "",
        "（本邮件由 AI 客服助手自动发出，回复本邮件无效）",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------
# 发送
# --------------------------------------------------------------------------
def _send_mail(
    cfg: Dict[str, Any],
    subject: str,
    body: str,
) -> Tuple[bool, str]:
    """真正发信，返回 (是否成功, 说明/错误)。"""
    missing = _missing_fields(cfg)
    if missing:
        return False, "配置不完整，缺少：" + "、".join(missing)

    recipients = _split_recipients(cfg.get("recipient_email", ""))
    if not recipients:
        return False, "接收通知的邮箱为空"

    sender = str(cfg.get("sender_email")).strip()
    auth_code = str(cfg.get("auth_code")).strip()
    host = str(cfg.get("smtp_host")).strip() or "smtp.qq.com"
    try:
        port = int(cfg.get("smtp_port") or 465)
    except (TypeError, ValueError):
        port = 465
    try:
        timeout = int(cfg.get("timeout") or 20)
    except (TypeError, ValueError):
        timeout = 20

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = formataddr((str(Header("AI客服助手", "utf-8")), sender))
    msg["To"] = ", ".join(recipients)

    try:
        context = ssl.create_default_context()
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=timeout, context=context)
        else:
            server = smtplib.SMTP(host, port, timeout=timeout)
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
        try:
            server.login(sender, auth_code)
            server.sendmail(sender, recipients, msg.as_string())
        finally:
            try:
                server.quit()
            except Exception:
                pass
        return True, "已发送至 " + "、".join(recipients)
    except smtplib.SMTPAuthenticationError:
        # 最常见：把邮箱登录密码当成授权码填了
        return False, "SMTP 认证失败：请确认填的是「授权码」而不是 QQ 密码"
    except smtplib.SMTPException as e:
        return False, f"SMTP 错误：{type(e).__name__}: {e}"
    except (OSError, ssl.SSLError) as e:
        return False, f"网络错误：{type(e).__name__}: {e}"
    except Exception as e:  # pragma: no cover - 兜底，绝不外抛
        return False, f"未知错误：{type(e).__name__}: {e}"


# --------------------------------------------------------------------------
# 对外接口
# --------------------------------------------------------------------------
def notify_transfer(
    *,
    reason: str = "",
    customer_message: str = "",
    shop_name: str = "",
    shop_id: Any = None,
    user_id: Any = None,
    session_id: str = "",
    trigger: str = "AI 判断需要人工接管",
) -> bool:
    """转人工时发通知。同步阻塞，调用方请放工作线程。

    Returns: 是否真的发出去了（未启用 / 未配置都返回 False）。
    """
    cfg = get_notify_config()
    if not cfg.get("enabled"):
        logger.debug("转人工邮件通知未启用，跳过")
        return False

    subject = "⚠️ 需要人工接手 - AI 客服转人工提醒"
    body = _render_body(
        reason=reason,
        customer_message=customer_message,
        shop_name=shop_name,
        shop_id=shop_id,
        user_id=user_id,
        session_id=session_id,
        trigger=trigger,
        customer_message_enabled=bool(cfg.get("include_customer_message", True)),
    )

    ok, detail = _send_mail(cfg, subject, body)
    if ok:
        logger.info(f"转人工通知已发送: {detail}")
    else:
        logger.warning(f"转人工通知发送失败: {detail}")
    return ok


def send_test_email() -> Tuple[bool, str]:
    """UI 上的「发送测试邮件」按钮。同步阻塞，调用方请放工作线程。"""
    cfg = get_notify_config()
    body = _render_body(
        reason="这是一封测试邮件。看到它就说明转人工提醒已经打通了。",
        customer_message="（测试）客户：我要 60 方大概多少钱",
        shop_name="（测试）",
        shop_id=None,
        user_id=None,
        session_id="test-session",
        trigger="手动测试",
        customer_message_enabled=True,
    )
    return _send_mail(cfg, "【测试】AI 客服转人工提醒", body)


def describe_status() -> str:
    """给启动日志用的一句话状态说明。"""
    cfg = get_notify_config()
    if not cfg.get("enabled"):
        return "转人工邮件通知未启用（可在「转人工通知」页面开启）"
    missing = _missing_fields(cfg)
    if missing:
        return "转人工邮件通知已启用，但配置不完整，缺少：" + "、".join(missing)
    return ("转人工邮件通知已启用：AI 请求人工接管时会把原因和客户原话发到 "
            + str(cfg.get("recipient_email")))
