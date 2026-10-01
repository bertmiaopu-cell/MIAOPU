"""转人工通知 + 关键词拦截停用 的自测脚本

不依赖 pytest，直接运行即可：

    python tests/test_transfer_notify.py

以 test_ 开头的函数也会被 pytest 正常收集。
"""
from __future__ import annotations

import asyncio
import smtplib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ==========================================================================
# 一、邮件通知模块
# ==========================================================================
def test_split_recipients():
    from service.transfer_notify import _split_recipients

    assert _split_recipients("") == []
    assert _split_recipients("a@qq.com") == ["a@qq.com"]
    assert _split_recipients("a@qq.com,b@139.com") == ["a@qq.com", "b@139.com"]
    assert _split_recipients("a@qq.com；b@139.com") == ["a@qq.com", "b@139.com"]
    assert _split_recipients("a@qq.com; a@qq.com") == ["a@qq.com"]
    print("  [OK] 收件人解析（逗号/分号/去重）")


def test_render_body_contains_reason_and_message():
    from service.transfer_notify import _render_body

    body = _render_body(
        reason="退货流程需要人工处理",
        customer_message="我想了解下退货流程",
        shop_name="祥和金属雕花外墙板",
        shop_id=274507345,
        user_id=145908542,
        session_id="conversation_abc",
        trigger="AI 判断需要人工接管",
    )
    for expected in ["需要人工接手", "退货流程需要人工处理", "我想了解下退货流程",
                     "祥和金属雕花外墙板", "274507345", "conversation_abc",
                     "AI 判断需要人工接管"]:
        assert expected in body, f"邮件正文缺少 {expected!r}"
    print("  [OK] 邮件正文包含「转人工原因 + 客户原话 + 店铺/会话信息」")


def test_render_body_can_hide_customer_message():
    from service.transfer_notify import _render_body

    body = _render_body(
        reason="r", customer_message="客户原话", shop_name="s",
        shop_id=1, user_id=2, session_id="x", trigger="t",
        customer_message_enabled=False,
    )
    assert "客户原话" not in body
    print("  [OK] 关掉「附带客户原话」后正文里确实没有客户消息")


def test_send_mail_missing_config_is_rejected():
    from service.transfer_notify import _send_mail

    ok, detail = _send_mail({"sender_email": "", "auth_code": "",
                             "recipient_email": "", "smtp_host": "smtp.qq.com"},
                            "s", "b")
    assert ok is False
    assert "配置不完整" in detail
    print("  [OK] 配置不全时明确报错，不抛异常")


def test_send_mail_success_with_fake_smtp():
    """用假的 SMTP 替身验证：登录 + 发信 + 退出都被正确调用。"""
    from service import transfer_notify as tn

    calls = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout=None, context=None):
            calls["host"] = host
            calls["port"] = port

        def login(self, user, code):
            calls["login"] = (user, code)

        def sendmail(self, sender, recipients, payload):
            calls["sendmail"] = (sender, recipients)
            calls["payload"] = payload

        def quit(self):
            calls["quit"] = True

    original = tn.smtplib.SMTP_SSL
    tn.smtplib.SMTP_SSL = FakeSMTP
    try:
        ok, detail = tn._send_mail(
            {"sender_email": "me@qq.com", "auth_code": "abcd1234",
             "recipient_email": "13800000000@139.com", "smtp_host": "smtp.qq.com",
             "smtp_port": 465, "timeout": 10},
            "主题", "正文",
        )
    finally:
        tn.smtplib.SMTP_SSL = original

    assert ok is True, detail
    assert calls["host"] == "smtp.qq.com" and calls["port"] == 465
    assert calls["login"] == ("me@qq.com", "abcd1234")
    assert calls["sendmail"][1] == ["13800000000@139.com"]
    assert calls["quit"] is True
    # 主题用 MIME 编码，正文原样带上
    assert "主题" in calls["payload"] or "=?utf-8?" in calls["payload"]
    print("  [OK] 假 SMTP 下发送链路正确（登录/收件人/退出）")


def test_auth_error_message_is_actionable():
    from service import transfer_notify as tn

    class FakeSMTP:
        def __init__(self, *a, **k):
            pass

        def login(self, *a, **k):
            raise smtplib.SMTPAuthenticationError(535, b"bad auth")

        def quit(self):
            pass

    original = tn.smtplib.SMTP_SSL
    tn.smtplib.SMTP_SSL = FakeSMTP
    try:
        ok, detail = tn._send_mail(
            {"sender_email": "me@qq.com", "auth_code": "wrong",
             "recipient_email": "a@b.com", "smtp_host": "smtp.qq.com",
             "smtp_port": 465, "timeout": 10},
            "s", "b",
        )
    finally:
        tn.smtplib.SMTP_SSL = original

    assert ok is False
    assert "授权码" in detail
    print("  [OK] 认证失败时提示「是不是把密码当授权码填了」")


def test_describe_status_three_states():
    from service import transfer_notify as tn

    original = tn.get_notify_config

    tn.get_notify_config = lambda: {"enabled": False}
    assert "未启用" in tn.describe_status()

    tn.get_notify_config = lambda: {"enabled": True, "sender_email": "",
                                    "auth_code": "", "recipient_email": "",
                                    "smtp_host": "smtp.qq.com"}
    assert "配置不完整" in tn.describe_status()

    tn.get_notify_config = lambda: {"enabled": True, "sender_email": "a@qq.com",
                                    "auth_code": "x", "recipient_email": "b@139.com",
                                    "smtp_host": "smtp.qq.com"}
    assert "b@139.com" in tn.describe_status()

    tn.get_notify_config = original
    print("  [OK] 启动状态描述覆盖「未启用 / 配置不完整 / 已启用」三种情况")


