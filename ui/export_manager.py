# ui/export_manager.py

import os
import json
import csv
from datetime import datetime
from typing import List, Dict, Optional
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtCore import QObject

from utils.helpers import format_size, format_speed


class ExportManager(QObject):
    """مدیریت عملیات Export دانلودها"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent

    def export_downloads(
        self, queue, format_name: str, file_path: str, include_headers: bool
    ):
        """
        اجرای عملیات Export
        Returns: (success: bool, message: str)
        """
        try:
            # گرفتن لیست دانلودها
            downloads = self._get_downloads_data(queue)

            if not downloads:
                return False, "Queue is empty."

            # انتخاب متد مناسب بر اساس فرمت
            if "Clipboard" in format_name:
                text = self._to_text(downloads, format_name, include_headers)
                QApplication.clipboard().setText(text)
                return True, f"Copied {len(downloads)} downloads to clipboard"

            if "URLs Only" in format_name:
                self._export_urls_only(downloads, file_path)
            elif "URLs + Names" in format_name:
                self._export_urls_names(downloads, file_path, include_headers)
            elif "Full Details (JSON)" in format_name:
                self._export_json_full(downloads, file_path, queue)
            elif "Full Details (CSV)" in format_name:
                self._export_csv_full(downloads, file_path, include_headers, queue)
            elif "Full Details (HTML)" in format_name:
                self._export_html_full(downloads, file_path, queue)
            else:
                return False, f"Unknown format: {format_name}"

            return (
                True,
                f"Exported {len(downloads)} downloads from '{queue.name}'\n{file_path}",
            )

        except Exception as e:
            return False, f"Error: {str(e)}"

    def _get_downloads_data(self, queue):
        """دریافت لیست دانلودها با اطلاعات کامل"""
        downloads = []
        for gid in queue.downloads:
            if (
                hasattr(self.parent, "_all_downloads")
                and gid in self.parent._all_downloads
            ):
                dl = self.parent._all_downloads[gid].copy()
            else:
                dl = {}

            # اگه url نداره، از queue.downloads_info بگیر
            if not dl.get("url"):
                info = queue.downloads_info.get(gid, {})
                dl["url"] = info.get("url", "")
                if not dl.get("name"):
                    dl["name"] = info.get("name", "Unknown")
                if not dl.get("status"):
                    dl["status"] = info.get("status", "unknown")
                if not dl.get("totalLength"):
                    dl["totalLength"] = info.get("totalLength", 0)
                if not dl.get("completedLength"):
                    dl["completedLength"] = info.get("completedLength", 0)
                if not dl.get("category"):
                    dl["category"] = info.get("category", "📁 Other")
                if not dl.get("download_type"):
                    dl["download_type"] = info.get("download_type", "normal")

            downloads.append(dl)

        return downloads

    def _export_urls_only(self, downloads: List[Dict], file_path: str):
        """فقط لینک‌ها (TXT)"""
        with open(file_path, "w", encoding="utf-8") as f:
            for dl in downloads:
                url = dl.get("url", "")
                if url:
                    f.write(url + "\n")

    def _export_urls_names(
        self, downloads: List[Dict], file_path: str, include_headers: bool
    ):
        """لینک‌ها + نام‌ها (CSV)"""
        with open(file_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            if include_headers:
                writer.writerow(["Name", "URL"])
            for dl in downloads:
                writer.writerow([dl.get("name", "Unknown"), dl.get("url", "")])

    def _export_json_full(self, downloads: List[Dict], file_path: str, queue):
        """اطلاعات کامل (JSON)"""
        data = {
            "exported_at": datetime.now().isoformat(),
            "queue": queue.name,
            "count": len(downloads),
            "downloads": downloads,
        }
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _export_csv_full(
        self, downloads: List[Dict], file_path: str, include_headers: bool, queue
    ):
        """اطلاعات کامل (CSV)"""
        fieldnames = [
            "name",
            "url",
            "status",
            "totalLength",
            "completedLength",
            "progress",
            "downloadSpeed",
            "category",
            "download_type",
        ]

        with open(file_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if include_headers:
                writer.writeheader()

            for dl in downloads:
                total = self._to_int(dl.get("totalLength", 0))
                completed = self._to_int(dl.get("completedLength", 0))
                progress = int((completed / total * 100) if total > 0 else 0)

                row = {
                    "name": dl.get("name", "Unknown"),
                    "url": dl.get("url", ""),
                    "status": dl.get("status", "unknown"),
                    "totalLength": format_size(total),
                    "completedLength": format_size(completed),
                    "progress": f"{progress}%",
                    "downloadSpeed": format_speed(
                        self._to_int(dl.get("downloadSpeed", 0))
                    ),
                    "category": dl.get("category", "📁 Other"),
                    "download_type": dl.get("download_type", "normal"),
                }
                writer.writerow(row)

    def _export_html_full(self, downloads: List[Dict], file_path: str, queue):
        """اطلاعات کامل (HTML)"""
        html = self._generate_html(downloads, queue)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(html)

    def _to_text(self, downloads: List[Dict], format_name: str, include_headers: bool):
        """تولید متن برای کلیپ‌بورد"""
        lines = []

        if "URLs Only" in format_name:
            for dl in downloads:
                if dl.get("url"):
                    lines.append(dl["url"])

        elif "URLs + Names" in format_name:
            if include_headers:
                lines.append("Name\tURL")
            for dl in downloads:
                lines.append(f"{dl.get('name', 'Unknown')}\t{dl.get('url', '')}")

        else:  # Full Details
            if include_headers:
                lines.append(
                    "Name\tStatus\tSize\tDownloaded\tProgress\tSpeed\tCategory\tURL"
                )
            for dl in downloads:
                total = self._to_int(dl.get("totalLength", 0))
                completed = self._to_int(dl.get("completedLength", 0))
                progress = int((completed / total * 100) if total > 0 else 0)

                lines.append(
                    f"{dl.get('name', 'Unknown')}\t"
                    f"{dl.get('status', 'unknown')}\t"
                    f"{format_size(total)}\t"
                    f"{format_size(completed)}\t"
                    f"{progress}%\t"
                    f"{format_speed(self._to_int(dl.get('downloadSpeed', 0)))}\t"
                    f"{dl.get('category', '📁 Other')}\t"
                    f"{dl.get('url', '')}"
                )

        return "\n".join(lines)

    def _generate_html(self, downloads: List[Dict], queue):
        """تولید HTML"""
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>FelfelDM - {queue.name} Export</title>
            <style>
                body {{ font-family: 'Segoe UI', Arial, sans-serif; padding: 20px; background: #f5f5f5; }}
                .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 30px; border-radius: 12px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
                h1 {{ color: #2d2d2d; }}
                .meta {{ color: #666; margin-bottom: 20px; padding-bottom: 15px; border-bottom: 2px solid #eee; }}
                .meta span {{ display: inline-block; margin-right: 20px; }}
                table {{ border-collapse: collapse; width: 100%; }}
                th {{ background: #2d2d2d; color: white; padding: 12px 16px; text-align: left; position: sticky; top: 0; }}
                td {{ padding: 10px 16px; border-bottom: 1px solid #eee; }}
                tr:hover {{ background: #f8f8f8; }}
                .status {{ display: inline-block; padding: 3px 12px; border-radius: 12px; font-size: 12px; font-weight: bold; }}
                .status-active {{ background: #27ae60; color: white; }}
                .status-paused {{ background: #f39c12; color: white; }}
                .status-complete {{ background: #3498db; color: white; }}
                .status-error {{ background: #e74c3c; color: white; }}
                .status-waiting {{ background: #95a5a6; color: white; }}
                .badge {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; background: #eee; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🌶️ FelfelDM - Downloads Export</h1>
                <div class="meta">
                    <span>Queue: <b>{queue.name}</b></span>
                    <span>Total: <b>{len(downloads)}</b> downloads</span>
                    <span>Exported: <b>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</b></span>
                </div>
                <table>
                    <thead>
                        <tr>
                            <th>#</th>
                            <th>Name</th>
                            <th>URL</th>
                            <th>Status</th>
                            <th>Size</th>
                            <th>Downloaded</th>
                            <th>Progress</th>
                            <th>Speed</th>
                            <th>Category</th>
                        </tr>
                    </thead>
                    <tbody>
        """

        for i, dl in enumerate(downloads, 1):
            total = self._to_int(dl.get("totalLength", 0))
            completed = self._to_int(dl.get("completedLength", 0))
            progress = int((completed / total * 100) if total > 0 else 0)

            status = dl.get("status", "unknown")
            status_class = {
                "active": "status-active",
                "downloading": "status-active",
                "paused": "status-paused",
                "complete": "status-complete",
                "completed": "status-complete",
                "error": "status-error",
                "waiting": "status-waiting",
            }.get(status, "")

            status_text = {
                "active": "Downloading",
                "downloading": "Downloading",
                "paused": "Paused",
                "complete": "Complete",
                "completed": "Complete",
                "error": "Error",
                "waiting": "Waiting",
            }.get(status, status.title())

            url = (
                dl.get("url", "")[:60] + "..."
                if len(dl.get("url", "")) > 60
                else dl.get("url", "")
            )

            html += f"""
                    <tr>
                        <td>{i}</td>
                        <td><b>{dl.get('name', 'Unknown')}</b></td>
                        <td style="font-size: 12px; color: #555; word-break: break-all;">{url}</td>
                        <td><span class="status {status_class}">{status_text}</span></td>
                        <td>{format_size(total)}</td>
                        <td>{format_size(completed)}</td>
                        <td>{progress}%</td>
                        <td>{format_speed(self._to_int(dl.get('downloadSpeed', 0)))}</td>
                        <td><span class="badge">{dl.get('category', '📁 Other')}</span></td>
                    </tr>
            """

        html += """
                    </tbody>
                </table>
            </div>
        </body>
        </html>
        """

        return html

    @staticmethod
    def _to_int(value) -> int:
        """تبدیل مطمئن به int"""
        try:
            return int(value) if value else 0
        except (ValueError, TypeError):
            return 0
