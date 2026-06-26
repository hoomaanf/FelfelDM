#!/usr/bin/env python3
"""
DLManager Pro - Download Manager
"""

import sys
import os
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from ui.main_window import MainWindow
from utils.style import setup_style, CustomProxyStyle

def main():
    """نقطه ورود اصلی برنامه"""
    
    # تنظیمات High DPI برای نمایش بهتر در صفحه‌های با رزولوشن بالا
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    
    # تنظیمات محیط برای Wayland و KDE
    os.environ.setdefault("QT_QPA_PLATFORM", "wayland")
    os.environ.setdefault("QT_QPA_PLATFORMTHEME", "kde")
    
    # ایجاد اپلیکیشن
    app = QApplication(sys.argv)
    
    # اعمال استایل سفارشی برای SpinBox (فلش‌های بالا/پایین)
    app.setStyle(CustomProxyStyle())
    
    # تنظیم نام اپلیکیشن
    app.setApplicationName("DL Manager")
    
    # جلوگیری از خروج برنامه وقتی آخرین پنجره بسته میشه
    app.setQuitOnLastWindowClosed(False)
    
    # اعمال استایل کلی (تم تاریک/روشن، آیکون‌ها و ...)
    setup_style(app)
    
    # ایجاد و نمایش پنجره اصلی
    win = MainWindow()
    win.show()
    
    # اجرای حلقه اصلی برنامه
    sys.exit(app.exec())

if __name__ == "__main__":
    main()