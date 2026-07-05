import re
from typing import Optional, Dict, Any
from enum import Enum

class ProxyType(Enum):
    HTTP = "http"
    HTTPS = "https"
    SOCKS4 = "socks4"
    SOCKS5 = "socks5"

class ProxyConfig:
    def __init__(self, 
                 proxy_type: ProxyType = ProxyType.HTTP,
                 host: str = "",
                 port: int = 8080,
                 username: Optional[str] = None,
                 password: Optional[str] = None,
                 enabled: bool = True,
                 name: str = "Default"):
        self.type = proxy_type
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.enabled = enabled
        self.name = name
    
    def __repr__(self):
        if not self.enabled:
            return "Proxy(disabled)"
        return f"Proxy({self.type.value}://{self.host}:{self.port})"
    
    def to_aria2_args(self) -> list:
        """تبدیل به پارامترهای aria2"""
        if not self.enabled or not self.host:
            return []
            
        proxy_url = self._build_proxy_url()
        if not proxy_url:
            return []
            
        return ["--all-proxy", proxy_url]
    
    def _build_proxy_url(self) -> str:
        """ساخت URL پروکسی برای aria2"""
        auth = ""
        if self.username and self.password:
            auth = f"{self.username}:{self.password}@"
            
        return f"{self.type.value}://{auth}{self.host}:{self.port}"
    
    def to_dict(self) -> dict:
        return {
            "type": self.type.value,
            "host": self.host,
            "port": self.port,
            "username": self.username,
            "password": self.password,
            "enabled": self.enabled,
            "name": self.name
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'ProxyConfig':
        return cls(
            proxy_type=ProxyType(data.get("type", "http")),
            host=data.get("host", ""),
            port=data.get("port", 8080),
            username=data.get("username"),
            password=data.get("password"),
            enabled=data.get("enabled", True),
            name=data.get("name", "Default")
        )
    
    def is_valid(self) -> bool:
        """بررسی معتبر بودن پروکسی"""
        if not self.host:
            return False
        if not 1 <= self.port <= 65535:
            return False
        ip_pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
        domain_pattern = r'^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$'
        if not (re.match(ip_pattern, self.host) or re.match(domain_pattern, self.host)):
            return False
        return True
    
    def get_display_string(self) -> str:
        """نمایش پروکسی به صورت رشته"""
        if not self.enabled:
            return "Disabled"
        if not self.host:
            return "Not Configured"
        auth = "🔒 " if self.username else ""
        return f"{auth}{self.type.value.upper()}://{self.host}:{self.port}"


class ProxyManager:
    def __init__(self, data_store):
        self.data_store = data_store
        self.global_proxy: Optional[ProxyConfig] = None
        self.queue_proxies: Dict[str, ProxyConfig] = {}  # queue_name -> ProxyConfig
        self._load_proxies()
    
    def _load_proxies(self):
        """Load proxy settings from data store"""
        try:
            proxy_data = self.data_store.settings.get("proxy_settings", {})
            
            if "global" in proxy_data and proxy_data["global"]:
                self.global_proxy = ProxyConfig.from_dict(proxy_data["global"])
            else:
                self.global_proxy = ProxyConfig(enabled=False)
            
            self.queue_proxies = {}
            for q in self.data_store.queues:
                if q.proxy_config and q.proxy_config.host:
                    self.queue_proxies[q.name] = q.proxy_config
                    
        except Exception as e:
            print(f"⚠️ Error loading proxy settings: {e}")
            self.global_proxy = ProxyConfig(enabled=False)
            self.queue_proxies = {}
    
    def save_proxies(self):
        """Save proxy settings"""
        try:
            queue_proxies = {}
            for q in self.data_store.queues:
                if q.proxy_config and q.proxy_config.host:
                    queue_proxies[q.name] = q.proxy_config.to_dict()
            
            data = {
                "global": self.global_proxy.to_dict() if self.global_proxy and self.global_proxy.host else None,
                "queues": queue_proxies
            }
            self.data_store.settings["proxy_settings"] = data
            self.data_store.save()
        except Exception as e:
            print(f"⚠️ Error saving proxy settings: {e}")
    
    def get_proxy_for_queue(self, queue_name: str) -> Optional[ProxyConfig]:
        if queue_name in self.queue_proxies:
            config = self.queue_proxies[queue_name]
            if config.enabled and config.is_valid():
                return config
        
        if self.global_proxy and self.global_proxy.enabled and self.global_proxy.is_valid():
            return self.global_proxy
            
        return None
    
    def get_aria2_proxy_args(self, queue_name: str = None) -> list:
        """دریافت آرگومان‌های پروکسی برای aria2"""
        if queue_name:
            proxy = self.get_proxy_for_queue(queue_name)
            if proxy:
                return proxy.to_aria2_args()
        return []
    
    def set_global_proxy(self, config: ProxyConfig):
        self.global_proxy = config
        self.save_proxies()
        self._apply_proxy_to_aria2()
    
    def set_queue_proxy(self, queue_name: str, config: Optional[ProxyConfig]):
        if config and config.host:
            self.queue_proxies[queue_name] = config
        elif queue_name in self.queue_proxies:
            del self.queue_proxies[queue_name]
        self.save_proxies()
        self._apply_proxy_to_aria2()
    
    def _apply_proxy_to_aria2(self):
        """اعمال پروکسی به aria2 از طریق RPC"""
        try:
            from core.aria2_rpc import Aria2RPC
            pass
        except:
            pass
    
    def get_queue_proxy(self, queue_name: str) -> Optional[ProxyConfig]:
        """دریافت پروکسی تنظیم شده برای صف (بدون fallback)"""
        return self.queue_proxies.get(queue_name)
    
    def remove_queue_proxy(self, queue_name: str):
        """حذف پروکسی مخصوص صف"""
        if queue_name in self.queue_proxies:
            del self.queue_proxies[queue_name]
            self.save_proxies()
            
    def get_proxy_for_download(self, download_id: str) -> Optional[ProxyConfig]:
        """دریافت پروکسی مخصوص یک دانلود خاص"""
        if hasattr(self.data_store, 'download_proxies'):
            download_proxies = self.data_store.download_proxies
            if download_id in download_proxies:
                config_data = download_proxies[download_id]
                if config_data and config_data.get("enabled", False):
                    return ProxyConfig.from_dict(config_data)
        return None
    
    def set_download_proxy(self, download_id: str, config: Optional[ProxyConfig]):
        """تنظیم پروکسی برای یک دانلود خاص"""
        if not hasattr(self.data_store, 'download_proxies'):
            self.data_store.download_proxies = {}
        
        if config and config.enabled and config.is_valid():
            self.data_store.download_proxies[download_id] = config.to_dict()
        elif download_id in self.data_store.download_proxies:
            del self.data_store.download_proxies[download_id]
        
        self.data_store.save()