# core/youtube_worker.py

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
    
    def __init__(self, url, output_path, format_type="mp4", cookie_file=None):
        super().__init__()
        self.url = url
        self.output_path = output_path
        self.format_type = format_type
        self.cookie_file = cookie_file
        self.is_fetching_info = False
        self.process = None
        self.is_paused = False
        self.is_cancelled = False
        self.current_file = None
        self._is_running = False
        
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
                self.status.emit("Paused")
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
                self.status.emit("Resuming...")
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
                    if os.path.getsize(f) < 1024 * 1024:  # فقط فایل‌های کوچک (ناقص)
                        os.remove(f)
                        print(f"🗑️ Deleted: {f}")
                except:
                    pass
                    
        except Exception as e:
            print(f"Error deleting partial files: {e}")
    
    def _fetch_info(self):
        try:
            self.status.emit("Getting video info...")
            
            cmd = ["yt-dlp", "--skip-download", "--dump-json", self.url]
            if self.cookie_file and os.path.exists(self.cookie_file):
                cmd.extend(["--cookies", self.cookie_file])
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            info = json.loads(result.stdout)
            
            self.progress.emit(100)
            self.info_fetched.emit(info)
            self.finished.emit(True, "Info fetched successfully!")
            
        except subprocess.CalledProcessError as e:
            self.finished.emit(False, f"Failed to fetch info: {e.stderr}")
        except Exception as e:
            self.finished.emit(False, f"Error: {str(e)}")
        finally:
            self._is_running = False
    
    def _download(self):
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
                self.url
            ]
            
            if self.format_type == "mp3":
                cmd.extend(["-x", "--audio-format", "mp3"])
            elif self.format_type == "mp4":
                cmd.extend(["-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"])
            elif self.format_type == "webm":
                cmd.extend(["-f", "bestvideo[ext=webm]+bestaudio[ext=webm]/best[ext=webm]/best"])
            else:
                cmd.extend(["-f", "best"])
            
            if self.cookie_file and os.path.exists(self.cookie_file):
                cmd.extend(["--cookies", self.cookie_file])
            
            self.status.emit("Downloading...")
            
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            
            last_status = ""
            line_count = 0
            
            for line in self.process.stdout:
                if self.is_cancelled:
                    break
                
                # اگر Pause هستیم، خطوط رو نادیده بگیر
                if self.is_paused:
                    continue
                
                # استخراج درصد
                if "[download]" in line and "%" in line:
                    try:
                        percent_match = re.search(r'(\d+\.?\d*)%', line)
                        if percent_match:
                            percent = float(percent_match.group(1))
                            if percent > 0:
                                self.progress.emit(int(percent))
                    except:
                        pass
                
                # استخراج سرعت و ETA
                if "ETA" in line or "speed" in line:
                    speed_match = re.search(r'([\d.]+\s*[KM]?i?B/s)', line)
                    speed = speed_match.group(1) if speed_match else ""
                    
                    eta_match = re.search(r'ETA\s+([\d:]+|\w+)', line)
                    eta = eta_match.group(1) if eta_match else ""
                    
                    if speed and eta:
                        self.speed_eta.emit(speed, eta)
                
                # به‌روزرسانی وضعیت (فقط خطوطی که جدید هستن)
                clean_line = line.strip()
                if clean_line and "[download]" in clean_line and not self.is_paused:
                    # خطوط تکراری رو فیلتر کن
                    if clean_line != last_status:
                        self.status.emit(clean_line[:100])  # فقط ۱۰۰ کاراکتر اول
                        last_status = clean_line
                        line_count += 1
            
            self.process.wait()
            
            if self.is_cancelled:
                return
            
            if self.process.returncode == 0:
                self.progress.emit(100)
                self.status.emit("Download completed!")
                self.speed_eta.emit("", "")
                self.finished.emit(True, "Download completed successfully!")
            else:
                self.finished.emit(False, "Download failed!")
                
        except Exception as e:
            self.finished.emit(False, f"Error: {str(e)}")
        finally:
            self._is_running = False
            self.process = None