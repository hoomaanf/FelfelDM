# core/aria2_handler.py

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot
import os


class Aria2Handler(QObject):
    """
    این کلاس در ترد کارگر زندگی می‌کند و تمام عملیات‌های blocking
    با aria2 را انجام می‌دهد.
    """

    operation_result = pyqtSignal(str, object)  # operation_name, result

    def __init__(self, aria2, store):
        super().__init__()
        self.aria2 = aria2
        self.store = store

    @pyqtSlot(str)
    def resume(self, gid: str):
        print(f"🔍 [Worker] Received resume request for {gid}")
        try:
            self.aria2.resume(gid)
            self.operation_result.emit("resume", {"gid": gid, "success": True})
            print(f"▶️ [Handler] Resumed {gid}")
        except Exception as e:
            self.operation_result.emit(
                "resume", {"gid": gid, "success": False, "error": str(e)}
            )
            print(f"⚠️ [Handler] Resume failed for {gid}: {e}")

    @pyqtSlot(str)
    def pause(self, gid: str):
        try:
            self.aria2.pause(gid)
            self.operation_result.emit("pause", {"gid": gid, "success": True})
            print(f"⏸️ [Handler] Paused {gid}")
        except Exception as e:
            self.operation_result.emit(
                "pause", {"gid": gid, "success": False, "error": str(e)}
            )
            print(f"⚠️ [Handler] Pause failed for {gid}: {e}")

    @pyqtSlot(str)
    def remove(self, gid: str):
        try:
            self.aria2.remove(gid)
            self.operation_result.emit("remove", {"gid": gid, "success": True})
            print(f"🗑️ [Handler] Removed {gid}")
        except Exception as e:
            self.operation_result.emit(
                "remove", {"gid": gid, "success": False, "error": str(e)}
            )
            print(f"⚠️ [Handler] Remove failed for {gid}: {e}")

    @pyqtSlot(str, dict)
    def add_url(self, url: str, options: dict):
        try:
            new_gid = self.aria2.add_url(url, options)
            self.operation_result.emit(
                "add_url", {"url": url, "gid": new_gid, "success": True}
            )
            print(f"➕ [Handler] Added URL: {url} -> {new_gid}")
        except Exception as e:
            self.operation_result.emit(
                "add_url", {"url": url, "gid": None, "success": False, "error": str(e)}
            )
            print(f"⚠️ [Handler] Add URL failed: {e}")

    @pyqtSlot(str, dict)
    def add_torrent(self, torrent_data: str, options: dict):
        """اضافه کردن دانلود تورنت"""
        try:
            # چک کن فایل هست یا base64
            if os.path.exists(torrent_data):
                new_gid = self.aria2.add_torrent(torrent_data, options)
            else:
                new_gid = self.aria2.add_magnet(torrent_data, options)

            self.operation_result.emit("add_torrent", {"gid": new_gid, "success": True})
            print(f"🧲 [Handler] Added torrent: {new_gid}")
        except Exception as e:
            self.operation_result.emit(
                "add_torrent", {"gid": None, "success": False, "error": str(e)}
            )
            print(f"⚠️ [Handler] Add torrent failed: {e}")

    @pyqtSlot(str)
    def re_add(self, old_gid: str):
        """Re-add a download using stored info"""
        try:
            url = None
            save_path = None
            speed_limit = 0
            for q in self.store.queues:
                if old_gid in q.downloads_info:
                    info = q.downloads_info[old_gid]
                    url = info.get("url")
                    save_path = q.save_path
                    speed_limit = getattr(q, "speed_limit", 0)
                    break

            if not url or not save_path:
                print(f"❌ [Handler] Cannot re-add: missing info for {old_gid}")
                self.operation_result.emit(
                    "re_add", {"old": old_gid, "new": None, "success": False}
                )
                return

            options = {
                "dir": save_path,
                "split": "8",
                "max-connection-per-server": "8",
                "continue": "true",
                "always-resume": "true",
            }
            if speed_limit > 0:
                options["max-download-limit"] = f"{speed_limit}K"

            new_gid = self.aria2.add_url(url, options)
            if new_gid:
                self.aria2.resume(new_gid)
                print(f"🔄 [Handler] Re-added {old_gid} -> {new_gid}")
                self.operation_result.emit(
                    "re_add", {"old": old_gid, "new": new_gid, "success": True}
                )
            else:
                self.operation_result.emit(
                    "re_add", {"old": old_gid, "new": None, "success": False}
                )
        except Exception as e:
            print(f"⚠️ [Handler] Re-add failed: {e}")
            self.operation_result.emit(
                "re_add",
                {"old": old_gid, "new": None, "success": False, "error": str(e)},
            )

    @pyqtSlot(str, int)
    def set_speed_limit(self, gid: str, speed_kb: int):
        try:
            limit = "0" if speed_kb <= 0 else f"{speed_kb}K"
            self.aria2.change_option(gid, {"max-download-limit": limit})
            self.operation_result.emit(
                "set_speed_limit", {"gid": gid, "speed": speed_kb, "success": True}
            )
            print(f"⚡ [Handler] Speed limit set for {gid}: {limit}")
        except Exception as e:
            self.operation_result.emit(
                "set_speed_limit",
                {"gid": gid, "speed": speed_kb, "success": False, "error": str(e)},
            )
            print(f"⚠️ [Handler] Set speed limit failed: {e}")

    @pyqtSlot()
    def save_session(self):
        try:
            self.aria2.save_session()
            self.operation_result.emit("save_session", {"success": True})
            print(f"💾 [Handler] Session saved")
        except Exception as e:
            self.operation_result.emit(
                "save_session", {"success": False, "error": str(e)}
            )
            print(f"⚠️ [Handler] Save session failed: {e}")

    @pyqtSlot()
    def shutdown(self):
        try:
            self.aria2.shutdown()
            self.operation_result.emit("shutdown", {"success": True})
            print(f"🛑 [Handler] aria2 shutdown")
        except Exception as e:
            self.operation_result.emit("shutdown", {"success": False, "error": str(e)})
            print(f"⚠️ [Handler] Shutdown failed: {e}")
