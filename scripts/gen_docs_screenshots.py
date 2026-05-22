#!/usr/bin/env python3
"""生成用户手册用的 UI 截图。

跑法 (项目根目录):
    QT_QPA_PLATFORM=offscreen .venv/bin/python scripts/gen_docs_screenshots.py

输出: docs/img/*.png

全程 mock stage + mock camera, 不需要硬件。
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

# 必须在 import Qt 之前设置, 让无头服务器也能渲染
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from PySide6.QtCore import Qt, QTimer  # noqa: E402
from PySide6.QtGui import QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402


OUT = REPO / "docs" / "img"
OUT.mkdir(parents=True, exist_ok=True)


def _silence_dialogs() -> None:
    """避免脚本被弹窗卡死: warning/critical/information/question 全部走默认通过。"""
    QMessageBox.warning = lambda *a, **k: None
    QMessageBox.critical = lambda *a, **k: None
    QMessageBox.information = lambda *a, **k: None
    QMessageBox.question = lambda *a, **k: QMessageBox.StandardButton.Yes


def _save(widget, name: str) -> Path:
    """grab 整个 widget 区域并保存到 docs/img/<name>.png。"""
    widget.show()
    QApplication.processEvents()
    time.sleep(0.05)
    QApplication.processEvents()
    pix: QPixmap = widget.grab()
    out = OUT / f"{name}.png"
    pix.save(str(out))
    print(f"  saved {out.relative_to(REPO)}  ({pix.width()}x{pix.height()})")
    return out


def _pump(app: QApplication, seconds: float) -> None:
    """处理事件循环 seconds 秒 (让 mock stage tick + mock camera 出帧)。"""
    deadline = time.time() + seconds
    while time.time() < deadline:
        app.processEvents()
        time.sleep(0.02)


def main() -> None:  # noqa: C901
    _silence_dialogs()
    app = QApplication.instance() or QApplication(sys.argv)
    from psf_scan.ui.theme import apply_theme
    apply_theme(app, scale=1.0, mode="dark")
    from psf_scan.app import MainWindow

    win = MainWindow()
    # 给状态栏顶上一个常用尺寸, 避免布局忽宽忽窄
    win.resize(1400, 900)
    win.show()
    _pump(app, 0.3)

    # 数据目录指到临时位置, 防止脚本污染用户真实数据
    tmp = Path(tempfile.mkdtemp(prefix="psf_docs_"))
    win._settings.set_data_dir(tmp)
    win._refresh_data_dir_label()

    # ① 主窗口 — 未连接状态 (用户启动第一眼)
    print("[1/9] main_idle")
    _pump(app, 0.2)
    _save(win, "main_idle")

    # 连接 mock + mock
    win.status_strip.connect_requested.emit("mock", "mock")
    _pump(app, 0.5)

    # ② 主窗口 — 已连接 (LIVE IMAGE 已经在跑帧)
    print("[2/9] main_connected")
    win._tabs.setCurrentIndex(0)
    _pump(app, 1.0)  # 让相机至少出几帧
    _save(win, "main_connected")

    # ③ 控制面板单独抠出来 (4 列结构看得清楚)
    print("[3/9] control_panel")
    _save(win.control, "control_panel")

    # ④ Camera View 内部 (含 sharpness + line profile 工具按钮)
    print("[4/9] camera_view")
    _save(win.cam_view, "camera_view")

    # ⑤ Stage View (右侧软限位红线 + 行程指示)
    print("[5/9] stage_view")
    _save(win.stage_view, "stage_view")

    # ⑥ 跑一次小扫描 → 拿到 PSF Stack 真实数据后截图
    print("[6/9] psf_view (跑 mock 扫描中...)")
    win.control.sp_zs.setValue(-1.0)
    win.control.sp_ze.setValue(1.0)
    win.control.sp_zd.setValue(0.2)  # 11 个点
    win.control.sp_dwell.setValue(5)
    win.control.sp_avg.setValue(1)
    params = win.control._scan_params_from_controls()
    win._on_scan_start(params)
    # 等扫描完成 (最长 25s)
    deadline = time.time() + 25
    while time.time() < deadline:
        app.processEvents()
        if win._save_thread is None and win._scan_thread is None and win._scan_writer is None:
            time.sleep(0.3)
            app.processEvents()
            break
        time.sleep(0.05)
    _pump(app, 0.3)
    _save(win.psf_view, "psf_view")

    # ⑦ Line profile 对话框 (打开 line 工具)
    print("[7/9] line_profile_dialog")
    win._tabs.setCurrentIndex(0)
    _pump(app, 0.2)
    win.cam_view.btn_line_profile.setChecked(True)
    _pump(app, 0.5)
    if win.cam_view._line_dialog is not None:
        # 推几个新帧, 让 profile 有数据
        _pump(app, 0.8)
        _save(win.cam_view._line_dialog, "line_profile_dialog")
    win.cam_view.btn_line_profile.setChecked(False)
    _pump(app, 0.2)

    # ⑧ 设置对话框 (含 hw 帧提示 + autofocus 分组)
    print("[8/9] settings_dialog")
    from psf_scan.ui.settings_dialog import SettingsDialog
    sdlg = SettingsDialog(win._settings, parent=win)
    sdlg.resize(620, 720)
    sdlg.show()
    _pump(app, 0.3)
    _save(sdlg, "settings_dialog")
    sdlg.close()

    # ⑨ PI 连接对话框 (实机配置长啥样)
    print("[9/9] pi_connect_dialog")
    from psf_scan.ui.pi_connect_dialog import PIConnectDialog
    pidlg = PIConnectDialog(win._settings.pi_params(), parent=win)
    pidlg.resize(540, 540)
    pidlg.show()
    _pump(app, 0.3)
    _save(pidlg, "pi_connect_dialog")
    pidlg.close()

    win.close()
    print(f"\nAll screenshots saved to {OUT.relative_to(REPO)}/")


if __name__ == "__main__":
    main()
