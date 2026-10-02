"""对话脱敏：发给大模型之前，把客户隐私信息替换成占位符；回复时再还原。

背景
----
拼多多《不当获取/使用信息处理规则》2.2(7) 明确禁止把「他人信息」披露或传输给
非平台认可的服务商。本应用在回复时会调用云端 LLM（如 DeepSeek），客户消息里的
手机号、地址、订单号会**原样发出去**。作者只在日志层做了脱敏，请求内容没有。

做法
----
* 出站（发给 LLM 前）：把敏感片段替换成 ``PHONE1`` / ``ADDR1`` 这类占位符，
  原值保存在本次请求的映射表里；
* 入站（回复客户前）：把占位符换回原值。
* 映射表只存在于单次请求的内存中，不落盘。

注意：这是**降低风险**，不是"合规通行证"。真要做到完全合规，应走拼多多开放平台
的官方接口。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------- 正则
# 手机号：1 开头 11 位，前后不能再接数字（避免从长数字里截一半）
RE_MOBILE = re.compile(r'(?<!\d)1[3-9]\d{9}(?!\d)')
# 身份证：18 位，末位可为 X
RE_IDCARD = re.compile(r'(?<!\d)\d{17}[\dXx](?!\d)')
# 固话：区号 + 7~8 位
RE_LANDLINE = re.compile(r'(?<!\d)0\d{2,3}[- ]?\d{7,8}(?!\d)')
# 长数字：订单号 / 银行卡 / 快递单号
RE_LONGNUM = re.compile(r'(?<!\d)\d{12,20}(?!\d)')

# 地址关键词（用于启发式判断一个片段是不是地址）
ADDR_KEYS = (
    '省', '自治区', '市', '区', '县', '镇', '乡', '街道', '路', '街', '巷',
    '村', '组', '小区', '大厦', '广场', '号', '栋', '幢', '单元', '室', '楼',
)
# 片段切分：中英文标点、空白都算边界（保留分隔符，方便原样拼回）
RE_SPLIT = re.compile(r'([，。！？；：、,.!?;:\s\n\r\t（）()\[\]【】“”"]+)')

# 各类占位符前缀
TAG_MOBILE = 'PHONE'
TAG_IDCARD = 'IDCARD'
TAG_LANDLINE = 'TEL'
TAG_LONGNUM = 'ORDER'
TAG_ADDR = 'ADDR'


class _Masker:
    """一次脱敏过程的状态：同一原值复用同一个占位符。"""

    def __init__(self):
        self.mapping: Dict[str, str] = {}   # placeholder -> 原值
        self.by_value: Dict[str, str] = {}  # 原值 -> placeholder
        self.counter: Dict[str, int] = {}

    def ph(self, tag: str, value: str) -> str:
        if value in self.by_value:
            return self.by_value[value]
        self.counter[tag] = self.counter.get(tag, 0) + 1
        placeholder = '%s%d' % (tag, self.counter[tag])
        self.mapping[placeholder] = value
        self.by_value[value] = placeholder
        return placeholder


# 向左扩展时的停止字符：这些字前面通常是主语/动词，不该并进地址
ADDR_STOP_CHARS = set('是我您的你在到发寄送要需给请和与把将了这那你我他她它们有个没')


def _mask_address_segments(text: str, m: _Masker) -> str:
    """按片段判断，把"像地址"的那一段替换掉。

    先定位第一个地址关键词（省/市/区/号…），再向左回退几个汉字，把"浙江省"
    这类前缀一并带上，避免出现「浙江ADDR1」这种半截结果。
    """
    parts = RE_SPLIT.split(text)
    for i, part in enumerate(parts):
        if not part or RE_SPLIT.fullmatch(part):
            continue
        pos = -1
        for key in ADDR_KEYS:
            idx = part.find(key)
            if idx != -1 and (pos == -1 or idx < pos):
                pos = idx
        if pos == -1:
            continue

        # 向左回退：把地名前缀（如"浙江"）一并纳入
        start = pos
        steps = 0
        while (start > 0 and steps < 6
               and '\u4e00' <= part[start - 1] <= '\u9fff'
               and part[start - 1] not in ADDR_STOP_CHARS):
            start -= 1
            steps += 1

        candidate = part[start:]
        if len(candidate) < 6:
            continue
        parts[i] = part[:start] + m.ph(TAG_ADDR, candidate)
    return ''.join(parts)


def mask_text(text: str, *, mobile=True, idcard=True, landline=True,
              longnum=True, address=True) -> Tuple[str, Dict[str, str]]:
    """脱敏一段文本，返回 (脱敏后文本, 映射表)。"""
    if not isinstance(text, str) or not text:
        return text, {}

    m = _Masker()
    out = text
    # 顺序很重要：先长后短，身份证在长数字之前，手机号在长数字之前
    if idcard:
        out = RE_IDCARD.sub(lambda mo: m.ph(TAG_IDCARD, mo.group()), out)
    if mobile:
        out = RE_MOBILE.sub(lambda mo: m.ph(TAG_MOBILE, mo.group()), out)
    if landline:
        out = RE_LANDLINE.sub(lambda mo: m.ph(TAG_LANDLINE, mo.group()), out)
    if longnum:
        out = RE_LONGNUM.sub(lambda mo: m.ph(TAG_LONGNUM, mo.group()), out)
    if address:
        out = _mask_address_segments(out, m)
    return out, m.mapping


def restore_text(text: str, mapping: Optional[Dict[str, str]]) -> str:
    """把占位符换回原值。找不到映射时原样返回。"""
    if not text or not mapping:
        return text
    out = text
    # 大小写不敏感：模型偶尔会把 PHONE1 写成 phone1
    for placeholder, original in mapping.items():
        out = re.sub(re.escape(placeholder), lambda _m, v=original: v, out, flags=re.IGNORECASE)
    return out


def mask_messages(messages: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    """脱敏一整轮对话消息。

    只处理 user / assistant 的文本内容；system（含本应用自己的指令）和 tool
    （知识库、商品信息）保持原样，避免破坏提示词和工具协议。
    图片块不动。
    """
    mapping: Dict[str, str] = {}
    if not messages:
        return messages, mapping

    out: List[Dict[str, Any]] = []
    for msg in messages:
        if not isinstance(msg, dict) or msg.get('role') not in ('user', 'assistant'):
            out.append(msg)
            continue
        content = msg.get('content')
        if isinstance(content, str):
            masked, mp = mask_text(content)
            mapping.update(mp)
            new_msg = dict(msg)
            new_msg['content'] = masked
            out.append(new_msg)
        elif isinstance(content, list):
            new_blocks = []
            for block in content:
                if isinstance(block, dict) and block.get('type') == 'text':
                    masked, mp = mask_text(str(block.get('text', '')))
                    mapping.update(mp)
                    new_block = dict(block)
                    new_block['text'] = masked
                    new_blocks.append(new_block)
                else:
                    new_blocks.append(block)
            new_msg = dict(msg)
            new_msg['content'] = new_blocks
            out.append(new_msg)
        else:
            out.append(msg)
    return out, mapping


# ---------------------------------------------------------------- 配置读取
DEFAULTS: Dict[str, Any] = {
    'mask_enabled': True,
    'mask_mobile': True,
    'mask_idcard': True,
    'mask_landline': True,
    'mask_long_number': True,
    'mask_address': True,
}


def get_privacy_config() -> Dict[str, Any]:
    from config import config
    raw = config.get('privacy', {}) or {}
    if not isinstance(raw, dict):
        raw = {}
    merged = dict(DEFAULTS)
    merged.update({k: v for k, v in raw.items() if v is not None})
    return merged


def mask_messages_with_config(messages: List[Dict[str, Any]]):
    """按 config.json 的 privacy 段执行脱敏；未启用时原样返回。"""
    cfg = get_privacy_config()
    if not cfg.get('mask_enabled'):
        return messages, {}
    return mask_text_messages(messages, cfg)


def mask_text_messages(messages, cfg):
    """同 mask_messages，但各类别开关可控。"""
    mapping: Dict[str, str] = {}
    out: List[Dict[str, Any]] = []
    for msg in messages or []:
        if not isinstance(msg, dict) or msg.get('role') not in ('user', 'assistant'):
            out.append(msg)
            continue
        content = msg.get('content')

        def _do(s: str):
            m, mp = mask_text(
                s,
                mobile=bool(cfg.get('mask_mobile', True)),
                idcard=bool(cfg.get('mask_idcard', True)),
                landline=bool(cfg.get('mask_landline', True)),
                longnum=bool(cfg.get('mask_long_number', True)),
                address=bool(cfg.get('mask_address', True)),
            )
            mapping.update(mp)
            return m

        if isinstance(content, str):
            nm = dict(msg)
            nm['content'] = _do(content)
            out.append(nm)
        elif isinstance(content, list):
            blocks = []
            for block in content:
                if isinstance(block, dict) and block.get('type') == 'text':
                    nb = dict(block)
                    nb['text'] = _do(str(block.get('text', '')))
                    blocks.append(nb)
                else:
                    blocks.append(block)
            nm = dict(msg)
            nm['content'] = blocks
            out.append(nm)
        else:
            out.append(msg)
    return out, mapping
