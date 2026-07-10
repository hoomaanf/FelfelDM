import requests
import subprocess
import time
import os

class Aria2RPC:
    def __init__(self, host="http://localhost", port=6800, secret=""):
        self.url = f"{host}:{port}/jsonrpc"
        self.secret = secret
        self._id = 0
        self.on_error = None 

    def _call(self, method, params=None):
        self._id += 1
        token = f"token:{self.secret}" if self.secret else None
        p = [token] + (params or []) if token else (params or [])
        payload = {"jsonrpc": "2.0", "id": str(self._id), "method": method, "params": p}
        try:
            r = requests.post(self.url, json=payload, timeout=5)
            result = r.json()
            if "error" in result:
                err = result["error"]
                msg = f"aria2 error: {err.get('message', err)}"
                print(f"⚠ [{method}]: {msg}")
                if self.on_error:
                    self.on_error(msg)
                return None
            return result.get("result")
        except requests.exceptions.ConnectionError:
            msg = "aria2 disconnected"
            if self.on_error:
                self.on_error(msg)
            return None
        except requests.exceptions.Timeout:
            msg = f"aria2 timeout [{method}]"
            print(f"⚠ {msg}")
            if self.on_error:
                self.on_error(msg)
            return None
        except Exception as e:
            msg = f"aria2 error: {e}"
            print(f"⚠ [{method}]: {msg}")
            if self.on_error:
                self.on_error(msg)
            return None

    def add_url(self, url, options=None):
        if options is None:
            options = {}
        return self._call("aria2.addUri", [[url], options])

    def pause(self, gid):
        return self._call("aria2.pause", [gid])

    def resume(self, gid):
        return self._call("aria2.unpause", [gid])

    def remove(self, gid):
        self._call("aria2.remove", [gid])
        self._call("aria2.removeDownloadResult", [gid])

    def change_global_option(self, options):
        return self._call("aria2.changeGlobalOption", [options])

    def get_global_stat(self):
        return self._call("aria2.getGlobalStat")

    def tell_status(self, gid, keys=None):
        if keys is None:
            keys = ["gid", "status", "totalLength", "completedLength",
                    "downloadSpeed", "connections", "files", "errorMessage"]
        return self._call("aria2.tellStatus", [gid, keys])

    def tell_active(self):
        return self._call("aria2.tellActive") or []

    def tell_waiting(self, offset=0, num=1000):
        return self._call("aria2.tellWaiting", [offset, num]) or []

    def tell_stopped(self, offset=0, num=1000):
        return self._call("aria2.tellStopped", [offset, num]) or []

    def is_connected(self):
        """Check if aria2 is running and responding"""
        try:
            result = self._call("aria2.getGlobalStat")
            return result is not None
        except:
            return False
    
    def get_status(self, gid):
        result = self.tell_status(gid, ["gid", "status"])
        if result:
            return result.get("status")
        return None

    def force_pause(self, gid):
        return self._call("aria2.forcePause", [gid])

    def start_aria2(self):
        """Start aria2 daemon if not running"""
        if self.is_connected():
            print("✅ aria2 already running")
            return True
            
        print("Starting aria2 daemon...")
        
        # Kill existing aria2 processes first
        try:
            subprocess.run(["pkill", "-f", "aria2c"], capture_output=True)
            time.sleep(1)
        except:
            pass
        
        # Build command WITHOUT secret (use default config)
        aria2_cmd = [
            "aria2c",
            "--enable-rpc",
            "--rpc-listen-all",
            "--rpc-allow-origin-all",
            "--rpc-listen-port=6800",
            "--daemon",
            "--max-concurrent-downloads=5",
            "--max-connection-per-server=16",
            "--split=16",
            "--continue=true",
            "--always-resume=true",
        ]
        
        # Add secret only if set
        if self.secret:
            aria2_cmd.append(f"--rpc-secret={self.secret}")
        
        try:
            subprocess.Popen(
                aria2_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            time.sleep(2)
            
            # Try to connect
            for i in range(10):
                if self.is_connected():
                    print("✅ aria2 started successfully")
                    return True
                time.sleep(1)
                
            print("⚠️ aria2 failed to start after 10 seconds")
            return False
        except FileNotFoundError:
            print("❌ aria2 command not found. Please install aria2.")
            return False
        except Exception as e:
            print(f"Error starting aria2: {e}")
            return False
        
    def set_global_proxy(self, proxy_config):
        """تنظیم پروکسی سراسری در aria2"""
        if not proxy_config or not proxy_config.enabled:
            return self.change_global_option({"all-proxy": ""})
        
        if not proxy_config.is_valid():
            return False
        
        proxy_url = proxy_config._build_proxy_url()
        return self.change_global_option({"all-proxy": proxy_url})
    
    def set_download_speed_limit(self, gid, speed_limit_kb):
        """
        Set speed limit for a specific download in KB/s
        speed_limit_kb: 0 = no limit
        """
        if speed_limit_kb > 0:
            return self._call("aria2.changeOption", [gid, {"max-download-limit": f"{speed_limit_kb}K"}])
        else:
            return self._call("aria2.changeOption", [gid, {"max-download-limit": "0"}])