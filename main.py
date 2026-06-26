#!/usr/bin/env python3
"""
FelfelDM - Download Manager
"""

import sys
import os
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt
from ui.main_window import MainWindow
from utils.style import setup_style, CustomProxyStyle

def main():
    
    # تنظیمات High DPI برای نمایش بهتر در صفحه‌های با رزولوشن بالا
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    
    # تنظیمات محیط برای Wayland و KDE
    os.environ.setdefault("QT_QPA_PLATFORM", "wayland")
    os.environ.setdefault("QT_QPA_PLATFORMTHEME", "kde")
    
    # ایجاد اپلیکیشن
    app = QApplication(sys.argv)
    
    # 🆕 ست کردن آیکون برنامه (قبل از هر چیز)
    icon_paths = [
        "logo/icon256.png",
        "logo/icon128.png", 
        "logo/icon256.png",
        "logo/icon128.png"
    ]
    
    icon_set = False
    for path in icon_paths:
        if os.path.exists(path):
            app.setWindowIcon(QIcon(path))
            icon_set = True
            print(f"✅ Icon loaded from: {path}")
            break
    
    if not icon_set:
        print("⚠️ No icon found! Using default.")
    
    # اعمال استایل سفارشی برای SpinBox (فلش‌های بالا/پایین)
    app.setStyle(CustomProxyStyle())
    
    # تنظیم نام اپلیکیشن
    app.setApplicationName("FelfelDM")
    
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