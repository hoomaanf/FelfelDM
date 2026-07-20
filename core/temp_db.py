# core/temp_db.py

import sqlite3
import threading
from typing import Optional, Dict, List


class TempDB:

    def __init__(self):
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(":memory:", check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_tables()

    def _init_tables(self):
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS active_downloads (
                    gid TEXT PRIMARY KEY,
                    status TEXT,
                    progress INTEGER,
                    speed INTEGER,
                    eta TEXT,
                    name TEXT,
                    queue_name TEXT,
                    totalLength INTEGER DEFAULT 0,
                    completedLength INTEGER DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS active_queues (
                    name TEXT PRIMARY KEY,
                    is_active INTEGER,
                    shutdown_after_finish INTEGER,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )
            self._conn.commit()

    def update_download_status(
        self,
        gid: str,
        status: str,
        progress: int = 0,
        speed: int = 0,
        eta: str = "",
        name: str = "",
        totalLength: int = 0,
        completedLength: int = 0,
        queue_name: str = "",
    ):
        with self._lock:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO active_downloads 
                (gid, status, progress, speed, eta, name, queue_name, totalLength, completedLength, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
                (
                    gid,
                    status,
                    progress,
                    speed,
                    eta,
                    name,
                    queue_name,
                    totalLength,
                    completedLength,
                ),
            )
            self._conn.commit()

    def get_active_downloads(self) -> List[Dict]:
        with self._lock:
            cursor = self._conn.execute(
                "SELECT * FROM active_downloads ORDER BY updated_at DESC"
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_download(self, gid: str) -> Optional[Dict]:
        with self._lock:
            cursor = self._conn.execute(
                "SELECT * FROM active_downloads WHERE gid = ?", (gid,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def remove_download(self, gid: str):
        with self._lock:
            self._conn.execute("DELETE FROM active_downloads WHERE gid = ?", (gid,))
            self._conn.commit()

    def clear_all(self):
        with self._lock:
            self._conn.execute("DELETE FROM active_downloads")
            self._conn.commit()

    def get_active_count(self) -> int:
        with self._lock:
            cursor = self._conn.execute(
                "SELECT COUNT(*) as count FROM active_downloads"
            )
            return cursor.fetchone()["count"]

    def close(self):
        with self._lock:
            self._conn.close()
