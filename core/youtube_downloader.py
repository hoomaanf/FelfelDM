# core/youtube_downloader.py
import os
import subprocess
import json
from typing import Optional, Dict, List, Tuple


class YouTubeDownloader:

    def __init__(self, cookie_file: Optional[str] = None):
        self.cookie_file = cookie_file
        self.ytdlp_path = self._find_ytdlp()

    def _find_ytdlp(self) -> str:
        import shutil

        path = shutil.which("yt-dlp")
        if path:
            print(f"✅ Found yt-dlp at: {path}")
            return path

        raise FileNotFoundError(
            "❌ yt-dlp not found in system!\n"
            "Please install it using your package manager:\n"
            "  Arch:   sudo pacman -S yt-dlp\n"
            "  Ubuntu: sudo apt install yt-dlp\n"
            "  Fedora: sudo dnf install yt-dlp"
        )

    def get_video_info(self, url: str) -> Dict:
        cmd = [self.ytdlp_path, "--skip-download", "--dump-json", url]
        if self.cookie_file and os.path.exists(self.cookie_file):
            cmd.extend(["--cookies", self.cookie_file])

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return json.loads(result.stdout)
        except subprocess.CalledProcessError as e:
            raise Exception(f"Failed to get video info: {e.stderr}")

    def download(
        self, url: str, output_path: str, format_type: str = "mp4", gid: str = None
    ) -> Tuple[bool, str, str]:
        cmd = [
            self.ytdlp_path,
            "-o",
            os.path.join(output_path, "%(title)s.%(ext)s"),
            "--no-playlist",
            "--restrict-filenames",
            url,
        ]

        if format_type == "mp3":
            cmd.extend(["-x", "--audio-format", "mp3"])
        elif format_type == "mp4":
            cmd.extend(
                ["-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"]
            )
        elif format_type == "webm":
            cmd.extend(
                ["-f", "bestvideo[ext=webm]+bestaudio[ext=webm]/best[ext=webm]/best"]
            )
        else:
            cmd.extend(["-f", "best"])

        if self.cookie_file and os.path.exists(self.cookie_file):
            cmd.extend(["--cookies", self.cookie_file])

        try:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)

            downloaded_file = self._find_downloaded_file(output_path, url)

            return True, "Download completed successfully!", downloaded_file

        except subprocess.CalledProcessError as e:
            return False, f"Download failed: {e.stderr}", None

    def _find_downloaded_file(self, output_path: str, url: str) -> str:
        try:
            files = os.listdir(output_path)
            for file in files:
                full_path = os.path.join(output_path, file)
                if os.path.isfile(full_path) and file.lower().endswith(
                    (".mp4", ".mkv", ".webm", ".mp3", ".m4a", ".opus")
                ):
                    return full_path
            return ""
        except:
            return ""
