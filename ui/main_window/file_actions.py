"""Open a downloaded file or its folder, copy the link."""

import os
from typing import Optional

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QApplication, QMessageBox


class FileActionsMixin:
    """Open a downloaded file or its folder, copy the link."""

    def _open_download_file(self, download_id: str) -> bool:
        """Try to open the downloaded file with the default application.

        Returns True if the file was opened, False otherwise (caller should
        fall back to the details dialog).
        """
        data = self._all_downloads.get(download_id)
        if not data:
            return False

        file_path: Optional[str] = None

        # Prefer the stored file path(s)
        for f in data.get("files", []) or []:
            p = f.get("path")
            if p:
                file_path = p
                break

        # Fallback: derive from save_path + name
        if not file_path:
            save_path = data.get("save_path") or data.get("real_path")
            name = data.get("name")
            if save_path and name:
                candidate = os.path.join(save_path, name)
                if os.path.exists(candidate):
                    file_path = candidate

        if not file_path:
            return False

        # If it's a directory, open the folder instead
        if os.path.isdir(file_path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(file_path))
            return True

        if not os.path.exists(file_path):
            # File was moved/deleted by the user — show a warning but don't crash
            QMessageBox.warning(
                self,
                "File Not Found",
                f"The downloaded file no longer exists at:\n\n{file_path}",
            )
            return False

        opened = QDesktopServices.openUrl(QUrl.fromLocalFile(file_path))
        if not opened:
            QMessageBox.warning(
                self,
                "Cannot Open File",
                f"Could not open the file with the default application:\n\n{file_path}",
            )
            return False

        return True

    def _open_folder(self, gid: str) -> None:
        try:
            folder_path = self._find_download_folder(gid)
            if folder_path and os.path.exists(folder_path):
                QDesktopServices.openUrl(QUrl.fromLocalFile(folder_path))
            else:
                QMessageBox.warning(self, "Error", f"Folder not found:\n{folder_path}")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not open folder:\n{str(e)}")

    def _find_download_folder(self, gid: str) -> Optional[str]:
        if gid in self._all_downloads:
            files = self._all_downloads[gid].get("files", [])
            if files and files[0].get("path"):
                return os.path.dirname(files[0]["path"])

        for q in self.store.queues:
            if gid in q.downloads_info:
                info = q.downloads_info[gid]
                files = info.get("files", [])
                if files and files[0].get("path"):
                    return os.path.dirname(files[0]["path"])
                dl_save_path = info.get("save_path") or q.save_path
                if dl_save_path and os.path.exists(dl_save_path):
                    return dl_save_path

        saved_data = self.store.get_video_download(gid)
        if saved_data:
            folder_path = saved_data.get("save_path", "")
            if folder_path and os.path.exists(folder_path):
                return folder_path

        return os.path.expanduser("~/Downloads")

    def _copy_link(self, gid: str) -> None:
        saved_data = self.store.get_video_download(gid)
        if saved_data:
            QApplication.clipboard().setText(saved_data.get("url", ""))
        else:
            files = self._all_downloads.get(gid, {}).get("files", [])
            if files and files[0].get("uris"):
                QApplication.clipboard().setText(files[0]["uris"][0]["uri"])
