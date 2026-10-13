# core/youtube_worker.py

import os
import subprocess
import json
import re
import signal
import time
import uuid
import shutil
import sys
import tempfile
from typing import Optional, Set
from pathlib import Path
from PyQt6.QtCore import QThread, pyqtSignal


def _is_safe_path(path: Path, output_dir: Path) -> bool:
    """Reject anything that escapes output_dir via "..", symlinks, or
    is a directory."""
    try:
        real_output = output_dir.resolve()
        real_path = path.resolve()
    except (OSError, RuntimeError):
        return False
    # Must live directly inside output_dir (no subdirs, no ".." escape).
    if real_path.parent != real_output:
        return False
    if real_path == real_output:
        return False
    return True


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
        title=None,
        download_id=None,
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

        # ── C28 fix: track files yt-dlp reported as produced ──
        self._produced_paths: Set[Path] = set()

        # ── Dedicated temp dir (only for THIS download) ──
        # yt-dlp writes .part/.fXXX/.ytdl intermediates here. On
        # cancel we rmtree() the whole dir — safe because it's ours
        # alone and never contains user files.
        self.download_id = download_id or uuid.uuid4().hex
        self._temp_dir: Optional[Path] = None

        # Optional title (kept for callers; not used for deletion).
        self._title: Optional[str] = title or None

    # ─────────────────────────────────────────────────────────────
    #  yt-dlp discovery
    # ─────────────────────────────────────────────────────────────
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

    # ─────────────────────────────────────────────────────────────
    #  Size fetch
    # ─────────────────────────────────────────────────────────────
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

            result = subprocess.run(cmd, capture_output=True, text=True)

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

    # ─────────────────────────────────────────────────────────────
    #  Pause / Resume
    # ─────────────────────────────────────────────────────────────
    def pause(self):
        if self.process and not self.is_paused and self._is_running:
            self.is_paused = True
            try:
                pgid = os.getpgid(self.process.pid)
                os.killpg(pgid, signal.SIGSTOP)
                self.paused.emit()
                self.status.emit("⏸ Paused")
                print("⏸️ YouTube download paused")
            except Exception as e:
                print(f"Pause error: {e}")

    def resume(self):
        if self.process and self.is_paused and self._is_running:
            self.is_paused = False
            try:
                pgid = os.getpgid(self.process.pid)
                os.killpg(pgid, signal.SIGCONT)
                self.resumed.emit()
                self.status.emit("▶ Resuming...")
                print("▶️ YouTube download resumed")
            except Exception as e:
                print(f"Resume error: {e}")

    # ─────────────────────────────────────────────────────────────
    #  Cancel — kill process, rmtree temp dir, sweep reported files
    # ─────────────────────────────────────────────────────────────
    def cancel(self):
        """Cancel the download.

        - Kill the yt-dlp process group (SIGTERM then SIGKILL).
        - Remove the dedicated temp directory (rmtree). Safe because
          the dir is exclusively ours.
        - Sweep any files yt-dlp already reported via --print-to-file
          that may have landed in the user's output_path.
        """
        if not self._is_running:
            return
        self.is_cancelled = True

        if self.process:
            try:
                pgid = os.getpgid(self.process.pid)
                try:
                    os.killpg(pgid, signal.SIGCONT)
                except Exception:
                    pass

                os.killpg(pgid, signal.SIGTERM)

                deadline = time.time() + 2.0
                while time.time() < deadline:
                    if self.process.poll() is not None:
                        break
                    time.sleep(0.05)

                if self.process.poll() is None:
                    os.killpg(pgid, signal.SIGKILL)

            except ProcessLookupError:
                pass
            except Exception:
                try:
                    self.process.terminate()
                    time.sleep(0.3)
                    if self.process.poll() is None:
                        self.process.kill()
                except Exception:
                    pass

        # Give the kernel a moment to release file handles.
        time.sleep(0.3)

        # 1. rmtree the dedicated temp dir (safe, ours alone).
        self._cleanup_temp_dir()

        # 2. Sweep any files yt-dlp reported into output_path.
        try:
            self._delete_partial_files()
        except Exception as e:
            print(f"⚠️ [YouTubeWorker] Safe cleanup failed: {e}")

        self.speed_eta.emit("", "")

        if not self.wait(3000):
            print(
                "⚠️ [YouTubeWorker] cancel: thread didn't exit in 3s, "
                "terminating anyway"
            )
            self.terminate()
            self.wait(1000)

        self.finished.emit(False, "Download cancelled by user")

    # ─────────────────────────────────────────────────────────────
    #  Temp dir cleanup
    # ─────────────────────────────────────────────────────────────
    def _cleanup_temp_dir(self):
        """Remove the dedicated temp directory for this download.

        Safe: the dir is named felfeldm-dl-<uuid> and only contains
        files yt-dlp created for this specific download.
        """
        if not self._temp_dir:
            return
        try:
            if self._temp_dir.exists():
                shutil.rmtree(self._temp_dir, ignore_errors=True)
                print(f"🗑️ [YouTubeWorker] Removed temp dir: {self._temp_dir}")
        except Exception as e:
            print(f"⚠️ [YouTubeWorker] Could not remove temp dir: {e}")
        finally:
            self._temp_dir = None

    # ─────────────────────────────────────────────────────────────
    #  Delete only files yt-dlp explicitly reported
    # ─────────────────────────────────────────────────────────────
    def _delete_partial_files(self):
        """Delete ONLY files that yt-dlp itself reported as produced.

        Design principle: never guess. If we're not 100% sure a file
        was created by THIS download, we leave it alone.

        The list comes from --print-to-file with before_dl:filename,
        after_dl:filepath and after_move:filepath. Only files under
        output_path are considered here; files under _temp_dir are
        removed wholesale by _cleanup_temp_dir().
        """
        output_dir = Path(self.output_path).resolve()
        if not output_dir.is_dir():
            print(f"⚠️ [YouTubeWorker] Output dir missing: {output_dir}")
            return

        if not self._produced_paths:
            print(
                "ℹ️ [YouTubeWorker] No produced paths recorded; "
                "nothing deleted (safe)"
            )
            return

        deleted = 0
        for path in list(self._produced_paths):
            try:
                if not path.exists():
                    continue
                if not _is_safe_path(path, output_dir):
                    print(
                        f"⚠️ [YouTubeWorker] Refusing to delete " f"outside dir: {path}"
                    )
                    continue
                if path.is_dir():
                    print(f"⚠️ [YouTubeWorker] Refusing to rmtree: {path}")
                    continue
                path.unlink()
                deleted += 1
                print(f"🗑️ Deleted (produced): {path.name}")
            except FileNotFoundError:
                pass
            except OSError as e:
                print(f"⚠️ Could not delete {path}: {e}")

        if deleted == 0:
            print("ℹ️ [YouTubeWorker] Nothing to delete (safe)")
        else:
            print(f"✅ [YouTubeWorker] Deleted {deleted} file(s)")

    # ─────────────────────────────────────────────────────────────
    #  Info fetch
    # ─────────────────────────────────────────────────────────────
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

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode != 0:
                error_msg = result.stderr.strip()
                print(f"❌ Info fetch failed: {error_msg}")
                self.finished.emit(False, f"Failed to fetch info: {error_msg}")
                return

            info = json.loads(result.stdout)
            self._title = info.get("title") or None
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

    # ─────────────────────────────────────────────────────────────
    #  Download (uses -P temp: and -P home:)
    # ─────────────────────────────────────────────────────────────
    def _download(self):
        """Download YouTube video/audio.

        Uses yt-dlp's -P (--paths):
          -P home:<output_path>  → final merged file goes here
          -P temp:<temp_dir>     → .part, .fXXX.mp4, .ytdl, etc. go here

        The temp_dir is dedicated to this download (named
        felfeldm-dl-<uuid>), so we can safely rmtree() it on cancel
        without touching any user file.
        """
        produced_list_path: Optional[Path] = None
        try:
            self.status.emit("Preparing download...")
            self.progress.emit(0)

            ytdlp_path = self._find_system_ytdlp()
            print(f"🎯 yt-dlp resolved to: {ytdlp_path}")

            # ── Dedicated temp dir ──
            self._temp_dir = (
                Path(tempfile.gettempdir()) / f"felfeldm-dl-{self.download_id}"
            )
            self._temp_dir.mkdir(parents=True, exist_ok=True)
            try:
                os.chmod(self._temp_dir, 0o700)
            except OSError:
                pass
            print(f"📂 [YouTubeWorker] temp dir: {self._temp_dir}")

            # ── --print-to-file log ──
            fd, produced_name = tempfile.mkstemp(
                prefix="felfeldm-ytdlp-paths-", suffix=".txt"
            )
            os.close(fd)
            produced_list_path = Path(produced_name)

            cmd = [
                ytdlp_path,
                "-P",
                f"home:{self.output_path}",
                "-P",
                f"temp:{self._temp_dir}",
                "-o",
                "%(title)s.%(ext)s",
                "--no-playlist",
                "--progress",
                "--newline",
                "--continue",
                "--no-warnings",
                "--socket-timeout",
                "60",
                "--no-check-certificate",
                "--print-to-file",
                "before_dl:filename",
                str(produced_list_path),
                "--print-to-file",
                "after_dl:filepath",
                str(produced_list_path),
                "--print-to-file",
                "after_move:filepath",
                str(produced_list_path),
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

            if self.format_type not in ("mp3", "audio", "m4a"):
                cmd.extend(["--merge-output-format", "mp4"])

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
                start_new_session=True,
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

            # Ingest produced paths BEFORE checking returncode, so a
            # partially-successful download still has its paths
            # registered for future cleanup.
            self._ingest_produced_paths(produced_list_path)

            # Clean up temp dir regardless of outcome — no reason to
            # leave an empty felfeldm-dl-<id> directory around.
            self._cleanup_temp_dir()

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
            if produced_list_path is not None:
                try:
                    produced_list_path.unlink()
                except OSError:
                    pass
            self._cleanup_temp_dir()
            self._is_running = False
            self.process = None

    # ─────────────────────────────────────────────────────────────
    #  Ingest --print-to-file output
    # ─────────────────────────────────────────────────────────────
    def _ingest_produced_paths(self, produced_list_path: Path) -> None:
        """Read the paths yt-dlp reported and store them for cleanup.

        With -P home: and -P temp:, yt-dlp reports final paths under
        output_path and intermediate paths under the temp dir. We
        keep both; the temp-dir entries are useful for logging, and
        they're also removed by _cleanup_temp_dir() anyway.
        """
        try:
            text = produced_list_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return

        output_dir = Path(self.output_path).resolve()
        temp_dir_resolved: Optional[Path] = None
        if self._temp_dir is not None:
            try:
                temp_dir_resolved = self._temp_dir.resolve()
            except (OSError, RuntimeError):
                temp_dir_resolved = None

        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                p = Path(line)
            except Exception:
                continue
            if not p.is_absolute():
                p = Path.cwd() / p
            try:
                resolved = p.resolve(strict=False)
            except (OSError, RuntimeError):
                continue

            # Accept files under output_path or the dedicated temp dir.
            if resolved.parent != output_dir:
                if not (temp_dir_resolved and resolved.parent == temp_dir_resolved):
                    continue
            if resolved == output_dir:
                continue
            if temp_dir_resolved and resolved == temp_dir_resolved:
                continue

            self._produced_paths.add(resolved)

        if self._produced_paths:
            print(
                f"📋 [YouTubeWorker] Recorded {len(self._produced_paths)} "
                f"produced path(s)"
            )
            for p in sorted(self._produced_paths):
                print(f"   • {p.name}")
