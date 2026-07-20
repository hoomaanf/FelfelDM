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
    def __init__(self, host="http://localhost", port=6800, secret="", config_dir=None):
        self.host = host
        self.port = port
        self.secret = secret
        self.on_error = None
        self._connected = False
        self._aria2_process = None

        self._timeout = 2
        self._retry_count = 2
        self._retry_delay = 0.2

        self.config_dir = config_dir or os.path.expanduser("~/.config/felfelDM")
        self.session_file = os.path.join(self.config_dir, "aria2.session")
        self._ensure_session_file()

    def _ensure_session_file(self):
        try:
            os.makedirs(self.config_dir, exist_ok=True)
            if not os.path.exists(self.session_file):
                open(self.session_file, "w").close()
                print(f"📁 Created session file: {self.session_file}")
        except Exception as e:
            print(f"⚠️ Could not create session file: {e}")

    def _is_youtube_gid(self, gid: str) -> bool:
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
        return f"{self.host}:{self.port}/jsonrpc"

    def _call(self, method: str, params: List = None) -> Optional[Dict]:
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
                try:
                    error_body = e.read().decode("utf-8")
                except:
                    error_body = ""

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

    def start_aria2(self, max_concurrent: int = 5, max_tries: int = 5) -> bool:
        try:
            self._ensure_session_file()

            cmd = [
                "aria2c",
                "--enable-rpc",
                "--rpc-listen-all",
                "--rpc-allow-origin-all",
                "--daemon",
                f"--rpc-listen-port={self.port}",
                f"--max-concurrent-downloads={max_concurrent}",
                "--max-connection-per-server=16",
                "--split=16",
                "--continue=true",
                "--always-resume=true",
                "--retry-wait=2",
                f"--max-tries={max_tries}",
                "--min-split-size=1M",
                f"--save-session={self.session_file}",
                f"--input-file={self.session_file}",
                "--save-session-interval=60",
                "--timeout=5",
                "--connect-timeout=5",
            ]

            if self.secret:
                cmd.append(f"--rpc-secret={self.secret}")

            print(f"🚀 Starting aria2 with session file: {self.session_file}")
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            for _ in range(30):
                time.sleep(0.3)
                if self.is_connected():
                    print(f"✅ aria2 started on port {self.port}")
                    return True

            print(f"❌ aria2 failed to start on port {self.port}")
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
        return self._call("aria2.getVersion")

    def get_global_stat(self) -> Optional[Dict]:
        return self._call("aria2.getGlobalStat")

    def tell_active(self) -> List[Dict]:
        result = self._call("aria2.tellActive")
        return result if result else []

    def tell_waiting(self, offset: int = 0, num: int = 100) -> List[Dict]:
        result = self._call("aria2.tellWaiting", [offset, num])
        return result if result else []

    def tell_stopped(self, offset: int = 0, num: int = 100) -> List[Dict]:
        result = self._call("aria2.tellStopped", [offset, num])
        return result if result else []

    def get_status(self, gid: str) -> Optional[Dict]:
        if not gid:
            return None

        if self._is_youtube_gid(gid):
            return None

        return self._call("aria2.tellStatus", [gid])

    def tell_status(self, gid: str) -> Optional[Dict]:
        return self.get_status(gid)

    def add_url(self, url: str, options: Dict = None) -> Optional[str]:
        if not url:
            return None

        if options is None:
            options = {}

        pause_after_add = options.pop("pause", False)

        options = {k: v for k, v in options.items() if v is not None and v != ""}

        params = [[url], options]

        result = self._call("aria2.addUri", params)

        if result and pause_after_add:
            self.pause(result)
        return result

    def add_uris(self, urls: List[str], options: Dict = None) -> List[Optional[str]]:
        gids = []
        for url in urls:
            gid = self.add_url(url, options)
            gids.append(gid)
        return gids

    def pause(self, gid: str) -> bool:
        if not gid:
            return False

        if self._is_youtube_gid(gid):
            return False

        result = self._call("aria2.pause", [gid])
        return result is not None

    def force_pause(self, gid: str) -> bool:
        if not gid:
            return False

        if self._is_youtube_gid(gid):
            return False

        result = self._call("aria2.forcePause", [gid])
        return result is not None

    def resume(self, gid: str) -> bool:
        if not gid:
            return False

        if self._is_youtube_gid(gid):
            return False

        result = self._call("aria2.unpause", [gid])
        return result is not None

    def unpause(self, gid: str) -> bool:
        return self.resume(gid)

    def remove(self, gid: str) -> bool:
        if not gid:
            return False

        if self._is_youtube_gid(gid):
            return False

        result = self._call("aria2.remove", [gid])
        return result is not None

    def force_remove(self, gid: str) -> bool:
        if not gid:
            return False

        if self._is_youtube_gid(gid):
            return False

        result = self._call("aria2.forceRemove", [gid])
        return result is not None

    def change_global_option(self, options: Dict) -> bool:
        if not options:
            return False

        result = self._call("aria2.changeGlobalOption", [options])
        return result is not None

    def get_global_option(self) -> Optional[Dict]:
        return self._call("aria2.getGlobalOption")

    def set_download_speed_limit(self, gid: str, speed_kb: int) -> bool:
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
        if not gid or not options:
            return False

        if self._is_youtube_gid(gid):
            return False

        result = self._call("aria2.changeOption", [gid, options])
        return result is not None

    def get_option(self, gid: str) -> Optional[Dict]:
        if not gid:
            return None

        if self._is_youtube_gid(gid):
            return None

        return self._call("aria2.getOption", [gid])

    def set_global_proxy(self, proxy_config) -> bool:
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
        result = self._call("aria2.pauseAll")
        return result is not None

    def force_pause_all(self) -> bool:
        result = self._call("aria2.forcePauseAll")
        return result is not None

    def resume_all(self) -> bool:
        result = self._call("aria2.unpauseAll")
        return result is not None

    def unpause_all(self) -> bool:
        return self.resume_all()

    def purge_download_result(self) -> bool:
        result = self._call("aria2.purgeDownloadResult")
        return result is not None

    def save_session(self) -> bool:
        result = self._call("aria2.saveSession")
        return result is not None

    def shutdown(self) -> bool:
        try:

            self.save_session()
            time.sleep(0.5)

            result = self._call("aria2.shutdown")

            if result is not None:
                self._connected = False
                print("✅ aria2 shutdown successful")
                return True
            else:

                print("⚠️ aria2 shutdown returned None, trying force_shutdown...")
                return self.force_shutdown()

        except Exception as e:
            print(f"⚠️ Error during aria2 shutdown: {e}")
            try:

                subprocess.run(["pkill", "-f", "aria2c"], capture_output=True)
                print("✅ aria2 killed via pkill")
                return True
            except Exception as e2:
                print(f"❌ Could not kill aria2: {e2}")
                return False

    def force_shutdown(self) -> bool:
        try:
            result = self._call("aria2.forceShutdown")
            if result is not None:
                self._connected = False
                print("✅ aria2 force shutdown successful")
                return True
            return False
        except Exception as e:
            print(f"⚠️ Error during force shutdown: {e}")
            return False

    def get_files(self, gid: str) -> Optional[List[Dict]]:
        if not gid:
            return None

        if self._is_youtube_gid(gid):
            return None

        return self._call("aria2.getFiles", [gid])

    def get_peers(self, gid: str) -> Optional[List[Dict]]:
        if not gid:
            return None

        if self._is_youtube_gid(gid):
            return None

        return self._call("aria2.getPeers", [gid])

    def get_servers(self, gid: str) -> Optional[List[Dict]]:
        if not gid:
            return None

        if self._is_youtube_gid(gid):
            return None

        return self._call("aria2.getServers", [gid])

    def change_position(
        self, gid: str, pos: int, how: str = "POS_SET"
    ) -> Optional[int]:
        if not gid:
            return None

        if self._is_youtube_gid(gid):
            return None

        return self._call("aria2.changePosition", [gid, pos, how])

    def get_gid_status(self, gid: str) -> Optional[Dict]:
        try:
            return self.get_status(gid)
        except:
            return None

    def is_download_active(self, gid: str) -> bool:
        status = self.get_status(gid)
        if not status:
            return False
        return status.get("status") in ["active", "waiting"]

    def is_download_complete(self, gid: str) -> bool:
        status = self.get_status(gid)
        if not status:
            return False
        return status.get("status") == "complete"

    def is_download_paused(self, gid: str) -> bool:
        status = self.get_status(gid)
        if not status:
            return False
        return status.get("status") == "paused"

    def get_download_progress(self, gid: str) -> Optional[float]:
        status = self.get_status(gid)
        if not status:
            return None

        total = int(status.get("totalLength", 0))
        completed = int(status.get("completedLength", 0))

        if total == 0:
            return 0.0
        return (completed / total) * 100

    def get_download_speed(self, gid: str) -> Optional[int]:
        status = self.get_status(gid)
        if not status:
            return None
        return int(status.get("downloadSpeed", 0))

    def get_download_info_from_file(self, gid: str) -> Optional[Dict]:
        try:
            status = self.get_status(gid)
            if not status:
                return None

            files = status.get("files", [])
            if not files:
                return None

            for file_info in files:
                path = file_info.get("path", "")
                aria2_file = path + ".aria2"
                if path and os.path.exists(aria2_file):
                    try:
                        with open(aria2_file, "rb") as f:
                            f.seek(8)
                            total_bytes = f.read(8)
                            completed_bytes = f.read(8)

                            total_length = 0
                            completed_length = 0

                            if len(total_bytes) == 8:
                                total_length = int.from_bytes(
                                    total_bytes, byteorder="little", signed=False
                                )
                            if len(completed_bytes) == 8:
                                completed_length = int.from_bytes(
                                    completed_bytes, byteorder="little", signed=False
                                )

                            if total_length > 0:
                                return {
                                    "totalLength": total_length,
                                    "completedLength": completed_length,
                                }
                    except Exception as e:
                        print(f"⚠️ Could not read .aria2 file: {e}")

            return None
        except Exception as e:
            print(f"⚠️ Error getting download info from file: {e}")
            return None
