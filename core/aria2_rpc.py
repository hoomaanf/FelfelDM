# core/aria2_rpc.py

import json
import subprocess
import time
import re
import os
from typing import Optional, Dict, Any, List
import urllib.request
import urllib.error


class Aria2RPC:
    def __init__(self, host="http://localhost", port=6800, secret=""):
        self.host = host
        self.port = port
        self.secret = secret
        self.on_error = None
        self._connected = False
        self._aria2_process = None

        self._timeout = 10
        self._retry_count = 3
        self._retry_delay = 0.5

    def _is_youtube_gid(self, gid: str) -> bool:
        """بررسی اینکه GID مربوط به دانلود یوتیوب هست یا نه (فرمت UUID)"""
        if not gid:
            return False
        return bool(
            re.match(
                r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
                gid,
                re.IGNORECASE,
            )
        )

    def _get_url(self):
        """ساخت URL برای RPC"""
        return f"{self.host}:{self.port}/jsonrpc"

    def _call(self, method: str, params: List = None) -> Optional[Dict]:
        """فراخوانی متد RPC با مدیریت خطا"""
        if params is None:
            params = []

        if self.secret:
            params = [f"token:{self.secret}"] + params

        payload = {
            "jsonrpc": "2.0",
            "id": f"felfeldm_{int(time.time() * 1000)}",
            "method": method,
            "params": params,
        }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self._get_url(), data=data, headers={"Content-Type": "application/json"}
        )

        for attempt in range(self._retry_count):
            try:
                with urllib.request.urlopen(req, timeout=self._timeout) as response:
                    result = json.loads(response.read().decode("utf-8"))
                    if "error" in result:
                        error_msg = result["error"].get("message", str(result["error"]))
                        if "Invalid GID" in error_msg or (
                            "not found" in error_msg.lower()
                            and "gid" in error_msg.lower()
                        ):
                            print(f"ℹ️ [aria2] GID not found (ignored): {error_msg}")
                            return None
                        if self.on_error:
                            self.on_error(f"aria2 error: {error_msg}")
                        return None
                    return result.get("result")

            except urllib.error.HTTPError as e:
                print(f"❌ [aria2] HTTP Error {e.code}: {e.reason}")
                try:
                    error_body = e.read().decode("utf-8")
                    print(f"❌ [aria2] Response body: {error_body}")
                    print(f"❌ [aria2] Method: {method}")
                    print(f"❌ [aria2] Params: {params}")
                except:
                    pass

                if "GID" in error_body and "not found" in error_body:
                    return None

                if attempt < self._retry_count - 1:
                    time.sleep(self._retry_delay * (attempt + 1))
                    continue
                if self.on_error:
                    self.on_error(f"HTTP Error {e.code}: {e.reason}")
                return None

            except urllib.error.URLError as e:
                if attempt < self._retry_count - 1:
                    time.sleep(self._retry_delay * (attempt + 1))
                    continue
                if self.on_error:
                    self.on_error(f"Connection error: {e}")
                return None

            except Exception as e:
                if attempt < self._retry_count - 1:
                    time.sleep(self._retry_delay * (attempt + 1))
                    continue
                if self.on_error:
                    self.on_error(f"Error: {e}")
                return None

        return None

    def is_connected(self) -> bool:
        """بررسی اتصال به aria2"""
        try:
            result = self._call("aria2.getVersion")
            if result:
                self._connected = True
                return True
            self._connected = False
            return False
        except:
            self._connected = False
            return False

    def start_aria2(self) -> bool:
        """شروع aria2 به عنوان دیمن"""
        try:
            port = self.port
            cmd = [
                "aria2c",
                "--enable-rpc",
                "--rpc-listen-all",
                "--rpc-allow-origin-all",
                "--daemon",
                f"--rpc-listen-port={port}",
                "--max-concurrent-downloads=5",
                "--max-connection-per-server=16",
                "--split=16",
                "--continue=true",
                "--always-resume=true",
                "--retry-wait=2",
                "--max-tries=5",
                "--min-split-size=1M",
            ]

            if self.secret:
                cmd.append(f"--rpc-secret={self.secret}")

            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            for _ in range(30):
                time.sleep(0.5)
                if self.is_connected():
                    print(f"✅ aria2 started on port {port}")
                    return True

            print(f"❌ aria2 failed to start on port {port}")
            return False

        except FileNotFoundError:
            if self.on_error:
                self.on_error("aria2 not found! Please install: sudo apt install aria2")
            return False
        except Exception as e:
            if self.on_error:
                self.on_error(f"Failed to start aria2: {e}")
            return False

    def get_version(self) -> Optional[Dict]:
        """دریافت نسخه aria2"""
        return self._call("aria2.getVersion")

    def get_global_stat(self) -> Optional[Dict]:
        """دریافت آمار کلی"""
        return self._call("aria2.getGlobalStat")

    def tell_active(self) -> List[Dict]:
        """دریافت دانلودهای فعال"""
        result = self._call("aria2.tellActive")
        return result if result else []

    def tell_waiting(self, offset: int = 0, num: int = 100) -> List[Dict]:
        """دریافت دانلودهای در انتظار"""
        result = self._call("aria2.tellWaiting", [offset, num])
        return result if result else []

    def tell_stopped(self, offset: int = 0, num: int = 100) -> List[Dict]:
        """دریافت دانلودهای متوقف شده"""
        result = self._call("aria2.tellStopped", [offset, num])
        return result if result else []

    def get_status(self, gid: str) -> Optional[Dict]:
        """دریافت وضعیت یک دانلود"""
        if not gid:
            return None

        if self._is_youtube_gid(gid):
            return None

        return self._call("aria2.tellStatus", [gid])

    def tell_status(self, gid: str) -> Optional[Dict]:
        """همان get_status (برای سازگاری)"""
        return self.get_status(gid)

    def add_url(self, url: str, options: Dict = None) -> Optional[str]:
        """
        افزودن دانلود جدید با URL

        اصلاح شده: options مستقیماً به صورت dict ارسال میشه، نه list
        """
        if not url:
            return None

        if options is None:
            options = {}

        options = {k: v for k, v in options.items() if v is not None and v != ""}

        params = [[url], options]

        result = self._call("aria2.addUri", params)
        return result

    def add_uris(self, urls: List[str], options: Dict = None) -> List[Optional[str]]:
        """افزودن چندین دانلود"""
        gids = []
        for url in urls:
            gid = self.add_url(url, options)
            gids.append(gid)
        return gids

    def pause(self, gid: str) -> bool:
        """توقف موقت دانلود"""
        if not gid:
            return False

        if self._is_youtube_gid(gid):
            return False

        result = self._call("aria2.pause", [gid])
        return result is not None

    def force_pause(self, gid: str) -> bool:
        """توقف اجباری دانلود"""
        if not gid:
            return False

        if self._is_youtube_gid(gid):
            return False

        result = self._call("aria2.forcePause", [gid])
        return result is not None

    def resume(self, gid: str) -> bool:
        """ادامه دانلود"""
        if not gid:
            return False

        if self._is_youtube_gid(gid):
            return False

        result = self._call("aria2.unpause", [gid])
        return result is not None

    def unpause(self, gid: str) -> bool:
        """همان resume (برای سازگاری)"""
        return self.resume(gid)

    def remove(self, gid: str) -> bool:
        """حذف دانلود"""
        if not gid:
            return False

        if self._is_youtube_gid(gid):
            return False

        result = self._call("aria2.remove", [gid])
        return result is not None

    def force_remove(self, gid: str) -> bool:
        """حذف اجباری دانلود"""
        if not gid:
            return False

        if self._is_youtube_gid(gid):
            return False

        result = self._call("aria2.forceRemove", [gid])
        return result is not None

    def change_global_option(self, options: Dict) -> bool:
        """تغییر تنظیمات کلی"""
        if not options:
            return False

        result = self._call("aria2.changeGlobalOption", [options])
        return result is not None

    def get_global_option(self) -> Optional[Dict]:
        """دریافت تنظیمات کلی"""
        return self._call("aria2.getGlobalOption")

    def set_download_speed_limit(self, gid: str, speed_kb: int) -> bool:
        """تنظیم محدودیت سرعت برای یک دانلود"""
        if not gid:
            return False

        if self._is_youtube_gid(gid):
            return False

        if speed_kb <= 0:
            options = {"max-download-limit": "0"}
        else:
            options = {"max-download-limit": f"{speed_kb}K"}

        result = self._call("aria2.changeOption", [gid, options])
        return result is not None

    def change_option(self, gid: str, options: Dict) -> bool:
        """تغییر تنظیمات یک دانلود"""
        if not gid or not options:
            return False

        if self._is_youtube_gid(gid):
            return False

        result = self._call("aria2.changeOption", [gid, options])
        return result is not None

    def get_option(self, gid: str) -> Optional[Dict]:
        """دریافت تنظیمات یک دانلود"""
        if not gid:
            return None

        if self._is_youtube_gid(gid):
            return None

        return self._call("aria2.getOption", [gid])

    def set_global_proxy(self, proxy_config) -> bool:
        """تنظیم پروکسی کلی"""
        if (
            proxy_config
            and hasattr(proxy_config, "is_valid")
            and proxy_config.is_valid()
        ):
            proxy_url = proxy_config._build_proxy_url()
            options = {"all-proxy": proxy_url}
        else:
            options = {"all-proxy": ""}

        result = self._call("aria2.changeGlobalOption", [options])
        return result is not None

    def pause_all(self) -> bool:
        """توقف همه دانلودها"""
        result = self._call("aria2.pauseAll")
        return result is not None

    def force_pause_all(self) -> bool:
        """توقف اجباری همه دانلودها"""
        result = self._call("aria2.forcePauseAll")
        return result is not None

    def resume_all(self) -> bool:
        """ادامه همه دانلودها"""
        result = self._call("aria2.unpauseAll")
        return result is not None

    def unpause_all(self) -> bool:
        """همان resume_all (برای سازگاری)"""
        return self.resume_all()

    def purge_download_result(self) -> bool:
        """پاک کردن نتایج دانلودهای کامل شده"""
        result = self._call("aria2.purgeDownloadResult")
        return result is not None

    def save_session(self) -> bool:
        """ذخیره جلسه aria2"""
        result = self._call("aria2.saveSession")
        return result is not None

    def shutdown(self) -> bool:
        """خاموش کردن aria2"""
        result = self._call("aria2.shutdown")
        if result is not None:
            self._connected = False
            return True
        return False

    def force_shutdown(self) -> bool:
        """خاموش کردن اجباری aria2"""
        result = self._call("aria2.forceShutdown")
        if result is not None:
            self._connected = False
            return True
        return False

    def get_files(self, gid: str) -> Optional[List[Dict]]:
        """دریافت لیست فایل‌های یک دانلود"""
        if not gid:
            return None

        if self._is_youtube_gid(gid):
            return None

        return self._call("aria2.getFiles", [gid])

    def get_peers(self, gid: str) -> Optional[List[Dict]]:
        """دریافت لیست همتاهای یک دانلود"""
        if not gid:
            return None

        if self._is_youtube_gid(gid):
            return None

        return self._call("aria2.getPeers", [gid])

    def get_servers(self, gid: str) -> Optional[List[Dict]]:
        """دریافت لیست سرورهای یک دانلود"""
        if not gid:
            return None

        if self._is_youtube_gid(gid):
            return None

        return self._call("aria2.getServers", [gid])

    def change_position(
        self, gid: str, pos: int, how: str = "POS_SET"
    ) -> Optional[int]:
        """
        تغییر موقعیت دانلود در صف

        Args:
            gid: شناسه دانلود
            pos: موقعیت جدید یا مقدار جابه‌جایی
            how: روش جابه‌جایی ("POS_SET", "POS_CUR", "POS_END")
        """
        if not gid:
            return None

        if self._is_youtube_gid(gid):
            return None

        return self._call("aria2.changePosition", [gid, pos, how])

    def add_torrent(self, torrent: str, options: Dict = None) -> Optional[str]:
        """افزودن دانلود با فایل تورنت"""
        if not torrent:
            return None

        if options is None:
            options = {}

        # خواندن فایل تورنت
        try:
            with open(torrent, "rb") as f:
                torrent_data = f.read()
            import base64

            torrent_b64 = base64.b64encode(torrent_data).decode("ascii")
        except Exception as e:
            if self.on_error:
                self.on_error(f"Failed to read torrent file: {e}")
            return None

        options = {k: v for k, v in options.items() if v is not None and v != ""}
        params = [torrent_b64, options]

        return self._call("aria2.addTorrent", params)

    def add_metalink(self, metalink: str, options: Dict = None) -> Optional[str]:
        """افزودن دانلود با فایل متالینک"""
        if not metalink:
            return None

        if options is None:
            options = {}

        options = {k: v for k, v in options.items() if v is not None and v != ""}
        params = [metalink, options]

        return self._call("aria2.addMetalink", params)

    def get_gid_status(self, gid: str) -> Optional[Dict]:
        """دریافت وضعیت دانلود با GID (با هندلینگ خطا)"""
        try:
            return self.get_status(gid)
        except:
            return None

    def is_download_active(self, gid: str) -> bool:
        """بررسی اینکه دانلود فعال است یا نه"""
        status = self.get_status(gid)
        if not status:
            return False
        return status.get("status") in ["active", "waiting"]

    def is_download_complete(self, gid: str) -> bool:
        """بررسی اینکه دانلود کامل شده است یا نه"""
        status = self.get_status(gid)
        if not status:
            return False
        return status.get("status") == "complete"

    def is_download_paused(self, gid: str) -> bool:
        """بررسی اینکه دانلود متوقف شده است یا نه"""
        status = self.get_status(gid)
        if not status:
            return False
        return status.get("status") == "paused"

    def get_download_progress(self, gid: str) -> Optional[float]:
        """دریافت پیشرفت دانلود به صورت درصد"""
        status = self.get_status(gid)
        if not status:
            return None

        total = int(status.get("totalLength", 0))
        completed = int(status.get("completedLength", 0))

        if total == 0:
            return 0.0
        return (completed / total) * 100

    def get_download_speed(self, gid: str) -> Optional[int]:
        """دریافت سرعت دانلود به بایت بر ثانیه"""
        status = self.get_status(gid)
        if not status:
            return None
        return int(status.get("downloadSpeed", 0))
