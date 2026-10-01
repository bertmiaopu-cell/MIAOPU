"""
关键词检测处理器 - 检测转人工关键词并触发转人工流程

⚠️ 已停用（2026-10-02）
--------------------------------------------------------------------------
本处理器在处理器链里优先级最高：只要买家消息里命中任意一个关键词，就会
直接转人工并**跳过后面的 AI 处理器**，导致"客户问的是 AI 能答的问题，却
被关键词拦掉直接甩给人工"。

现在改为：**不再做关键词拦截，是否需要人工完全交给 AI 判断**。
做法是把关键词集合固定成一个永远不可能出现在买家消息里的哨兵值，
`can_handle()` 因此恒为 False，本处理器实际上变成空操作。

- 数据库里的关键词表和「关键词管理」界面都保留着，不影响原有数据；
- 想恢复旧行为，把下面的 `KEYWORD_INTERCEPT_ENABLED` 改回 True 即可。
"""
import asyncio
from datetime import datetime, time
from typing import Dict, Any
from bridge.context import Context, ContextType
from .base import BaseHandler
from database.db_manager import db_manager
from utils.logger_loguru import get_logger
from bridge.sender import get_sender

# 关键词拦截总开关。False = 转人工完全由 AI 判断（当前行为）。
KEYWORD_INTERCEPT_ENABLED = False

# 哨兵：含 NUL 字符，任何正常的买家消息都不可能包含它。
_NEVER_MATCH_KEYWORD = "\x00__keyword_intercept_disabled__\x00"


class KeywordDetectionHandler(BaseHandler):
    """关键词检测处理器 - 检测转人工关键词并触发转人工流程"""

    def __init__(self, business_hours=None):
        super().__init__("KeywordDetectionHandler")
        self.logger = get_logger("KeywordDetectionHandler")
        self.business_hours = business_hours or {"start": "08:00", "end": "23:00"}
        self.keywords = self._load_keywords()

        if KEYWORD_INTERCEPT_ENABLED:
            self.logger.info(f"关键词检测处理器初始化完成，加载了 {len(self.keywords)} 个关键词")
        else:
            self.logger.info(
                "关键词拦截已停用：转人工完全交给 AI 判断（关键词表保留，但不再参与匹配）"
            )

    def _load_keywords(self):
        """加载关键词。

        停用状态下直接返回哨兵集合，连数据库都不查，杜绝任何形式的误命中。
        """
        if not KEYWORD_INTERCEPT_ENABLED:
            return {_NEVER_MATCH_KEYWORD}

        try:
            keywords_data = db_manager.get_all_keywords()
            keywords = {item['keyword'].lower() for item in keywords_data if item.get('keyword')}
            self.logger.debug(f"loaded keyword count={len(keywords)}")
            return keywords
        except Exception as e:
            self.logger.error(
                f"keyword load failed: error_type={type(e).__name__}"
            )
            # 如果加载失败，使用默认关键词
            default_keywords = {
                "转人工", "人工客服", "真人", "客服", "人工", "工单", "好评",
                "取消订单", "改地址", "转售后客服", "转售后", "返现", "过敏",
                "退款", "没有效果", "骗人", "投诉", "纠纷", "开发票", "开票",
                "烂", "取消", "备注"
            }
            self.logger.warning(
                f"using default keywords: count={len(default_keywords)}"
            )
            return default_keywords

    def can_handle(self, context: Context) -> bool:
        """检查消息是否包含关键词"""
        # 停用状态下永远不接管，消息全部交给 AI 处理器
        if not KEYWORD_INTERCEPT_ENABLED:
            return False

        # 只处理文本类型的消息
        if not self._within_business_hours():
            return False
        if context.type != ContextType.TEXT:
            return False

        # 检查消息内容是否存在且为字符串
        if not context.content or not isinstance(context.content, str):
            return False

        # 将消息内容转换为小写进行检测
        content_lower = context.content.lower()

        # 检查是否包含任何关键词
        for keyword in self.keywords:
            if keyword in content_lower:
                self.logger.debug(
                    f"keyword detected: {keyword!r}, message_length={len(context.content)}"
                )
                return True

        return False

    async def handle(self, context: Context, metadata: Dict[str, Any]) -> bool:
        """转接到人工客服"""
        try:
            kwargs = context.kwargs
            shop_id = getattr(kwargs, 'shop_id', None) or (kwargs.get('shop_id') if isinstance(kwargs, dict) else None)
            user_id = getattr(kwargs, 'user_id', None) or (kwargs.get('user_id') if isinstance(kwargs, dict) else None)
            from_uid = getattr(kwargs, 'from_uid', None) or (kwargs.get('from_uid') if isinstance(kwargs, dict) else None)
            
            if not all([shop_id, user_id, from_uid]):
                return False
            
            sender = get_sender(context.channel_type)
            if not sender:
                self.logger.warning(f"无可用发送器: channel_type={context.channel_type}")
                return False

            # 获取可用的客服列表（同步 HTTP，放工作线程）
            cs_list = await asyncio.to_thread(sender.get_cs_list, shop_id, user_id)
            my_cs_uid = f"cs_{shop_id}_{user_id}"

            if cs_list and isinstance(cs_list, dict):
                # 过滤掉自己，不转接给自己
                available_cs_uids = [uid for uid in cs_list.keys() if uid != my_cs_uid]

                if available_cs_uids:
                    # 选择第一个可用的客服
                    cs_uid = available_cs_uids[0]
                    target_cs = cs_list[cs_uid]
                    cs_name = target_cs.get('username', '客服')

                    # 转移会话（同步 HTTP，放工作线程）
                    transfer_result = await asyncio.to_thread(sender.transfer_to_cs, shop_id, user_id, from_uid, cs_uid)

                    if transfer_result and transfer_result.get('success'):

                        self.logger.info(f"会话已成功转接给 {cs_name} ({cs_uid})")
                        return True
                    else:
                        self.logger.error("会话转接失败")
                else:
                    self.logger.warning("没有其他可用的客服进行转接")
                    await asyncio.to_thread(sender.send_text, shop_id, user_id, from_uid, "抱歉，当前没有其他客服在线，请您稍后再试。")
            
            return False
            
        except Exception as e:
            self.logger.error(
                f"客服转接处理失败: error_type={type(e).__name__}"
            )
            return False
            
    def reload_keywords(self) -> None:
        """重新加载关键词（用于管理员更新关键词后刷新）"""
        old_count = len(self.keywords)
        self.keywords = self._load_keywords()
        new_count = len(self.keywords)
        self.logger.info(f"关键词重新加载完成: {old_count} -> {new_count}")

    def get_keyword_count(self) -> int:
        """获取当前关键词数量"""
        return len(self.keywords)

    def get_keywords(self) -> set:
        """获取当前关键词列表"""
        return self.keywords.copy()

    def _within_business_hours(self) -> bool:
        """Return whether manual-service routing is currently enabled."""
        try:
            start = time.fromisoformat(str(self.business_hours.get("start", "08:00")))
            end = time.fromisoformat(str(self.business_hours.get("end", "23:00")))
            current = datetime.now().time()
            if start <= end:
                return start <= current <= end
            return current >= start or current <= end
        except (TypeError, ValueError):
            self.logger.warning("invalid business hours; manual routing disabled")
            return False
