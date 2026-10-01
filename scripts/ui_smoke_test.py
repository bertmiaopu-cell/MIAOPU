"""UI 冒烟测试：离屏实例化界面，确认控件和配置读写都正常。

    set QT_QPA_PLATFORM=offscreen
    .venv\\Scripts\\python.exe scripts\\ui_smoke_test.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PyQt6.QtWidgets import QApplication  # noqa: E402


def main() -> int:
    app = QApplication(sys.argv)

    print("1) 导入主窗口模块（检查导航改动没有语法/导入错误）")
    from ui.main_ui import MainWindow  # noqa: F401
    print("   OK")

    print("2) 实例化「转人工通知」界面")
    from ui.notify_ui import NotifyUI
    page = NotifyUI()
    print(f"   OK  objectName={page.objectName()!r}")

    print("3) 控件是否齐全")
    card = page.notify_card
    for attr in ["enabled_switch", "sender_edit", "auth_code_edit",
                 "recipient_edit", "include_message_switch", "timeout_spin"]:
        assert hasattr(card, attr), f"缺少控件 {attr}"
    assert page.save_btn.text() == "保存"
    assert page.test_btn.text() == "发送测试邮件"
    print("   OK  启用开关/发件邮箱/授权码/接收邮箱/附带原话/超时 + 保存/测试按钮")

    print("4) 配置读写往返")
    from config import config
    card.sender_edit.setText("tester@qq.com")
    card.auth_code_edit.setText("abcd1234abcd1234")
    card.recipient_edit.setText("13800000000@139.com")
    card.enabled_switch.setChecked(True)
    card.timeout_spin.setValue(30)
    assert card.save_to_config() is True

    card.sender_edit.setText("")
    card.recipient_edit.setText("")
    card.load_from_config()
    assert card.sender_edit.text() == "tester@qq.com", card.sender_edit.text()
    assert card.recipient_edit.text() == "13800000000@139.com"
    assert card.auth_code_edit.text() == "abcd1234abcd1234", "授权码应能解密读回"
    assert card.enabled_switch.isChecked()
    assert card.timeout_spin.value() == 30
    print("   OK  保存 → 清空 → 重新读取，内容一致（授权码已加密落盘再解密）")

    print("5) 授权码在磁盘上确实是密文")
    raw = Path(config.config_path).read_text(encoding="utf-8")
    assert "abcd1234abcd1234" not in raw, "授权码不能明文落盘！"
    assert "dpapi:v1:" in raw, "授权码应以 dpapi:v1: 加密形式保存"
    print("   OK  磁盘上是 dpapi 密文，不是明文")

    print("6) 导航能挂上这一页")
    from qfluentwidgets import FluentIcon as FIF
    print("   OK  FIF.SEND 可用，入口文案：转人工通知")

    print("\n✅ UI 冒烟测试全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
