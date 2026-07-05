import os
import subprocess
import json
import re
import signal
import time
import glob
from PyQt6.QtCore import QThread, pyqtSignal

class YouTubeWorker(QThread):
    progress = pyqtSignal(int)
    status = pyqtSignal(str)
    speed_eta = pyqtSignal(str, str)
    finished = pyqtSignal(bool, str)
    info_fetched = pyqtSignal(dict)
    paused = pyqtSignal()
    resumed = pyqtSignal()
    
    def __init__(self, url, output_path, format_type="mp4", cookie_file=None, proxy_url=None):
        super().__init__()
        self.url = url
        self.output_path = output_path
        self.format_type = format_type
        self.cookie_file = cookie_file
        self.proxy_url = proxy_url  # Proxy URL for yt-dlp
        self.is_fetching_info = False
        self.process = None
        self.is_paused = False
        self.is_cancelled = False
        self.current_file = None
        self._is_running = False
        self._last_progress = 0
        
    def run(self):
        self._is_running = True
        if self.is_fetching_info:
            self._fetch_info()
        else:
            self._download()
        self._is_running = False
    
    def is_running(self):
        return self._is_running or self.isRunning()
    
    def pause(self):
        """Pause download"""
        if self.process and not self.is_paused and self._is_running:
            self.is_paused = True
            try:
                self.process.send_signal(signal.SIGSTOP)
                self.paused.emit()
                self.status.emit("⏸ Paused")
                print("⏸️ YouTube download paused")
            except Exception as e:
                print(f"Pause error: {e}")
    
    def resume(self):
        """Resume download"""
        if self.process and self.is_paused and self._is_running:
            self.is_paused = False
            try:
                self.process.send_signal(signal.SIGCONT)
                self.resumed.emit()
                self.status.emit("▶ Resuming...")
                print("▶️ YouTube download resumed")
            except Exception as e:
                print(f"Resume error: {e}")
    
    def cancel(self):
        """Cancel download and delete partial files"""
        if not self._is_running:
            return
            
        self.is_cancelled = True
        
        # Kill process
        if self.process:
            try:
                self.process.terminate()
                time.sleep(0.5)
                if self.process.poll() is None:
                    self.process.kill()
            except:
                pass
        
        # Delete partial files
        self._delete_partial_files()
        
        # Wait for thread to finish
        self.wait()
        self.finished.emit(False, "Download cancelled by user")
    
    def _delete_partial_files(self):
        """Delete partial downloaded files"""
        try:
            # Delete .part files
            pattern = os.path.join(self.output_path, "*.part")
            for f in glob.glob(pattern):
                try:
                    os.remove(f)
                    print(f"🗑️ Deleted: {f}")
                except:
                    pass
            
            # Delete .ytdl files
            pattern = os.path.join(self.output_path, "*.ytdl")
            for f in glob.glob(pattern):
                try:
                    os.remove(f)
                    print(f"🗑️ Deleted: {f}")
                except:
                    pass
            
            # Delete .f* files (yt-dlp fragment files)
            pattern = os.path.join(self.output_path, "*.f*")
            for f in glob.glob(pattern):
                try:
                    if os.path.getsize(f) < 1024 * 1024:  # Only delete small fragment files
                        os.remove(f)
                        print(f"🗑️ Deleted: {f}")
                except:
                    pass
                    
        except Exception as e:
            print(f"Error deleting partial files: {e}")
    
    def _fetch_info(self):
        """Fetch video information from YouTube"""
        try:
            self.status.emit("Getting video info...")
            
            cmd = [
                "yt-dlp",
                "--skip-download",
                "--dump-json",
                "--no-warnings",
                self.url
            ]
            
            # Add proxy if available
            if self.proxy_url:
                cmd.extend(["--proxy", self.proxy_url])
                print(f"🌐 Using proxy for info fetch: {self.proxy_url}")
            
            # Add cookies if available
            if self.cookie_file and os.path.exists(self.cookie_file):
                cmd.extend(["--cookies", self.cookie_file])
            
            print(f"🔍 Running: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                error_msg = result.stderr.strip()
                print(f"❌ Info fetch failed: {error_msg}")
                self.finished.emit(False, f"Failed to fetch info: {error_msg}")
                return
            
            # Parse JSON output
            info = json.loads(result.stdout)
            
            self.progress.emit(100)
            self.info_fetched.emit(info)
            self.finished.emit(True, "Info fetched successfully!")
            
        except subprocess.TimeoutExpired:
            self.finished.emit(False, "Timeout while fetching video info")
        except json.JSONDecodeError as e:
            self.finished.emit(False, f"Failed to parse video info: {str(e)}")
        except FileNotFoundError:
            self.finished.emit(False, "yt-dlp not found. Please install: pip install yt-dlp")
        except Exception as e:
            self.finished.emit(False, f"Error: {str(e)}")
        finally:
            self._is_running = False
    
    def _download(self):
        """Download YouTube video/audio"""
        try:
            self.status.emit("Preparing download...")
            self.progress.emit(0)
            
            cmd = [
                "yt-dlp",
                "-o", os.path.join(self.output_path, "%(title)s.%(ext)s"),
                "--no-playlist",
                "--progress",
                "--newline",
                "--continue",
                "--no-warnings",
                "--socket-timeout", "60",
                "--no-check-certificate",
            ]
            
            if self.proxy_url:
                proxy_for_cmd = self.proxy_url
                if proxy_for_cmd.startswith("http://"):
                    proxy_for_cmd = proxy_for_cmd.replace("http://", "socks5://")
                elif proxy_for_cmd.startswith("https://"):
                    proxy_for_cmd = proxy_for_cmd.replace("https://", "socks5://")
                
                cmd.extend(["--proxy", proxy_for_cmd])
                print(f"🌐 Using proxy: {proxy_for_cmd}")
            else:
                print("ℹ️ No proxy configured") 
            
            if self.cookie_file and os.path.exists(self.cookie_file):
                cmd.extend(["--cookies", self.cookie_file])
                print(f"🍪 Using cookies: {self.cookie_file}")
            
            if self.format_type == "mp3":
                cmd.extend(["-x", "--audio-format", "mp3", "--audio-quality", "0"])
            elif self.format_type == "mp4":
                cmd.extend(["-f", "bv+ba/b"])
            else:
                cmd.extend(["-f", "bv+ba/b"])
            
            cmd.append(self.url)
            
            print(f"📥 Full command: {' '.join(cmd)}")
            
            self.status.emit("⬇ Downloading...")
            
            env = os.environ.copy()
            if self.proxy_url:
                env['HTTP_PROXY'] = self.proxy_url
                env['HTTPS_PROXY'] = self.proxy_url
                env['ALL_PROXY'] = self.proxy_url
                env['http_proxy'] = self.proxy_url
                env['https_proxy'] = self.proxy_url
                env['all_proxy'] = self.proxy_url
            
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env
            )
            
            for line in self.process.stdout:
                if self.is_cancelled:
                    break
                if self.is_paused:
                    continue
                
                if "[download]" in line:
                    percent_match = re.search(r'(\d+\.?\d*)%', line)
                    if percent_match:
                        percent = float(percent_match.group(1))
                        if percent > 0 and percent != self._last_progress:
                            self._last_progress = percent
                            self.progress.emit(int(percent))
                    
                    speed_match = re.search(r'([\d.]+\s*[KM]?i?B/s)', line)
                    eta_match = re.search(r'ETA\s+([\d:]+|\w+)', line)
                    speed = speed_match.group(1) if speed_match else ""
                    eta = eta_match.group(1) if eta_match else ""
                    if speed and eta:
                        self.speed_eta.emit(speed, eta)
                
                clean_line = line.strip()
                if clean_line and "[download]" in clean_line and not self.is_paused:
                    if len(clean_line) > 100:
                        clean_line = clean_line[:100] + "..."
                    self.status.emit(clean_line)
            
            self.process.wait()
            
            if self.is_cancelled:
                return
            
            if self.process.returncode == 0:
                self.progress.emit(100)
                self.status.emit("✅ Download completed!")
                self.speed_eta.emit("", "")
                self.finished.emit(True, "Download completed successfully!")
            else:
                error = self.process.stderr.read() if self.process.stderr else "Unknown error"
                self.finished.emit(False, f"Download failed! (code {self.process.returncode})")
                
        except Exception as e:
            self.finished.emit(False, f"Error: {str(e)}")
        finally:
            self._is_running = False
            self.process = None
    
    def _set_proxy_env(self):
        """Set environment variables for proxy as fallback"""
        if not self.proxy_url:
            return
        
        try:
            # Parse proxy URL
            import urllib.parse
            parsed = urllib.parse.urlparse(self.proxy_url)
            
            # Set HTTP_PROXY and HTTPS_PROXY
            os.environ['HTTP_PROXY'] = self.proxy_url
            os.environ['HTTPS_PROXY'] = self.proxy_url
            
            # Also set lowercase versions (some tools use these)
            os.environ['http_proxy'] = self.proxy_url
            os.environ['https_proxy'] = self.proxy_url
            
            print(f"🌐 Environment proxy set: {self.proxy_url}")
            
            # If proxy has auth, set no_proxy for localhost
            if parsed.username:
                os.environ['NO_PROXY'] = 'localhost,127.0.0.1'
                os.environ['no_proxy'] = 'localhost,127.0.0.1'
                
        except Exception as e:
            print(f"⚠️ Error setting proxy env: {e}")
    
    def get_proxy_status(self) -> str:
        """Get proxy status string for display"""
        if self.proxy_url:
            return f"🌐 Proxy: {self.proxy_url}"
        return "🌐 No proxy"
    
    def get_command(self) -> str:
        """Get the full command for debugging"""
        cmd = [
            "yt-dlp",
            "-o", os.path.join(self.output_path, "%(title)s.%(ext)s"),
            "--no-playlist",
            "--progress",
            "--newline",
            "--continue",
            self.url
        ]
        
        if self.proxy_url:
            cmd.extend(["--proxy", self.proxy_url])
        
        if self.cookie_file and os.path.exists(self.cookie_file):
            cmd.extend(["--cookies", self.cookie_file])
        
        return " ".join(cmd)
    
    def test_proxy(self) -> tuple:
        """Test if proxy is working"""
        if not self.proxy_url:
            return False, "No proxy configured"
        
        try:
            import urllib.request
            import urllib.error
            
            # Parse proxy URL
            parsed = urllib.parse.urlparse(self.proxy_url)
            
            # Create proxy handler
            proxy_handler = urllib.request.ProxyHandler({
                'http': self.proxy_url,
                'https': self.proxy_url
            })
            
            opener = urllib.request.build_opener(proxy_handler)
            urllib.request.install_opener(opener)
            
            # Test with google.com
            response = urllib.request.urlopen('https://www.google.com', timeout=10)
            
            if response.status == 200:
                return True, "Proxy is working"
            else:
                return False, f"Proxy returned status: {response.status}"
                
        except urllib.error.URLError as e:
            return False, f"Proxy error: {str(e)}"
        except Exception as e:
            return False, f"Error: {str(e)}"