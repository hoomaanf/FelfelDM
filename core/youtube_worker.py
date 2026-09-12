# core/youtube_worker.py

import os
import subprocess
import json
import re
import signal
import time
import glob
import shutil
import sys
from PyQt6.QtCore import QThread, pyqtSignal


class YouTubeWorker(QThread):
    progress = pyqtSignal(int)
    status = pyqtSignal(str)
    speed_eta = pyqtSignal(str, str)
    finished = pyqtSignal(bool, str)
    info_fetched = pyqtSignal(dict)
    paused = pyqtSignal()
    resumed = pyqtSignal()
    size_fetched = pyqtSignal(int)

    def __init__(
        self,
        url,
        output_path,
        format_type="mp4",
        cookie_file=None,
        proxy_url=None,
        format_id=None,
        quality="best",
        format_spec=None,
    ):
        super().__init__()
        self.url = url
        self.output_path = output_path
        self.format_type = format_type
        self.cookie_file = cookie_file
        self.proxy_url = proxy_url
        self.is_fetching_info = False
        self.is_fetching_size = False
        self.process = None
        self.is_paused = False
        self.is_cancelled = False
        self.current_file = None
        self._is_running = False
        self._last_progress = 0
        self._file_size = 0
        self.format_id = format_id
        self.quality = quality
        self.format_spec = format_spec

    def _find_system_ytdlp(self) -> str:

        preferred_paths = [
            os.path.expanduser("~/.local/bin/yt-dlp"),
            "/usr/local/bin/yt-dlp",
            "/usr/bin/yt-dlp",
            "/bin/yt-dlp",
            "/snap/bin/yt-dlp",
            os.path.expanduser("~/bin/yt-dlp"),
        ]

        venv_bin = os.path.join(sys.prefix, "bin")

        def is_venv_path(path: str) -> bool:
            if not path:
                return False
            try:
                real = os.path.realpath(path)
                venv_real = os.path.realpath(venv_bin)
                return real.startswith(venv_real)
            except Exception:
                return False

        for path in preferred_paths:
            if os.path.isfile(path) and os.access(path, os.X_OK):
                if not is_venv_path(path):
                    print(f"✅ Found system yt-dlp: {path}")
                    return path

        which_result = shutil.which("yt-dlp")
        if which_result and not is_venv_path(which_result):
            print(f"✅ Found yt-dlp in PATH: {which_result}")
            return which_result

        if which_result:
            print(f"⚠️ Only venv yt-dlp found: {which_result}")
            return which_result

        print("⚠️ yt-dlp not found, falling back to 'yt-dlp'")
        return "yt-dlp"

    def run(self):
        self._is_running = True
        if self.is_fetching_info:
            self._fetch_info()
        elif self.is_fetching_size:
            self._fetch_size()
        else:
            self._download()
        self._is_running = False

    def is_running(self):
        return self._is_running or self.isRunning()

    def fetch_size(self):
        if self.is_fetching_size:
            return
        self.is_fetching_size = True
        self.start()

    def _fetch_size(self):
        try:
            self.status.emit("Getting file size...")

            ytdlp_path = self._find_system_ytdlp()
            if not ytdlp_path:
                print("❌ yt-dlp not found")
                self.size_fetched.emit(0)
                return

            format_spec = getattr(self, "format_spec", None)
            format_id = getattr(self, "format_id", None)

            cmd = [
                ytdlp_path,
                "--skip-download",
                "--dump-json",
                "--no-warnings",
            ]

            if format_spec and format_spec not in ("bv+ba/b", "ba/b"):
                cmd.extend(["-f", format_spec])
            elif format_spec == "ba/b":
                cmd.extend(["-f", "ba"])
            elif format_spec:
                cmd.extend(["-f", format_spec])

            cmd.append(self.url)

            if self.proxy_url:
                cmd.extend(["--proxy", self.proxy_url])
                print(f"🌐 Using proxy for size fetch: {self.proxy_url}")

            if self.cookie_file and os.path.exists(self.cookie_file):
                cmd.extend(["--cookies", self.cookie_file])
                print(f"🍪 Using cookies for size fetch: {self.cookie_file}")

            print(f"📏 Fetching size with: {' '.join(cmd)}")

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode != 0:
                error_msg = result.stderr.strip()
                print(f"❌ Size fetch failed with code {result.returncode}")
                print(f"❌ stderr: {error_msg}")
                self.size_fetched.emit(0)
                return

            try:
                info = json.loads(result.stdout)
            except json.JSONDecodeError as e:
                print(f"❌ Failed to parse JSON: {e}")
                print(f"📄 Output: {result.stdout[:200]}...")
                self.size_fetched.emit(0)
                return

            filesize = info.get("filesize")
            if not filesize:
                filesize = info.get("filesize_approx", 0)

            if format_id and format_id not in ("best", "bestaudio"):
                requested = info.get("requested_formats", [])
                if requested:
                    total = 0
                    for fmt in requested:
                        fsize = fmt.get("filesize") or fmt.get("filesize_approx", 0)
                        if fsize:
                            total += int(fsize)
                    if total > 0:
                        filesize = total
                        print(f"📏 [SIZE] Using requested_formats size: {total}")

            if not filesize and format_id and format_id not in ("best", "bestaudio"):
                formats = info.get("formats", [])
                for fmt in formats:
                    if str(fmt.get("format_id")) == str(format_id):
                        fsize = fmt.get("filesize") or fmt.get("filesize_approx", 0)
                        if fsize:
                            filesize = int(fsize)
                            print(
                                f"📏 [SIZE] Found format {format_id} size: {filesize}"
                            )
                            break

            if filesize and int(filesize) > 0:
                self._file_size = int(filesize)
                print(
                    f"📏 File size: {self._file_size} bytes "
                    f"({self._file_size/1024/1024:.2f} MB)"
                )
                self.size_fetched.emit(self._file_size)
            else:
                formats = info.get("formats", [])
                max_size = 0
                for f in formats:
                    fsize = f.get("filesize") or f.get("filesize_approx", 0)
                    if fsize and int(fsize) > max_size:
                        max_size = int(fsize)

                if max_size > 0:
                    self._file_size = max_size
                    print(f"📏 File size from formats: {self._file_size} bytes")
                    self.size_fetched.emit(self._file_size)
                else:
                    print(f"⚠️ Could not determine file size for {self.url}")
                    self.size_fetched.emit(1)

        except subprocess.TimeoutExpired:
            print("❌ Timeout while fetching size")
            self.size_fetched.emit(0)
        except FileNotFoundError as e:
            print(f"❌ yt-dlp not found: {e}")
            self.size_fetched.emit(0)
        except Exception as e:
            print(f"❌ Size fetch error: {e}")
            import traceback
            traceback.print_exc()
            self.size_fetched.emit(0)
        finally:
            self.is_fetching_size = False
            self._is_running = False

    def pause(self):
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
        if not self._is_running:
            return
        self.is_cancelled = True
        if self.process:
            try:
                self.process.terminate()
                time.sleep(0.3)
                if self.process.poll() is None:
                    self.process.kill()
            except:
                pass
        self._delete_partial_files()
        self.wait()
        self.finished.emit(False, "Download cancelled by user")

    def _delete_partial_files(self):
        try:
            pattern = os.path.join(self.output_path, "*.part")
            for f in glob.glob(pattern):
                try:
                    os.remove(f)
                    print(f"🗑️ Deleted: {f}")
                except:
                    pass

            pattern = os.path.join(self.output_path, "*.ytdl")
            for f in glob.glob(pattern):
                try:
                    os.remove(f)
                    print(f"🗑️ Deleted: {f}")
                except:
                    pass

            pattern = os.path.join(self.output_path, "*.f*")
            for f in glob.glob(pattern):
                try:
                    if os.path.getsize(f) < 1024 * 1024:
                        os.remove(f)
                        print(f"🗑️ Deleted: {f}")
                except:
                    pass
        except Exception as e:
            print(f"Error deleting partial files: {e}")

    def _fetch_info(self):
        try:
            self.status.emit("Getting video info...")

            ytdlp_path = self._find_system_ytdlp()
            cmd = [
                ytdlp_path,
                "--skip-download",
                "--dump-json",
                "--no-warnings",
                self.url,
            ]

            if self.proxy_url:
                cmd.extend(["--proxy", self.proxy_url])
                print(f"🌐 Using proxy for info fetch: {self.proxy_url}")

            if self.cookie_file and os.path.exists(self.cookie_file):
                cmd.extend(["--cookies", self.cookie_file])

            print(f"🔍 Running: {' '.join(cmd)}")

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode != 0:
                error_msg = result.stderr.strip()
                print(f"❌ Info fetch failed: {error_msg}")
                self.finished.emit(False, f"Failed to fetch info: {error_msg}")
                return

            info = json.loads(result.stdout)
            self.progress.emit(100)
            self.info_fetched.emit(info)
            self.finished.emit(True, "Info fetched successfully!")

        except subprocess.TimeoutExpired:
            self.finished.emit(False, "Timeout while fetching video info")
        except json.JSONDecodeError as e:
            self.finished.emit(False, f"Failed to parse video info: {str(e)}")
        except FileNotFoundError:
            self.finished.emit(
                False, "yt-dlp not found. Please install: pip install yt-dlp"
            )
        except Exception as e:
            self.finished.emit(False, f"Error: {str(e)}")
        finally:
            self._is_running = False

    def _download(self):
        """Download YouTube video/audio"""
        try:
            self.status.emit("Preparing download...")
            self.progress.emit(0)

            ytdlp_path = self._find_system_ytdlp()
            print(f"🎯 yt-dlp resolved to: {ytdlp_path}")

            cmd = [
                ytdlp_path,
                "-o",
                os.path.join(self.output_path, "%(title)s.%(ext)s"),
                "--no-playlist",
                "--progress",
                "--newline",
                "--continue",
                "--no-warnings",
                "--socket-timeout",
                "60",
                "--no-check-certificate",
            ]

            if self.proxy_url:
                cmd.extend(["--proxy", self.proxy_url])
                print(f"🌐 Using proxy: {self.proxy_url}")
            else:
                print("ℹ️ No proxy configured")

            if self.cookie_file and os.path.exists(self.cookie_file):
                cmd.extend(["--cookies", self.cookie_file])
                print(f"🍪 Using cookies: {self.cookie_file}")

            format_spec = getattr(self, "format_spec", None)

            if self.format_type == "mp3":
                cmd.extend(["-x", "--audio-format", "mp3", "--audio-quality", "0"])
            elif format_spec:
                cmd.extend(["-f", format_spec])
            elif self.format_type in ("audio", "m4a"):
                cmd.extend(["-f", "ba/b"])
            else:
                cmd.extend(["-f", "bv+ba/b"])

            cmd.append(self.url)
            print(f"📥 Full command: {' '.join(cmd)}")
            self.status.emit("⬇ Downloading...")

            env = os.environ.copy()

            extra_paths = [
                os.path.expanduser("~/.local/bin"),
                "/usr/local/bin",
                "/usr/bin",
                "/bin",
                "/usr/local/sbin",
                "/usr/sbin",
                "/sbin",
                os.path.expanduser("~/.cargo/bin"),
            ]
            current_path = env.get("PATH", "")
            existing = set(current_path.split(":")) if current_path else set()
            for p in extra_paths:
                if p and p not in existing and os.path.exists(p):
                    current_path = f"{p}:{current_path}" if current_path else p
                    existing.add(p)
            env["PATH"] = current_path
            env["PYTHONUNBUFFERED"] = "1"

            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env,
            )

            error_lines = []

            for line in self.process.stdout:
                if self.is_cancelled:
                    break
                if self.is_paused:
                    continue

                error_lines.append(line.rstrip())

                if "[download]" in line:
                    percent_match = re.search(r"(\d+\.?\d*)%", line)
                    if percent_match:
                        percent = float(percent_match.group(1))
                        if percent > 0 and percent != self._last_progress:
                            self._last_progress = percent
                            self.progress.emit(int(percent))

                    speed_match = re.search(r"([\d.]+\s*[KM]?i?B/s)", line)
                    eta_match = re.search(r"ETA\s+([\d:]+|\w+)", line)
                    speed = speed_match.group(1) if speed_match else ""
                    eta = eta_match.group(1) if eta_match else ""
                    if speed and eta:
                        self.speed_eta.emit(speed, eta)

            self.process.wait()

            if self.is_cancelled:
                return

            if self.process.returncode == 0:
                self.progress.emit(100)
                self.status.emit("✅ Download completed!")
                self.speed_eta.emit("", "")
                self.finished.emit(True, "Download completed successfully!")
            else:
                print(f"❌❌❌ yt-dlp FAILED (code {self.process.returncode})")
                print(f"❌❌❌ CWD: {os.getcwd()}")
                print(f"❌❌❌ PATH: {env.get('PATH', 'NOT SET')[:300]}")
                print("❌❌❌ Last 30 lines of output:")
                for ln in error_lines[-30:]:
                    print(f"❌   {ln}")

                error_text = (
                    "\n".join(error_lines[-30:]) if error_lines else "Unknown error"
                )
                self.finished.emit(
                    False,
                    f"Download failed! (code {self.process.returncode})\n\n"
                    f"{error_text[-800:]}",
                )

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
            import urllib.parse

            parsed = urllib.parse.urlparse(self.proxy_url)
            os.environ["HTTP_PROXY"] = self.proxy_url
            os.environ["HTTPS_PROXY"] = self.proxy_url
            os.environ["http_proxy"] = self.proxy_url
            os.environ["https_proxy"] = self.proxy_url
            print(f"🌐 Environment proxy set: {self.proxy_url}")
            if parsed.username:
                os.environ["NO_PROXY"] = "localhost,127.0.0.1"
                os.environ["no_proxy"] = "localhost,127.0.0.1"
        except Exception as e:
            print(f"⚠️ Error setting proxy env: {e}")

    def get_proxy_status(self) -> str:
        if self.proxy_url:
            return f"🌐 Proxy: {self.proxy_url}"
        return "🌐 No proxy"

    def get_command(self) -> str:
        ytdlp_path = self._find_system_ytdlp()
        cmd = [
            ytdlp_path,
            "-o",
            os.path.join(self.output_path, "%(title)s.%(ext)s"),
            "--no-playlist",
            "--progress",
            "--newline",
            "--continue",
            self.url,
        ]
        if self.proxy_url:
            cmd.extend(["--proxy", self.proxy_url])
        if self.cookie_file and os.path.exists(self.cookie_file):
            cmd.extend(["--cookies", self.cookie_file])
        return " ".join(cmd)

    def test_proxy(self) -> tuple:
        if not self.proxy_url:
            return False, "No proxy configured"
        try:
            import urllib.request
            import urllib.error
            import urllib.parse as _up

            parsed = _up.urlparse(self.proxy_url)
            proxy_handler = urllib.request.ProxyHandler(
                {"http": self.proxy_url, "https": self.proxy_url}
            )
            opener = urllib.request.build_opener(proxy_handler)
            urllib.request.install_opener(opener)
            response = urllib.request.urlopen("https://www.google.com", timeout=10)
            if response.status == 200:
                return True, "Proxy is working"
            else:
                return False, f"Proxy returned status: {response.status}"
        except urllib.error.URLError as e:
            return False, f"Proxy error: {str(e)}"
        except Exception as e:
            return False, f"Error: {str(e)}"