def test_notify_transfer_skipped_when_disabled():
    from service import transfer_notify as tn

    # 未启用时不应该尝试发信
    original_cfg = tn.get_notify_config
    original_ssl = tn.smtplib.SMTP_SSL
    tn.get_notify_config = lambda: {"enabled": False}
    tn.smtplib.SMTP_SSL = lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("未启用时不应该发信")
    )
    try:
        assert tn.notify_transfer(reason="r") is False
    finally:
        tn.get_notify_config = original_cfg
        tn.smtplib.SMTP_SSL = original_ssl
    print("  [OK] 未启用时 notify_transfer 直接返回 False，不发信")


# ==========================================================================
# 二、Agent 循环里的转人工钩子
# ==========================================================================
class _FakeFn:
    def __init__(self, name):
        self.name = name


class _FakeToolCall:
    def __init__(self, name):
        self.function = _FakeFn(name)


class _FakeResult:
    def __init__(self, content):
        self.content = content


def _make_agent_without_init():
    from Agent.CustomerAgent.custom.customer_agent import CustomerAgent
    return CustomerAgent.__new__(CustomerAgent)


def test_hook_fires_on_successful_transfer():
    from service import transfer_notify as tn

    captured = {}
    original = tn.notify_transfer

    def fake_notify(**kwargs):
        captured.update(kwargs)
        return True

    tn.notify_transfer = fake_notify
    try:
        agent = _make_agent_without_init()
        asyncio.run(agent._notify_if_transferred(
            [_FakeToolCall("transfer_conversation")],
            [_FakeResult("会话转接成功")],
            "亲，这个问题要人工帮您处理，我帮您转接同事～",
            query="我想了解下退货流程",
            dependencies={"shop_id": 274507345, "user_id": 145908542,
                          "shop_name": "祥和金属雕花外墙板"},
            session_id="conversation_abc",
        ))
    finally:
        tn.notify_transfer = original

    assert captured["reason"] == "亲，这个问题要人工帮您处理，我帮您转接同事～"
    assert captured["customer_message"] == "我想了解下退货流程"
    assert captured["shop_id"] == 274507345
    assert captured["session_id"] == "conversation_abc"
    print("  [OK] 转接成功 → 带「原因 + 客户原话」触发通知")


def test_hook_silent_when_not_transferring():
    from service import transfer_notify as tn

    called = []
    original = tn.notify_transfer
    tn.notify_transfer = lambda **k: called.append(k)
    try:
        agent = _make_agent_without_init()
        asyncio.run(agent._notify_if_transferred(
            [_FakeToolCall("search_customer_service_knowledge")],
            [_FakeResult("未找到相关知识。")],
            "答案",
            query="q", dependencies={}, session_id="s",
        ))
    finally:
        tn.notify_transfer = original
    assert called == []
    print("  [OK] 没有调用转接工具时不发通知")


def test_hook_silent_when_transfer_failed():
    from service import transfer_notify as tn

    called = []
    original = tn.notify_transfer
    tn.notify_transfer = lambda **k: called.append(k)
    try:
        agent = _make_agent_without_init()
        asyncio.run(agent._notify_if_transferred(
            [_FakeToolCall("transfer_conversation")],
            [_FakeResult("转接失败：无法获取客服列表")],
            "转人工",
            query="q", dependencies={}, session_id="s",
        ))
    finally:
        tn.notify_transfer = original
    assert called == []
    print("  [OK] 转接失败时不发通知")


def test_hook_never_raises():
    """通知炸了也不能影响给买家的回复。"""
    from service import transfer_notify as tn

    original = tn.notify_transfer

    def boom(**kwargs):
        raise RuntimeError("模拟邮件服务器挂了")

    tn.notify_transfer = boom
    try:
        agent = _make_agent_without_init()
        asyncio.run(agent._notify_if_transferred(
            [_FakeToolCall("transfer_conversation")],
            [_FakeResult("会话转接成功")],
            "r", query="q", dependencies={}, session_id="s",
        ))
    finally:
        tn.notify_transfer = original
    print("  [OK] 通知内部异常被吞掉，不会影响回复")


# ==========================================================================
# 三、关键词拦截已停用
# ==========================================================================
class _FakeContext:
    def __init__(self, content, ctype="text"):
        self.content = content
        self.type = ctype


def test_keyword_intercept_disabled():
    from Message.handlers import keyword_handler as kh

    assert kh.KEYWORD_INTERCEPT_ENABLED is False, "关键词拦截应当是停用状态"
    assert "\x00" in kh._NEVER_MATCH_KEYWORD

    handler = kh.KeywordDetectionHandler(
        business_hours={"start": "00:00", "end": "23:59"}
    )
    assert handler.keywords == {kh._NEVER_MATCH_KEYWORD}, "停用后不应加载真实关键词"

    for text in ["我要转人工", "投诉", "退款", "破损了", "找客服",
                 "12315", "差评", "我要退货", "转真人", ""]:
        assert handler.can_handle(_FakeContext(text)) is False, \
            f"停用后不该被 {text!r} 命中"
    print("  [OK] 关键词拦截已停用：转人工/投诉/退款等一律不再拦截")


def main():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    print(f"共 {len(tests)} 项测试\n")
    failed = []
    for fn in tests:
        try:
            fn()
        except Exception as e:
            failed.append((fn.__name__, e))
            print(f"  [失败] {fn.__name__}: {type(e).__name__}: {e}")
    print()
    if failed:
        print(f"❌ {len(failed)}/{len(tests)} 项失败")
        return 1
    print(f"✅ 全部通过（{len(tests)} 项）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
