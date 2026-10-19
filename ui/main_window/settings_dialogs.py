"""Settings, about, update, log viewer and export dialogs."""

import os

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSystemTrayIcon,
    QVBoxLayout,
)

from ui.dialogs import SettingsDialog
from ui.export_dialog import ExportDialog
from utils.helpers import get_icon, get_resource_path
from utils.style import setup_style


class SettingsDialogsMixin:
    """Settings, about, update, log viewer and export dialogs."""

    def _open_settings(self) -> None:
        dlg = SettingsDialog(self.store.settings, self)
        self._show_singleton_dialog(
            "app_settings", dlg, on_accepted=self._process_settings
        )

    def _process_settings(self, dlg: "SettingsDialog") -> None:
        old_ssl = self.store.settings.get("disable_ssl_verify", False)
        old_port = self.store.settings.get("aria2_port", 6800)
        old_host = self.store.settings.get("aria2_host", "http://localhost")
        old_secret = self.store.settings.get("aria2_secret", "")

        s = dlg.get_settings()
        self.store.settings.update(s)
        self.store.save()

        theme = self.store.settings.get("theme", "auto")
        setup_style(QApplication.instance(), theme)

        new_ssl = self.store.settings.get("disable_ssl_verify", False)
        new_port = self.store.settings.get("aria2_port", 6800)
        new_host = self.store.settings.get("aria2_host", "http://localhost")
        new_secret = self.store.settings.get("aria2_secret", "")

        needs_restart = (
            old_ssl != new_ssl
            or old_port != new_port
            or old_host != new_host
            or old_secret != new_secret
        )

        if needs_restart:

            reply = QMessageBox.information(
                self,
                "Restart Required",
                "Some settings (SSL, Port, Host, Secret) require restarting aria2.\n\n"
                "Please restart FelfelDM for changes to take effect.\n\n"
                "Do you want to restart now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )

            if reply == QMessageBox.StandardButton.Yes:
                self.quit_app()
                self.tray.showMessage(
                    "FelfelDM",
                    "aria2 restarted with new settings",
                    QSystemTrayIcon.MessageIcon.Information,
                    5000,
                )
            else:
                self.tray.showMessage(
                    "FelfelDM",
                    "⚠️ Some settings require restart.\nPlease restart FelfelDM later.",
                    QSystemTrayIcon.MessageIcon.Warning,
                    3000,
                )

        else:
            q = self._current_queue()
            has_queue_limit = q and q.speed_limit > 0

            if has_queue_limit:
                self.aria2.change_global_option({"max-overall-download-limit": "0"})
                print(f"⚡ [SpeedLimit] Queue limit wins over global")
                self._apply_queue_speed_limit(q)
            else:
                self._apply_global_speed_limit()

            if not self._apply_settings_to_aria2():
                self._restart_aria2()
            else:
                self.tray.showMessage(
                    "FelfelDM",
                    "Settings applied successfully",
                    QSystemTrayIcon.MessageIcon.Information,
                    5000,
                )

        self._refresh_table()

    def _show_about(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("About FelfelDM")
        dialog.setMinimumWidth(420)
        dialog.setModal(True)

        layout = QVBoxLayout(dialog)
        layout.setSpacing(12)
        layout.setContentsMargins(25, 25, 25, 20)

        icon_label = QLabel()
        icon_path = get_resource_path("logo/icon512.png")
        if os.path.exists(icon_path):
            pixmap = QPixmap(icon_path)
            if not pixmap.isNull():
                icon_label.setPixmap(
                    pixmap.scaled(80, 80, Qt.AspectRatioMode.KeepAspectRatio)
                )
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_label)

        title = QLabel("<h1 style='color: #e74c3c;'>🌶️ FelfelDM</h1>")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        desc = QLabel(
            "<p style='font-size: 14px;'>A modern download manager</p>"
            "<p style='font-size: 12px; color: #888;'>Built with PyQt6 and aria2</p>"
        )
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setWordWrap(True)
        layout.addWidget(desc)

        layout.addSpacing(10)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        update_btn = QPushButton(get_icon("system-software-update"), "Update")
        update_btn.setMinimumWidth(160)
        update_btn.clicked.connect(lambda: (dialog.accept(), self._update()))

        close_btn = QPushButton("Close")
        close_btn.setMinimumWidth(100)
        close_btn.clicked.connect(dialog.accept)

        btn_layout.addStretch()
        btn_layout.addWidget(update_btn)
        btn_layout.addWidget(close_btn)
        btn_layout.addStretch()

        layout.addLayout(btn_layout)

        dialog.exec()

    def _update(self) -> None:
        """Open the update dialog to install the latest version."""
        key = "update_dialog"
        existing = self._open_dialogs.get(key)
        if existing is not None:
            try:
                if existing.isVisible():
                    existing.raise_()
                    existing.activateWindow()
                    return
            except RuntimeError:
                self._open_dialogs.pop(key, None)

        from ui.update_dialog import UpdateDialog

        dlg = UpdateDialog(parent=self)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self._open_dialogs[key] = dlg

        def _cleanup(*_):
            if self._open_dialogs.get(key) is dlg:
                self._open_dialogs.pop(key, None)

        dlg.finished.connect(_cleanup)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _show_log_viewer(self) -> None:
        from ui.log_viewer import LogViewerDialog

        key = "log_viewer"
        existing = self._open_dialogs.get(key)
        if existing is not None:
            try:
                if existing.isVisible():
                    existing.raise_()
                    existing.activateWindow()
                    return
            except RuntimeError:
                self._open_dialogs.pop(key, None)

        dlg = LogViewerDialog(parent=self)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self._open_dialogs[key] = dlg

        def _cleanup(*_):
            if self._open_dialogs.get(key) is dlg:
                self._open_dialogs.pop(key, None)

        dlg.finished.connect(_cleanup)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _export_downloads(self):
        """Open export dialog"""
        queues_with_downloads = [q for q in self.store.queues if q.downloads]
        if not queues_with_downloads:
            QMessageBox.information(self, "Export", "No downloads to export.")
            return

        dialog = ExportDialog(queues_with_downloads, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            success, message = self.export_manager.export_downloads(
                data["queue"], data["format"], data["path"], data["include_headers"]
            )

            if success:
                self.tray.showMessage(
                    "FelfelDM",
                    f"{message}",
                    QSystemTrayIcon.MessageIcon.Information,
                    3000,
                )
            else:
                QMessageBox.critical(self, "Export Failed", message)
