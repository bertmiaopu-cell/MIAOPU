"""隐私与回复节奏界面

* 对话脱敏：发给云端大模型之前，把客户消息里的手机号、地址、订单号等换成占位符，
  回复时自动还原。降低「把他人信息传输给非平台认可第三方」的合规风险。
* 回复节奏：给回复加 1~10 秒随机延迟，避免"秒回"被平台判定为机器自动回复。

界面风格对齐作者原有的「系统设置」页。
"""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QVBoxLayout, QWidget,
                             QFormLayout)
from qfluentwidgets import (CardWidget, SubtitleLabel, CaptionLabel,
                            StrongBodyLabel, PrimaryPushButton, PushButton,
                            LineEdit, ScrollArea, SwitchButton, SpinBox,
                            DoubleSpinBox, FluentIcon as FIF,
                            InfoBar, InfoBarPosition)

from config import config, save_config
from utils.logger_loguru import get_logger

logger = get_logger("PrivacyUI")


class PrivacyConfigCard(CardWidget):
    """对话脱敏配置卡片"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUI()

    def setupUI(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(16)

        title = StrongBodyLabel("对话脱敏")
        title.setFont(QFont("Microsoft YaHei", 12, QFont.Weight.Bold))
        layout.addWidget(title)

        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.setFormAlignment(Qt.AlignmentFlag.AlignLeft)

        self.enabled_switch = SwitchButton()
        self.enabled_switch.setOnText("已启用")
        self.enabled_switch.setOffText("已关闭")
        form.addRow("总开关:", self.enabled_switch)

        self.mobile_switch = SwitchButton()
        self.mobile_switch.setOnText("脱敏")
        self.mobile_switch.setOffText("保留")
        form.addRow("手机号:", self.mobile_switch)

        self.idcard_switch = SwitchButton()
        self.idcard_switch.setOnText("脱敏")
        self.idcard_switch.setOffText("保留")
        form.addRow("身份证号:", self.idcard_switch)

        self.landline_switch = SwitchButton()
        self.landline_switch.setOnText("脱敏")
        self.landline_switch.setOffText("保留")
        form.addRow("固定电话:", self.landline_switch)

        self.longnum_switch = SwitchButton()
        self.longnum_switch.setOnText("脱敏")
        self.longnum_switch.setOffText("保留")
        form.addRow("订单号/银行卡:", self.longnum_switch)

        self.address_switch = SwitchButton()
        self.address_switch.setOnText("脱敏")
        self.address_switch.setOffText("保留")
        form.addRow("收货地址:", self.address_switch)

        layout.addLayout(form)

        help_label = CaptionLabel(
            "工作方式：客户消息发给大模型之前，里面这些信息会被换成 PHONE1 / ADDR1 这类占位符；"
            "大模型的回复发回客户之前，占位符会自动还原成真实内容。原值只存在这一次请求的内存里，不落盘。\n"
            "⚠️ 这是降低风险，不等于完全合规。要做到完全合规应走拼多多开放平台的官方接口。"
        )
        help_label.setWordWrap(True)
        help_label.setStyleSheet("color: #666;")
        layout.addWidget(help_label)

    def load_from_config(self):
        get = config.get
        self.enabled_switch.setChecked(bool(get('privacy.mask_enabled', True)))
        self.mobile_switch.setChecked(bool(get('privacy.mask_mobile', True)))
        self.idcard_switch.setChecked(bool(get('privacy.mask_idcard', True)))
        self.landline_switch.setChecked(bool(get('privacy.mask_landline', True)))
        self.longnum_switch.setChecked(bool(get('privacy.mask_long_number', True)))
        self.address_switch.setChecked(bool(get('privacy.mask_address', True)))

    def save_to_config(self):
        config.set('privacy.mask_enabled', self.enabled_switch.isChecked(), save=False)
        config.set('privacy.mask_mobile', self.mobile_switch.isChecked(), save=False)
        config.set('privacy.mask_idcard', self.idcard_switch.isChecked(), save=False)
        config.set('privacy.mask_landline', self.landline_switch.isChecked(), save=False)
        config.set('privacy.mask_long_number', self.longnum_switch.isChecked(), save=False)
        config.set('privacy.mask_address', self.address_switch.isChecked(), save=False)


class ReplyRhythmCard(CardWidget):
    """回复节奏配置卡片"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUI()

    def setupUI(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(16)

        title = StrongBodyLabel("回复节奏（拟人化延迟）")
        title.setFont(QFont("Microsoft YaHei", 12, QFont.Weight.Bold))
        layout.addWidget(title)

        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.setFormAlignment(Qt.AlignmentFlag.AlignLeft)

        self.delay_switch = SwitchButton()
        self.delay_switch.setOnText("已启用")
        self.delay_switch.setOffText("已关闭")
        form.addRow("随机延迟:", self.delay_switch)

        self.min_spin = DoubleSpinBox()
        self.min_spin.setRange(0.5, 60.0)
        self.min_spin.setSingleStep(0.5)
        self.min_spin.setDecimals(1)
        self.min_spin.setSuffix(" 秒")
        form.addRow("最短延迟:", self.min_spin)

        self.max_spin = DoubleSpinBox()
        self.max_spin.setRange(0.5, 120.0)
        self.max_spin.setSingleStep(0.5)
        self.max_spin.setDecimals(1)
        self.max_spin.setSuffix(" 秒")
        form.addRow("最长延迟:", self.max_spin)

        layout.addLayout(form)

        help_label = CaptionLabel(
            "每条回复发出前，会在你设定的区间里随机取一个秒数等一等再发。\n"
            "为什么需要：平台判断「机器自动回复」最直接的特征就是秒回 —— 尤其是半夜也零点几秒回一条。\n"
            "建议 1~10 秒（默认），既不太拖沓，也不会看起来像脚本。转人工的通知不受这个延迟影响，是立刻发的。"
        )
        help_label.setWordWrap(True)
        help_label.setStyleSheet("color: #666;")
        layout.addWidget(help_label)

    def load_from_config(self):
        get = config.get
        self.delay_switch.setChecked(bool(get('reply.delay_enabled', True)))
        try:
            self.min_spin.setValue(float(get('reply.delay_min', 1.0) or 1.0))
            self.max_spin.setValue(float(get('reply.delay_max', 10.0) or 10.0))
        except (TypeError, ValueError):
            self.min_spin.setValue(1.0)
            self.max_spin.setValue(10.0)

    def save_to_config(self):
        lo = float(self.min_spin.value())
        hi = float(self.max_spin.value())
        if lo > hi:
            lo, hi = hi, lo
        config.set('reply.delay_enabled', self.delay_switch.isChecked(), save=False)
        config.set('reply.delay_min', lo, save=False)
        config.set('reply.delay_max', hi, save=False)


class PrivacyUI(QFrame):
    """隐私与回复节奏界面"""

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.logger = get_logger("PrivacyUI")
        self.setupUI()
        self.loadConfig()
        self.setObjectName("隐私与节奏")

    def setupUI(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(30, 30, 30, 30)
        main_layout.setSpacing(25)
        main_layout.addWidget(self.createHeaderWidget())
        main_layout.addWidget(self.createContentWidget(), 1)

    def createHeaderWidget(self):
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(20)

        title_label = SubtitleLabel("隐私与节奏")
        title_label.setFont(QFont("Microsoft YaHei", 18, QFont.Weight.Bold))
        description_label = CaptionLabel("管理发给大模型的客户信息，以及回复的节奏")
        description_label.setStyleSheet("color: #666;")

        title_area = QWidget()
        title_layout = QVBoxLayout(title_area)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(5)
        title_layout.addWidget(title_label)
        title_layout.addWidget(description_label)

        buttons_widget = QWidget()
        buttons_layout = QHBoxLayout(buttons_widget)
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        buttons_layout.setSpacing(10)

        self.save_btn = PrimaryPushButton("保存")
        self.save_btn.setIcon(FIF.SAVE)
        self.save_btn.setFixedSize(100, 40)
        buttons_layout.addWidget(self.save_btn)

        header_layout.addWidget(title_area)
        header_layout.addStretch()
        header_layout.addWidget(buttons_widget)
        return header_widget

    def createContentWidget(self):
        scroll_area = ScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setStyleSheet("""
            ScrollArea {
                border: none;
                background-color: transparent;
            }
        """)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(20)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.privacy_card = PrivacyConfigCard()
        self.rhythm_card = ReplyRhythmCard()
        layout.addWidget(self.privacy_card)
        layout.addWidget(self.rhythm_card)

        # 脱敏效果自测
        test_card = CardWidget()
        test_layout = QVBoxLayout(test_card)
        test_layout.setContentsMargins(20, 16, 20, 16)
        test_layout.setSpacing(10)
        t = StrongBodyLabel("试试脱敏效果")
        t.setFont(QFont("Microsoft YaHei", 12, QFont.Weight.Bold))
        test_layout.addWidget(t)

        row = QHBoxLayout()
        self.test_input = LineEdit()
        self.test_input.setPlaceholderText("粘贴一句带手机号/地址的话，例如：我地址是浙江省杭州市余杭区五常街道文一西路969号，电话13800138000")
        self.test_input.setClearButtonEnabled(True)
        self.test_btn = PushButton("测试")
        self.test_btn.setIcon(FIF.SEARCH)
        self.test_btn.setFixedSize(90, 34)
        row.addWidget(self.test_input, 1)
        row.addWidget(self.test_btn)
        test_layout.addLayout(row)

        self.test_output = CaptionLabel("（点「测试」看脱敏结果）")
        self.test_output.setWordWrap(True)
        self.test_output.setStyleSheet("color: #2C3E50;")
        test_layout.addWidget(self.test_output)

        layout.addWidget(test_card)
        layout.addStretch()

        container.setStyleSheet("""
            QWidget {
                background-color: transparent;
            }
        """)
        scroll_area.setWidget(container)

        self.save_btn.clicked.connect(self.onSave)
        self.test_btn.clicked.connect(self.onTest)
        return scroll_area

    # ------------------------------------------------------------------ 行为
    def loadConfig(self):
        try:
            self.privacy_card.load_from_config()
            self.rhythm_card.load_from_config()
        except Exception as e:
            self.logger.error(f"读取隐私配置失败: error_type={type(e).__name__}")

    def onSave(self):
        try:
            self.privacy_card.save_to_config()
            self.rhythm_card.save_to_config()
            if not save_config():
                raise RuntimeError("配置写入失败")
            self.logger.info("隐私与节奏配置保存成功")
            InfoBar.success(
                title="保存成功",
                content="已生效（无需重启软件）",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=2500,
                parent=self,
            )
        except Exception as e:
            self.logger.error(f"保存隐私配置失败: error_type={type(e).__name__}")
            InfoBar.error(
                title="保存失败", content=str(e),
                orient=Qt.Orientation.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP, duration=4000, parent=self,
            )

    def onTest(self):
        text = self.test_input.text().strip()
        if not text:
            self.test_output.setText("先在上面输入一句话再点测试。")
            return
        try:
            from utils.privacy_mask import mask_text, restore_text
            masked, mapping = mask_text(text)
            if not mapping:
                self.test_output.setText("这句话里没有识别到手机号/地址/订单号等敏感信息。")
                return
            back = restore_text(masked, mapping)
            lines = ["脱敏后：" + masked, "还原后：" + back, "本次替换："]
            for k, v in mapping.items():
                lines.append("　%s ← %s" % (k, v))
            self.test_output.setText("\n".join(lines))
        except Exception as e:
            self.test_output.setText("测试失败：%s" % e)
