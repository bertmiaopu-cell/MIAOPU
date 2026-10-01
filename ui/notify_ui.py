"""转人工通知界面

买家咨询被转接给人工时，用 QQ 邮箱把通知发到商家的手机邮箱。

界面风格对齐作者原有的「系统设置」页：同一个 qfluentwidgets 卡片式表单 +
顶部标题栏 + 右下角保存按钮，方便一眼认出来是同一个软件。
"""

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QVBoxLayout, QWidget,
                             QFormLayout)
from qfluentwidgets import (CardWidget, SubtitleLabel, CaptionLabel,
                            StrongBodyLabel, PrimaryPushButton, PushButton,
                            LineEdit, PasswordLineEdit, ScrollArea,
                            SwitchButton, SpinBox, FluentIcon as FIF,
                            InfoBar, InfoBarPosition)

from config import config, save_config
from utils.logger_loguru import get_logger

logger = get_logger("NotifyUI")


class _TestMailWorker(QThread):
    """测试邮件放到后台线程发，避免 SMTP 阻塞界面。"""

    finished_with = pyqtSignal(bool, str)

    def run(self):  # noqa: D102 - QThread 约定
        try:
            from service.transfer_notify import send_test_email
            ok, msg = send_test_email()
        except Exception as e:  # pragma: no cover - 兜底
            ok, msg = False, f"{type(e).__name__}: {e}"
        self.finished_with.emit(ok, msg)


