# core/aria2_rpc.py

import json
import subprocess
import time
import re
import socket
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

        # تنظیمات aria2 برای زمان‌های مختلف
        self._timeout = 10
        self._retry_count = 3

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
        """فراخوانی متد RPC"""
        if params is None:
            params = []

        # اگر secret وجود دارد، به params اضافه کن
        if self.secret:
            params = [f"token:{self.secret}"] + params

        payload = {
            "jsonrpc": "2.0",
            "id": "felfeldm",
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
                        if "Invalid GID" in error_msg:
                            return None
                        if self.on_error:
                            self.on_error(f"aria2 error: {error_msg}")
                        return None
                    return result.get("result")
            except urllib.error.URLError as e:
                if attempt < self._retry_count - 1:
                    time.sleep(0.5)
                    continue
                if self.on_error:
                    self.on_error(f"Connection error: {e}")
                return None
            except Exception as e:
                if attempt < self._retry_count - 1:
                    time.sleep(0.5)
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

            # منتظر بمان تا aria2 راه‌اندازی شود
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

    # ===== متدهای اصلی =====

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

        # ===== SKIP برای GIDهای یوتیوب =====
        if self._is_youtube_gid(gid):
            return None

        return self._call("aria2.tellStatus", [gid])

    def tell_status(self, gid: str) -> Optional[Dict]:
        """همان get_status (برای سازگاری)"""
        return self.get_status(gid)

    def add_url(self, url: str, options: Dict = None) -> Optional[str]:
        """افزودن دانلود جدید با URL"""
        if not url:
            return None

        if options is None:
            options = {}

        # تبدیل options به فرمت aria2
        aria2_options = []
        for key, value in options.items():
            if value is not None and value != "":
                aria2_options.append(f"{key}={value}")

        params = [[url], aria2_options]

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

        # ===== SKIP برای GIDهای یوتیوب =====
        if self._is_youtube_gid(gid):
            return False

        result = self._call("aria2.pause", [gid])
        return result is not None

    def force_pause(self, gid: str) -> bool:
        """توقف اجباری دانلود"""
        if not gid:
            return False

        # ===== SKIP برای GIDهای یوتیوب =====
        if self._is_youtube_gid(gid):
            return False

        result = self._call("aria2.forcePause", [gid])
        return result is not None

    def resume(self, gid: str) -> bool:
        """ادامه دانلود"""
        if not gid:
            return False

        # ===== SKIP برای GIDهای یوتیوب =====
        if self._is_youtube_gid(gid):
            return False

        result = self._call("aria2.unpause", [gid])
        return result is not None

    def remove(self, gid: str) -> bool:
        """حذف دانلود"""
        if not gid:
            return False

        # ===== SKIP برای GIDهای یوتیوب =====
        if self._is_youtube_gid(gid):
            return False

        result = self._call("aria2.remove", [gid])
        return result is not None

    def change_global_option(self, options: Dict) -> bool:
        """تغییر تنظیمات کلی"""
        if not options:
            return False

        result = self._call("aria2.changeGlobalOption", [options])
        return result is not None

    def set_download_speed_limit(self, gid: str, speed_kb: int) -> bool:
        """تنظیم محدودیت سرعت برای یک دانلود"""
        if not gid:
            return False

        # ===== SKIP برای GIDهای یوتیوب =====
        if self._is_youtube_gid(gid):
            return False

        if speed_kb <= 0:
            options = {"max-download-limit": "0"}
        else:
            options = {"max-download-limit": f"{speed_kb}K"}

        result = self._call("aria2.changeOption", [gid, options])
        return result is not None

    def set_global_proxy(self, proxy_config) -> bool:
        """تنظیم پروکسی کلی"""
        if proxy_config and proxy_config.is_valid():
            proxy_url = proxy_config._build_proxy_url()
            options = {"all-proxy": proxy_url}
        else:
            options = {"all-proxy": ""}

        result = self._call("aria2.changeGlobalOption", [options])
        return result is not None
