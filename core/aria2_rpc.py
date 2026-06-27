import requests

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
            r = requests.post(self.url, json=payload, timeout=1.5)
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
        return self._call("aria2.addUri", [[url], options or {}])

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
        return self.get_global_stat() is not None
    
    def get_status(self, gid):
        result = self.tell_status(gid, ["gid", "status"])
        if result:
            return result.get("status")
        return None
    def force_pause(self, gid):
        return self._call("aria2.forcePause", [gid])
