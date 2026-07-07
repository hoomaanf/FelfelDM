# core/file_size_fetcher.py

import re
import time
import requests
from typing import Optional, Dict, Tuple
from urllib.parse import urlparse, unquote


class FileSizeFetcher:
    
    DEFAULT_TIMEOUT = 10
    DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    
    def __init__(
        self,
        timeout: int = DEFAULT_TIMEOUT,
        user_agent: Optional[str] = None,
        proxy: Optional[Dict[str, str]] = None,
        verify_ssl: bool = True,
    ):
        self.timeout = timeout
        self.user_agent = user_agent or self.DEFAULT_USER_AGENT
        self.proxy = proxy
        self.verify_ssl = verify_ssl
        self._session = None
    
    @property
    def session(self) -> requests.Session:
        if self._session is None:
            self._session = requests.Session()
            self._session.headers.update({
                "User-Agent": self.user_agent,
                "Accept": "*/*",
                "Accept-Encoding": "gzip, deflate, br",
                "Accept-Language": "en-US,en;q=0.9",
                "Connection": "keep-alive",
            })
            if self.proxy:
                self._session.proxies.update(self.proxy)
            self._session.verify = self.verify_ssl
        return self._session
    
    def get_size(self, url: str) -> Optional[int]:
        size = self._head_method(url)
        if size is not None:
            return size
        
        size = self._range_method(url)
        if size is not None:
            return size
        
        size = self._stream_method(url)
        if size is not None:
            return size
        
        if self._is_youtube_url(url):
            size = self._youtube_method(url)
            if size is not None:
                return size
        
        return None
    
    def _head_method(self, url: str) -> Optional[int]:
        try:
            response = self.session.head(
                url,
                timeout=self.timeout,
                allow_redirects=True,
            )
            
            if response.status_code == 200:
                content_length = response.headers.get("content-length")
                if content_length and content_length.isdigit():
                    return int(content_length)
                    
        except Exception as e:
            pass
        
        return None
    
    def _range_method(self, url: str) -> Optional[int]:
        try:
            response = self.session.get(
                url,
                timeout=self.timeout,
                allow_redirects=True,
                headers={"Range": "bytes=0-0"},
                stream=True,
            )
            
            if response.status_code in (200, 206):
                content_range = response.headers.get("content-range", "")
                if content_range:
                    match = re.search(r"/(\d+)$", content_range)
                    if match:
                        return int(match.group(1))
                
                content_length = response.headers.get("content-length")
                if content_length and content_length.isdigit():
                    return int(content_length)
                    
        except Exception as e:
            pass
        
        return None
    
    def _stream_method(self, url: str) -> Optional[int]:
        try:
            response = self.session.get(
                url,
                timeout=self.timeout,
                allow_redirects=True,
                stream=True,
            )
            
            if response.status_code == 200:
                content_length = response.headers.get("content-length")
                if content_length and content_length.isdigit():
                    return int(content_length)
                
                transfer_encoding = response.headers.get("transfer-encoding")
                if transfer_encoding == "chunked":
                    try:
                        chunk = response.raw.read(64)
                        if chunk:
                            hex_str = chunk.split(b"\r\n")[0]
                            if hex_str:
                                chunk_size = int(hex_str, 16)
                                if chunk_size > 0:
                                    return chunk_size
                    except:
                        pass
                    
        except Exception as e:
            pass
        
        return None
    
    def _youtube_method(self, url: str) -> Optional[int]:
        try:
            import subprocess
            import json
            
            cmd = [
                "yt-dlp",
                "--no-playlist",
                "--skip-download",
                "--print-json",
                "--quiet",
                "--no-warnings",
                url,
            ]
            
            if self.proxy:
                proxy_url = self.proxy.get("http") or self.proxy.get("https")
                if proxy_url:
                    cmd.extend(["--proxy", proxy_url])
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
            
            if result.returncode == 0 and result.stdout:
                data = json.loads(result.stdout)
                filesize = data.get("filesize") or data.get("filesize_approx")
                if filesize:
                    return int(filesize)
                    
        except Exception as e:
            pass
        
        return None
    
    def _is_youtube_url(self, url: str) -> bool:
        youtube_patterns = [
            r"youtube\.com/watch",
            r"youtu\.be/",
            r"youtube\.com/shorts",
            r"youtube\.com/embed",
            r"m\.youtube\.com",
        ]
        for pattern in youtube_patterns:
            if re.search(pattern, url):
                return True
        return False
    
    def close(self):
        if self._session:
            self._session.close()
            self._session = None
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()



def get_file_size(url: str, timeout: int = 10, proxy: Optional[Dict[str, str]] = None) -> Optional[int]:
    fetcher = FileSizeFetcher(timeout=timeout, proxy=proxy)
    try:
        result = fetcher.get_size(url)
        return result
    finally:
        fetcher.close()