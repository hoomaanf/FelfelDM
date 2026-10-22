"""Restoring/saving downloads and closing/quitting the app."""

import os
import time

from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from ui.splash import SplashScreen


class LifecycleMixin:
    """Restoring/saving downloads and closing/quitting the app."""

    def _restore_downloads(self) -> None:
        print("🔄 Loading downloads from storage...")

        original_on_error = self.aria2.on_error
        self.aria2.on_error = None

        try:
            if not self.aria2.is_connected():
                print("⏳ Waiting for aria2 to connect...")
                for attempt in range(15):
                    time.sleep(0.5)
                    if self.aria2.is_connected():
                        print(f"aria2 connected after {attempt+1} attempts")
                        break

            active_gids = set()
            waiting_gids = set()
            stopped_gids = set()
            live_gids = set()
            try:
                for dl in self.aria2.tell_active() or []:
                    if dl.get("gid"):
                        active_gids.add(dl["gid"])
                        live_gids.add(dl["gid"])
                for dl in self.aria2.tell_waiting() or []:
                    if dl.get("gid"):
                        waiting_gids.add(dl["gid"])
                        live_gids.add(dl["gid"])
                for dl in self.aria2.tell_stopped(0, 300) or []:
                    if dl.get("gid"):
                        stopped_gids.add(dl["gid"])
                        live_gids.add(dl["gid"])
                pass
            except Exception as e:
                print(f"⚠️ [Restore] Could not fetch aria2 status: {e}")

            auto_clear = self.store.settings.get("auto_clear_completed", False)
            restored_count = 0
            needs_save = False

            for q in self.store.queues:
                to_remove = []

                for download_id in q.downloads:
                    info = q.downloads_info.get(download_id, {})
                    status = info.get("status", "")

                    if auto_clear and status in ["complete", "completed"]:
                        to_remove.append(download_id)
                        needs_save = True
                        continue

                    if not info:
                        info = {
                            "name": "Unknown",
                            "status": "paused",
                            "totalLength": 0,
                            "completedLength": 0,
                            "files": [],
                            "category": "📁 Other",
                            "download_type": "normal",
                        }
                        q.downloads_info[download_id] = info
                        needs_save = True

                    total_length = int(info.get("totalLength", 0))
                    if total_length == 0:
                        files = info.get("files", [])
                        if files and files[0].get("length"):
                            try:
                                total_length = int(files[0]["length"])
                            except (ValueError, TypeError):
                                pass

                    info_status = info.get("status", "")
                    completed_length = int(info.get("completedLength", 0))
                    files = info.get("files", [])
                    download_type = info.get("download_type", "normal")
                    category = info.get("category", "📁 Other")
                    name = info.get("name", "Unknown")
                    aria2_gid = info.get("aria2_gid")

                    if not files or not files[0].get("path"):
                        dl_save_path = info.get("save_path") or q.save_path
                        if name and dl_save_path:
                            files = [{"path": os.path.join(dl_save_path, name)}]

                    if name == "Unknown":
                        if files and files[0].get("path"):
                            name = os.path.basename(files[0]["path"])
                    if name == "Unknown":
                        url = info.get("url", "")
                        if url:
                            name = url.split("/")[-1].split("?")[0]

                    if info_status in ["complete", "completed"]:
                        final_status = "complete"
                    elif aria2_gid and aria2_gid in live_gids:

                        final_status = "paused"
                    else:

                        if info_status in ["complete", "completed"]:
                            final_status = "complete"
                        else:
                            final_status = "error"
                            print(
                                f"⚠️ [Restore] {download_id[:12]} has dead GID "
                                f"({aria2_gid}) → marking as error for re-add"
                            )

                    matched_rule_name = info.get("matched_rule")
                    rule_speed = info.get("rule_speed_limit", 0)

                    url = info.get("url", "")
                    if url and download_type == "normal":
                        try:
                            _rule = self.store.rule_engine.find_match(url)
                            if _rule:
                                matched_rule_name = _rule.name
                                if _rule.speed_limit:
                                    rule_speed = _rule.speed_limit
                        except Exception as e:
                            print(f"⚠️ [Restore] Rule match failed for {url}: {e}")

                    self._all_downloads[download_id] = {
                        "id": download_id,
                        "aria2_gid": aria2_gid,
                        "gid": aria2_gid,
                        "name": name,
                        "status": final_status,
                        "totalLength": total_length,
                        "completedLength": completed_length,
                        "downloadSpeed": 0,
                        "connections": 0,
                        "files": files,
                        "errorMessage": "",
                        "category": category,
                        "size_fetch_attempts": (1 if total_length > 0 else 0),
                        "error_count": 0,
                        "download_type": download_type,
                        "matched_rule": matched_rule_name,
                        "rule_speed_limit": rule_speed,
                        "proxy_url": info.get("proxy_url", ""),
                    }

                    q.downloads_info[download_id]["status"] = final_status
                    q.downloads_info[download_id]["totalLength"] = total_length
                    q.downloads_info[download_id]["aria2_gid"] = aria2_gid
                    q.downloads_info[download_id]["matched_rule"] = matched_rule_name
                    q.downloads_info[download_id]["rule_speed_limit"] = rule_speed
                    restored_count += 1

                for download_id in to_remove:
                    q.downloads.remove(download_id)
                    if download_id in q.downloads_info:
                        del q.downloads_info[download_id]
                    if download_id in self._all_downloads:
                        del self._all_downloads[download_id]

            if needs_save:
                self.store.save()

            print(f"Loaded {restored_count} download(s)")
            print(f"📊 _all_downloads has {len(self._all_downloads)} entries")

            for download_id, data in self._all_downloads.items():
                if data.get("status") not in ("complete", "error", "removed"):
                    data["status"] = "paused"

            for q in self.store.queues:
                q.paused = True
            self.store.save()

            print(
                f"⏸️ [Restore] All downloads set to paused "
                f"({len(self._all_downloads)} items)"
            )

        finally:
            self.aria2.on_error = original_on_error

    def _save_downloads_info(self) -> None:
        for q in self.store.queues:
            for gid in q.downloads:
                if gid in self._all_downloads:
                    dl = self._all_downloads[gid]
                    if gid not in q.downloads_info:
                        q.downloads_info[gid] = {}

                    name = dl.get("name", "")
                    if not name or name == "Unknown":
                        name = q.downloads_info[gid].get("name", "")
                    if not name or name == "Unknown":
                        files = dl.get("files", [])
                        if files and files[0].get("path"):
                            name = os.path.basename(files[0]["path"])
                    if not name or name == "Unknown":
                        url = q.downloads_info[gid].get("url", "")
                        if url:
                            name = url.split("/")[-1].split("?")[0]
                    if not name:
                        name = "Unknown"

                    total_length = dl.get("totalLength", 0)
                    if total_length == 0:

                        total_length = q.downloads_info[gid].get("totalLength", 0)
                    if total_length == 0:

                        files = dl.get("files", [])
                        if files and files[0].get("length"):
                            try:
                                total_length = int(files[0]["length"])
                            except (ValueError, TypeError):
                                pass
                    if total_length == 0:

                        try:
                            if self.aria2 and self.aria2.is_connected():
                                status_data = self.aria2.get_status(gid)
                                if status_data:
                                    aria2_total = int(status_data.get("totalLength", 0))
                                    if aria2_total > 0:
                                        total_length = aria2_total
                        except:
                            pass

                    q.downloads_info[gid].update(
                        {
                            "url": q.downloads_info[gid].get("url", ""),
                            "name": name,
                            "totalLength": total_length,
                            "completedLength": dl.get("completedLength", 0),
                            "status": dl.get("status", "unknown"),
                            "files": dl.get("files", []),
                            "category": dl.get("category", "📁 Other"),
                            "error_count": dl.get("error_count", 0),
                            "errorMessage": dl.get("errorMessage", ""),
                            "download_type": dl.get("download_type", "normal"),
                        }
                    )

    def closeEvent(self, event: QCloseEvent) -> None:
        # ── Is anything actively downloading? ──
        has_active = False
        for q in self.store.queues:
            for gid in q.downloads:
                if gid in self._all_downloads:
                    status = self._all_downloads[gid].get("status", "")
                    if status in ("active", "waiting", "downloading"):
                        has_active = True
                        break
            if has_active:
                break

        if has_active:
            reply = QMessageBox.question(
                self,
                "Downloads in Progress",
                "There are active downloads. Closing the main window will "
                "keep downloads running in the background.\n\n"
                "Do you want to close the main window?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            # C41 fix: "No" must keep the window open, not hide it.
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return

            self.hide()
            self.tray.showMessage(
                "FelfelDM",
                "Downloads are running in the background.\n"
                "Right-click the tray icon to show the main window.",
                QSystemTrayIcon.MessageIcon.Information,
                3000,
            )
            event.ignore()
            return

        # ── No active downloads: hide to tray, or quit if no tray ──
        if hasattr(self, "tray") and self.tray.isVisible():
            self.hide()
            event.ignore()
        else:
            self.quit_app()
            event.accept()

    def quit_app(self) -> None:
        """Quit the application for real (tray → Quit, or no tray).

        C43 fix: iterate _video_dialogs.values(), not .items() — the
        old code passed (key, value) tuples to .close(), and every
        close silently failed inside the except block.

        C44 fix: call worker.stop() explicitly, then wait for the
        thread to finish. quit() is a no-op on a QThread with a custom
        run(), so the old code left BackendWorker polling forever and
        yt-dlp children (which use start_new_session=True) survived
        the app's exit and kept writing to .part files.
        """
        print("🛑 Shutting down...")

        # ── 1. Stop the scheduler (only on real quit) ──
        if hasattr(self, "schedule_thread") and self.schedule_thread:
            try:
                self.schedule_thread.stop()
            except Exception as e:
                print(f"⚠️ Error stopping scheduler: {e}")

        # ── 2. Stop retry timers ──
        if self._countdown_timer:
            self._countdown_timer.stop()
        for t in self._retry_timers.values():
            try:
                t.stop()
            except Exception:
                pass
        self._retry_timers.clear()
        self._retry_state.clear()
        self._retrying_gids.clear()

        # ── 3. Stop the speed-update timer ──
        if hasattr(self, "speed_update_timer") and self.speed_update_timer:
            self.speed_update_timer.stop()

        # ── 4. Splash screen ──
        theme_setting: str = self.store.settings.get("theme", "auto")
        is_dark: bool = self._detect_theme(theme_setting)
        shutdown_dialog = SplashScreen(is_dark=is_dark)
        shutdown_dialog.show()
        QApplication.processEvents()

        # ── 5. Ask backend to save session + pause downloads ──
        shutdown_dialog.update_status("Saving session...", 10)
        try:
            if self.worker:
                self.worker.save_session_requested.emit()
        except Exception:
            pass

        shutdown_dialog.update_status("Pausing downloads...", 20)
        for q in self.store.queues:
            for gid in q.downloads:
                try:
                    if gid in self._all_downloads:
                        status = self._all_downloads[gid].get("status", "")
                        if status in ("active", "waiting", "downloading"):
                            if self.worker:
                                self._worker_pause(gid)
                            if (
                                self._all_downloads[gid].get("download_type")
                                == "video"
                            ):
                                self._all_downloads[gid]["status"] = "paused"
                                self._all_downloads[gid]["downloadSpeed"] = 0
                except Exception:
                    pass
            q.paused = True

        shutdown_dialog.update_status("Saving data...", 35)
        try:
            self._save_downloads_info()
            self.store.save()
        except Exception as e:
            print(f"⚠️ Error saving data: {e}")

        # ── 6. Close all progress dialogs ──
        shutdown_dialog.update_status("Closing dialogs...", 45)
        for gid, dialog in list(self._progress_dialogs.items()):
            try:
                dialog.close()
                dialog.deleteLater()
            except Exception:
                pass
        self._progress_dialogs.clear()

        # C43 fix: values(), not items().
        for dlg in list(self._video_dialogs.values()):
            try:
                dlg.close()
                dlg.deleteLater()
            except Exception:
                pass
        self._video_dialogs.clear()

        # ── 7. Stop BackendWorker properly (C44 fix) ──
        shutdown_dialog.update_status("Stopping backend...", 55)
        if hasattr(self, "worker") and self.worker:
            try:
                # Ask the worker loop to exit and cancel all yt-dlp
                # children so they don't survive as orphans.
                self.worker.stop()
            except Exception as e:
                print(f"⚠️ Error stopping worker: {e}")
            try:
                self.worker.wait(3000)
            except Exception:
                pass

        # ── 8. Shutdown aria2 ──
        shutdown_dialog.update_status("Stopping aria2...", 70)
        try:
            if self.aria2:
                self.aria2.save_session()
                self._stop_own_aria2()
        except Exception as e:
            print(f"⚠️ Error during aria2 shutdown: {e}")

        # ── 9. Flush datastore ──
        shutdown_dialog.update_status("Closing data store...", 85)
        if hasattr(self.store, "shutdown"):
            try:
                self.store.shutdown()
            except Exception as e:
                print(f"⚠️ Error closing datastore: {e}")

        # ── 10. Stop the local extension server ──
        # Never stopped before: the port stayed bound until the process was
        # reaped, so a quick restart could hit "address already in use" and
        # the extension saw a dead server it still believed was up.
        shutdown_dialog.update_status("Stopping local server...", 92)
        if getattr(self, "local_server", None) is not None:
            try:
                self.local_server.stop()
            except Exception as e:
                print(f"⚠️ Error stopping local server: {e}")
            self.local_server = None

        shutdown_dialog.update_status("👋 Goodbye...", 100)
        if hasattr(self, "tray"):
            try:
                self.tray.hide()
            except Exception:
                pass

        QApplication.processEvents()

        print("🛑 Shutdown complete")
        import sys

        sys.exit(0)
