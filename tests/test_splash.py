def test_show_splash_returns_widget(qtbot):
    from psf_scan._splash import show_splash
    splash = show_splash()
    qtbot.addWidget(splash)
    assert splash is not None
    assert splash.isVisible()
    splash.close()


def test_show_splash_returns_none_without_qapplication(qtbot, monkeypatch):
    # qtbot ensures a QApplication exists, then we mock instance() to None.
    from PySide6.QtWidgets import QApplication
    from psf_scan._splash import show_splash

    monkeypatch.setattr(QApplication, "instance", staticmethod(lambda: None))
    assert show_splash() is None
