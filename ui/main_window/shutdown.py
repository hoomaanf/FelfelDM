"""'Shut down when finished' feature."""

import os

from PyQt6.QtWidgets import QSystemTrayIcon

from ui.dialogs import ShutdownCountdownDialog


class ShutdownMixin:
    """'Shut down when finished' feature."""

    def _toggle_shutdown(self, checked: bool) -> None:
        self.store.settings["shutdown_after_finish"] = checked
        self.store.save()

        if not checked and self._shutdown_dialog:
            self._shutdown_dialog.reject()
            self._shutdown_dialog = None
            self._shutdown_dialog_shown = False
            self.tray.showMessage(
                "FelfelDM",
                "Shutdown cancelled.",
                QSystemTrayIcon.MessageIcon.Information,
                5000,
            )
        elif checked:
            self.tray.showMessage(
                "FelfelDM",
                "🛑 Shutdown will trigger when all downloads complete.",
                QSystemTrayIcon.MessageIcon.Information,
                5000,
            )
            self._check_already_complete()

    def _check_already_complete(self) -> None:
        if not self._startup_complete:
            return

        if not self.shutdown_cb.isChecked() or self._shutdown_dialog_shown:
            return

        total = 0
        complete = 0

        for q in self.store.queues:
            for gid in q.downloads:
                total += 1
                status = self._all_downloads.get(gid, {}).get("status", "")

                if status in ["active", "waiting", "downloading"]:
                    return

                if status in ["complete", "completed", "error", "removed"]:
                    complete += 1

        if total == 0:
            return

        if complete == total:
            if not self._shutdown_dialog_shown:
                self._shutdown_dialog_shown = True
                self.tray.showMessage(
                    "🌶️ FelfelDM",
                    "All downloads completed!\n🛑 System will shut down in 20 seconds.",
                    QSystemTrayIcon.MessageIcon.Information,
                    5000,
                )
                self._show_shutdown_countdown()

    def _show_shutdown_countdown(self) -> None:
        if self._shutdown_dialog:
            self._shutdown_dialog.close()
            self._shutdown_dialog = None

        dialog = ShutdownCountdownDialog(self)
        dialog.accepted.connect(self._shutdown_system)
        dialog.rejected.connect(self._cancel_shutdown)
        dialog.start_countdown()

        self._shutdown_dialog = dialog
        self._center_dialog_on_screen(dialog)

    def _shutdown_system(self) -> None:
        self._shutdown_dialog = None
        self._shutdown_dialog_shown = False
        self.tray.showMessage(
            "FelfelDM",
            "🛑 Shutting down system...",
            QSystemTrayIcon.MessageIcon.Information,
            3000,
        )

        # Issue the actual poweroff request BEFORE tearing the app down.
        # quit_app() ends with sys.exit(0), which kills this process
        # immediately — any code placed after that call never runs, which
        # was the bug: the app quit cleanly but the machine never powered
        # off because that call came first.
        self._request_system_poweroff()

        self.quit_app()

    def _request_system_poweroff(self) -> None:
        try:
            from PyQt6.QtDBus import QDBusInterface, QDBusConnection

            bus = QDBusConnection.systemBus()
            logind = QDBusInterface(
                "org.freedesktop.login1",
                "/org/freedesktop/login1",
                "org.freedesktop.login1.Manager",
                bus,
            )

            if logind.isValid():
                can = logind.call("CanPowerOff").arguments()
                if can and can[0] == "yes":
                    print("[Shutdown] DBus PowerOff")
                    logind.call("PowerOff", False)
                    return
                else:
                    print(f"⚠️ [Shutdown] DBus cannot poweroff: {can}")
        except Exception as e:
            print(f"⚠️ [Shutdown] DBus failed: {e}")

        print("🔄 [Shutdown] Falling back to systemctl")
        os.system("systemctl poweroff")

    def _cancel_shutdown(self) -> None:
        self._shutdown_dialog = None
        self._shutdown_dialog_shown = False
        self.shutdown_cb.setChecked(False)
        self.store.settings["shutdown_after_finish"] = False
        self.store.save()
        self.tray.showMessage(
            "FelfelDM",
            "Shutdown cancelled.",
            QSystemTrayIcon.MessageIcon.Information,
            5000,
        )
