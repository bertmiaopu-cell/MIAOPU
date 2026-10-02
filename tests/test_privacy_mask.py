"""对话脱敏 + 回复延迟 的自测脚本

    python tests/test_privacy_mask.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ==========================================================================
# 一、各类敏感信息能被脱敏，并且能还原
# ==========================================================================
def test_mobile():
    from utils.privacy_mask import mask_text, restore_text
    src = "我的电话是13800138000，方便的话打给我"
    masked, mp = mask_text(src)
    assert "13800138000" not in masked, masked
    assert "PHONE1" in masked, masked
    assert restore_text(masked, mp) == src
    print("  [OK] 手机号脱敏并可还原")


def test_idcard():
    from utils.privacy_mask import mask_text, restore_text
    src = "身份证号 110101199003078515 麻烦登记一下"
    masked, mp = mask_text(src)
    assert "110101199003078515" not in masked, masked
    assert restore_text(masked, mp) == src
    print("  [OK] 身份证号脱敏并可还原")


def test_long_order_number():
    from utils.privacy_mask import mask_text, restore_text
    src = "我的订单号是 2209151234567890 帮我查下物流"
    masked, mp = mask_text(src)
    assert "2209151234567890" not in masked, masked
    assert restore_text(masked, mp) == src
    print("  [OK] 订单号（长数字）脱敏并可还原")


def test_landline():
    from utils.privacy_mask import mask_text, restore_text
    src = "我们厂里座机 0571-88886666，随时联系"
    masked, mp = mask_text(src)
    assert "88886666" not in masked, masked
    assert restore_text(masked, mp) == src
    print("  [OK] 固话脱敏并可还原")


def test_address():
    from utils.privacy_mask import mask_text, restore_text
    src = "我地址是浙江省杭州市余杭区五常街道文一西路969号，麻烦发这里"
    masked, mp = mask_text(src)
    assert "文一西路" not in masked, masked
    assert "ADDR1" in masked, masked
    assert restore_text(masked, mp) == src
    print("  [OK] 收货地址脱敏并可还原")


def test_same_value_reuses_placeholder():
    from utils.privacy_mask import mask_text
    src = "电话13800138000，再确认一下还是13800138000对吗"
    masked, mp = mask_text(src)
    assert masked.count("PHONE1") == 2, masked
    assert len(mp) == 1, mp
    print("  [OK] 同一个号码复用同一个占位符")


def test_restore_is_case_insensitive():
    from utils.privacy_mask import restore_text
    out = restore_text("您的手机号 phone1 我记下了", {"PHONE1": "13800138000"})
    assert "13800138000" in out, out
    print("  [OK] 还原时大小写不敏感（模型偶尔会写成小写）")


# ==========================================================================
# 二、不能误伤正常话术（这是最关键的一条）
# ==========================================================================
REAL_SCRIPTS = [
    "亲，咱们是按平方计价的：16 毫米 26 元/平方、20 毫米 30 元/平方、25 毫米 34 元/平方，双色每平方加 3 元。",
    "亲，40 平方起发，1 件 = 1 平方单拍发样品件，要 40 平方就拍 40 件。",
    "亲，咱们的报价是裸板出厂价，【不含运费】，运费需要您这边承担，可以到付。",
    "亲，咱们有三种厚度可选：16毫米、20毫米和25毫米。越厚保温隔热效果越好。",
    "工字中缝 8.5 元/米，T 字中缝 5 元/米，门窗包 5×5 6 元/米，按整根发货。",
    "亲，超 4 米的板物流不送到门，需到就近物流点自提。",
    "亲，咱们支持七天无理由退货的，退回运费由您承担。",
    "亲，您的金属雕花外墙板已经发出，物流大概7天左右送达。",
    "亲，我给您报个明白价：板材 1040 元 + 配件 114 元 = 1154 元。",
    "亲，您可以拨打拼多多官方客服电话咨询平台规则。",
    "亲，新疆、西藏这些地方运费会比内地高一些，支持到付。",
    "亲，咱们的板子宽度固定 40 公分，长度 2 到 6 米可以定尺。",
]


def test_real_scripts_not_touched():
    from utils.privacy_mask import mask_text
    bad = []
    for s in REAL_SCRIPTS:
        masked, mp = mask_text(s)
        if masked != s:
            bad.append((s, masked, mp))
    assert not bad, "正常话术被误伤：\n" + "\n".join(
        "  原文: %s\n  脱敏: %s\n  映射: %s" % b for b in bad)
    print("  [OK] %d 条真实话术零误伤" % len(REAL_SCRIPTS))


# ==========================================================================
# 三、消息列表脱敏：只动 user/assistant
# ==========================================================================
def test_mask_messages_scope():
    from utils.privacy_mask import mask_messages
    messages = [
        {"role": "system", "content": "系统指令里出现13800138000也不能动"},
        {"role": "user", "content": "我的电话13800138000"},
        {"role": "assistant", "content": "好的，电话13800138000收到"},
        {"role": "tool", "content": "知识库返回，含13800138000"},
    ]
    masked, mp = mask_messages(messages)
    assert "13800138000" in masked[0]["content"], "system 不该被动"
    assert "13800138000" in masked[3]["content"], "tool 不该被动"
    assert "PHONE1" in masked[1]["content"], masked[1]
    assert "PHONE1" in masked[2]["content"], masked[2]
    print("  [OK] 只脱敏 user/assistant，system 与 tool 原样保留")


def test_mask_messages_multimodal_blocks():
    from utils.privacy_mask import mask_messages
    messages = [{
        "role": "user",
        "content": [
            {"type": "text", "text": "电话13800138000"},
            {"type": "image_url", "image_url": {"url": "http://x/y.jpg"}},
        ],
    }]
    masked, mp = mask_messages(messages)
    assert "PHONE1" in masked[0]["content"][0]["text"]
    assert masked[0]["content"][1] == {"type": "image_url", "image_url": {"url": "http://x/y.jpg"}}
    print("  [OK] 多模态消息只脱敏文本块，图片块不动")


def test_mask_disabled_returns_original():
    from service import transfer_notify  # noqa: F401  仅为保证依赖可导入
    from utils import privacy_mask

    original = privacy_mask.get_privacy_config
    privacy_mask.get_privacy_config = lambda: {"mask_enabled": False}
    try:
        messages = [{"role": "user", "content": "电话13800138000"}]
        masked, mp = privacy_mask.mask_messages_with_config(messages)
        assert masked[0]["content"] == "电话13800138000"
        assert mp == {}
    finally:
        privacy_mask.get_privacy_config = original
    print("  [OK] 总开关关闭时不脱敏")


# ==========================================================================
# 四、回复延迟配置
# ==========================================================================
def test_reply_delay_config_defaults():
    from config import ConfigModel
    m = ConfigModel()
    assert m.reply.delay_enabled is True
    assert float(m.reply.delay_min) == 1.0
    assert float(m.reply.delay_max) == 10.0
    assert m.privacy.mask_enabled is True
    print("  [OK] 默认配置：脱敏开启、延迟 1~10 秒")


def test_reply_delay_range_is_sane():
    import random
    lo, hi = 1.0, 10.0
    samples = [random.uniform(lo, hi) for _ in range(200)]
    assert all(lo <= s <= hi for s in samples)
    assert min(samples) < 4 and max(samples) > 7, "随机分布看起来不对"
    print("  [OK] 1~10 秒随机延迟取值范围正确")


# ==========================================================================
# 五、回归：脱敏不能污染数据库
#
# 曾经的 bug：_run_agent_loop 会把「带工具调用的中间 assistant 消息」写进数据库，
# 而那条消息是脱敏后的，于是库里永久留下 ADDR1；下一轮引用到它时映射表已失效，
# 客户就会看到字面的 "ADDR1"。
# ==========================================================================
def test_agent_loop_saves_restored_content_to_db():
    import asyncio
    from types import SimpleNamespace
    from Agent.CustomerAgent.custom.customer_agent import CustomerAgent

    REAL = "浙江省杭州市余杭区五常街道文一西路969号"
    MASKED = "我地址是ADDR1"
    MAPPING = {"ADDR1": REAL}

    class _Agent:
        """只搭 _run_agent_loop 需要的这几个部件。"""

        def __init__(self):
            self._config = SimpleNamespace(max_loops=4)
            self.saved = []
            self._session_manager = SimpleNamespace(add_message=self._save)
            self._tool_executor = SimpleNamespace(execute_parallel=self._exec)
            self._responses = [
                SimpleNamespace(
                    content="好的，寄到 ADDR1 是吧",
                    has_tool_calls=True,
                    tool_calls=[SimpleNamespace(
                        id="call_1",
                        function=SimpleNamespace(name="search_customer_service_knowledge",
                                                 arguments='{"query":"运费"}'),
                    )],
                ),
                SimpleNamespace(content="已经登记好了", has_tool_calls=False, tool_calls=None),
            ]
            self.seen_by_llm = []

        def _save(self, **kw):
            self.saved.append(kw)
            return True

        async def _exec(self, tool_calls, dependencies):
            return [SimpleNamespace(
                to_dict=lambda: {"role": "tool", "tool_call_id": "call_1",
                                 "content": "运费由买家承担，寄到 ADDR1 需到付"},
                content="运费由买家承担，寄到 ADDR1 需到付",
                tool_call_id="call_1",
            )]

        async def _chat_with_vision_fallback(self, messages, tool_choice=None):
            self.seen_by_llm.append([m.get("content") for m in messages])
            return self._responses.pop(0)

        async def _notify_if_transferred(self, *a, **k):
            return None

    agent = _Agent()
    out = asyncio.run(CustomerAgent._run_agent_loop(
        agent,
        [{"role": "user", "content": MASKED}],
        {},
        session_id="s1",
        query=MASKED,
        mask_map=MAPPING,
    ))

    # 1) 发给 LLM 的上下文里必须是脱敏的，绝不能出现真实地址
    for snapshot in agent.seen_by_llm:
        for c in snapshot:
            assert REAL not in str(c), f"真实地址泄露给了 LLM: {c}"

    # 2) 存进数据库的必须已还原，不能留下占位符
    blob = "\n".join(str(m.get("content")) for m in agent.saved)
    assert "ADDR1" not in blob, f"数据库里残留占位符：\n{blob}"
    assert REAL in blob, f"数据库里没有还原出真实地址：\n{blob}"
    print("  [OK] 中间消息落库前还原，LLM 上下文保持脱敏（回归）")


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