class NotifyConfigCard(CardWidget):
    """邮件通知配置卡片"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUI()

    def setupUI(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(16)

        title_label = StrongBodyLabel("QQ 邮箱通知配置")
        title_label.setFont(QFont("Microsoft YaHei", 12, QFont.Weight.Bold))
        layout.addWidget(title_label)

        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.setFormAlignment(Qt.AlignmentFlag.AlignLeft)

        self.enabled_switch = SwitchButton()
        self.enabled_switch.setOnText("已启用")
        self.enabled_switch.setOffText("已关闭")
        form.addRow("转人工邮件通知:", self.enabled_switch)

        self.sender_edit = LineEdit()
        self.sender_edit.setPlaceholderText("例如 12345678@qq.com")
        self.sender_edit.setClearButtonEnabled(True)
        form.addRow("发件 QQ 邮箱:", self.sender_edit)

        self.auth_code_edit = PasswordLineEdit()
        self.auth_code_edit.setPlaceholderText("QQ 邮箱的 16 位 SMTP 授权码（不是QQ密码）")
        self.auth_code_edit.setClearButtonEnabled(True)
        form.addRow("邮箱授权码:", self.auth_code_edit)

        self.recipient_edit = LineEdit()
        self.recipient_edit.setPlaceholderText("手机邮箱，例如 138xxxxxxxx@139.com（多个用逗号分隔）")
        self.recipient_edit.setClearButtonEnabled(True)
        form.addRow("接收通知的邮箱:", self.recipient_edit)

        self.include_message_switch = SwitchButton()
        self.include_message_switch.setOnText("附带")
        self.include_message_switch.setOffText("不附带")
        form.addRow("邮件里带上客户原话:", self.include_message_switch)

        self.timeout_spin = SpinBox()
        self.timeout_spin.setRange(5, 120)
        self.timeout_spin.setSuffix(" 秒")
        form.addRow("发送超时:", self.timeout_spin)

        layout.addLayout(form)

        # 用法说明（和作者的说明性 CaptionLabel 风格一致）
        help_label = CaptionLabel(
            "怎么拿到授权码：电脑登录 QQ 邮箱网页版 → 设置 → 账户 → "
            "找到「IMAP/SMTP服务」→ 点开启 → 按提示用手机发一条短信 → "
            "页面会给你 16 位授权码，复制到这里即可。\n"
            "接收邮箱怎么选：① 填你自己的 QQ 邮箱，微信里会弹「QQ邮箱提醒」；"
            "② 填手机号@139.com（移动）/ @wo.cn（联通）/ @189.cn（电信），会直接发短信到你手机上。\n"
            "授权码会用 Windows 凭据加密后保存，不会明文落盘。"
        )
        help_label.setWordWrap(True)
        help_label.setStyleSheet("color: #666;")
        layout.addWidget(help_label)

    # ------------------------------------------------------------------ 读写
    def load_from_config(self):
        """把 config.json 里的 notify 段读进界面"""
        get = config.get
        self.enabled_switch.setChecked(bool(get("notify.enabled", False)))
        self.sender_edit.setText(str(get("notify.sender_email", "") or ""))
        self.auth_code_edit.setText(str(get("notify.auth_code", "") or ""))
        self.recipient_edit.setText(str(get("notify.recipient_email", "") or ""))
        self.include_message_switch.setChecked(
            bool(get("notify.include_customer_message", True))
        )
        try:
            self.timeout_spin.setValue(int(get("notify.timeout", 20) or 20))
        except (TypeError, ValueError):
            self.timeout_spin.setValue(20)

    def save_to_config(self):
        """写回 config.json（授权码会被 DPAPI 加密后落盘）"""
        config.set("notify.enabled", self.enabled_switch.isChecked(), save=False)
        config.set("notify.sender_email", self.sender_edit.text().strip(), save=False)
        config.set("notify.auth_code", self.auth_code_edit.text().strip(), save=False)
        config.set("notify.recipient_email", self.recipient_edit.text().strip(), save=False)
        config.set("notify.include_customer_message",
                   self.include_message_switch.isChecked(), save=False)
        config.set("notify.timeout", int(self.timeout_spin.value()), save=False)
        config.set("notify.smtp_host", "smtp.qq.com", save=False)
        config.set("notify.smtp_port", 465, save=False)
        return save_config()


class NotifyUI(QFrame):
    """转人工通知界面"""

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.logger = get_logger("NotifyUI")
        self._worker = None
        self.setupUI()
        self.loadConfig()
        self.setObjectName("转人工通知")

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

        title_label = SubtitleLabel("转人工通知")
        title_label.setFont(QFont("Microsoft YaHei", 18, QFont.Weight.Bold))
        description_label = CaptionLabel(
            "AI 请求人工接管时，把「为什么转」和「客户说了什么」发到你的手机邮箱"
        )
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

        self.test_btn = PushButton("发送测试邮件")
        self.test_btn.setIcon(FIF.SEND)
        self.test_btn.setFixedSize(150, 40)

        self.save_btn = PrimaryPushButton("保存")
        self.save_btn.setIcon(FIF.SAVE)
        self.save_btn.setFixedSize(100, 40)

        buttons_layout.addWidget(self.test_btn)
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

        content_container = QWidget()
        content_layout = QVBoxLayout(content_container)
        content_layout.setSpacing(20)
        content_layout.setContentsMargins(20, 20, 20, 20)
        content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.notify_card = NotifyConfigCard()
        content_layout.addWidget(self.notify_card)

        # 邮件长什么样的示例
        preview = CardWidget()
        preview_layout = QVBoxLayout(preview)
        preview_layout.setContentsMargins(20, 16, 20, 16)
        preview_layout.setSpacing(8)
        pv_title = StrongBodyLabel("邮件长这样")
        pv_title.setFont(QFont("Microsoft YaHei", 12, QFont.Weight.Bold))
        preview_layout.addWidget(pv_title)
        sample = CaptionLabel(
            "主题：⚠️ 需要人工接手 - AI 客服转人工提醒\n\n"
            "【需要人工接手】\n"
            "时间：2026-10-02 03:10:22\n"
            "店铺：祥和金属雕花外墙板（274507345）\n"
            "触发方式：AI 判断需要人工接管\n\n"
            "─── AI 请求人工接管的原因 ───\n"
            "亲，退货流程需要人工给您处理，我帮您转接专门的同事，稍等一下～\n\n"
            "─── 客户最后说的话 ───\n"
            "我想了解下退货流程\n\n"
            "请尽快到拼多多商家后台接待该客户。"
        )
        sample.setWordWrap(True)
        sample.setStyleSheet("color: #555;")
        preview_layout.addWidget(sample)
        content_layout.addWidget(preview)

        content_layout.addStretch()

        content_container.setStyleSheet("""
            QWidget {
                background-color: transparent;
            }
        """)
        scroll_area.setWidget(content_container)

        self.save_btn.clicked.connect(self.onSave)
        self.test_btn.clicked.connect(self.onTest)
        return scroll_area

    # ------------------------------------------------------------------ 行为
    def loadConfig(self):
        try:
            self.notify_card.load_from_config()
        except Exception as e:
            self.logger.error(f"读取通知配置失败: error_type={type(e).__name__}")

    def onSave(self):
        try:
            if not self.notify_card.save_to_config():
                raise RuntimeError("配置写入失败")
            self.logger.info("转人工通知配置保存成功")
            InfoBar.success(
                title="保存成功",
                content="转人工邮件通知配置已生效（无需重启）",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=2500,
                parent=self,
            )
        except Exception as e:
            self.logger.error(f"保存通知配置失败: error_type={type(e).__name__}")
            InfoBar.error(
                title="保存失败",
                content=str(e),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=4000,
                parent=self,
            )

    def onTest(self):
        """先保存当前填写的内容，再按当前内容发一封测试邮件。"""
        try:
            self.notify_card.save_to_config()
        except Exception:
            pass

        self.test_btn.setEnabled(False)
        self.test_btn.setText("发送中…")
        self._worker = _TestMailWorker(self)
        self._worker.finished_with.connect(self._onTestDone)
        self._worker.start()

    def _onTestDone(self, ok: bool, msg: str):
        self.test_btn.setEnabled(True)
        self.test_btn.setText("发送测试邮件")
        if ok:
            InfoBar.success(
                title="测试邮件已发送",
                content=msg + "　请查看手机邮箱（也可能在垃圾邮件里）",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=5000,
                parent=self,
            )
        else:
            InfoBar.error(
                title="发送失败",
                content=msg,
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=8000,
                parent=self,
            )
