# 🌶️ FelfelDM

<div align="center">
  <img src="logo/icon512.png" alt="FelfelDM Logo" width="180">
  <h2>A Modern Download Manager for Linux</h2>

  <p>
    <img src="https://img.shields.io/badge/Python-3.10%2B-blue?style=for-the-badge&logo=python" alt="Python">
    <img src="https://img.shields.io/badge/PyQt6-6.11-blue?style=for-the-badge&logo=qt" alt="PyQt6">
    <img src="https://img.shields.io/badge/aria2-1.37-blue?style=for-the-badge&logo=aria2" alt="aria2">
    <img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License">
    <br>
    <img src="https://img.shields.io/badge/Platform-Linux-FCC624?style=for-the-badge&logo=linux" alt="Platform">
    <img src="https://img.shields.io/badge/Status-Active-success?style=for-the-badge" alt="Status">
    <br>
    <img src="https://img.shields.io/badge/Firefox-FF7139?style=for-the-badge&logo=firefox" alt="Firefox">
    <img src="https://img.shields.io/badge/Chrome-4285F4?style=for-the-badge&logo=google-chrome" alt="Chrome">
  </p>
</div>

---

## 📸 Screenshot

<div align="center">
  <img src="screenshots/main-window.png" alt="FelfelDM Main Window" width="800">
  <p><em>Main Interface - Dark Theme</em></p>
</div>

---

## ✨ Features

### Core Features

- 🚀 **Multiple Queues** — Create and manage multiple download queues
- ⏰ **Scheduled Downloads** — Set time windows for automatic downloads
- 📊 **Real-time Progress** — Live download speed and progress tracking
- 🎯 **Smart Management** — Auto-retry, pause/resume, and error handling
- 🗑️ **Safe Removal** — Remove from list or delete files permanently
- 🎵 **YouTube Download** — Download videos and audio from YouTube with dynamic quality selection

### Queue Management

- 📋 **Queue Status** — Real-time status display for each queue (Running, Paused, Idle, Empty)
- 🔄 **Auto-Pause on Empty** — Queues automatically pause when empty
- ⏱️ **Smart Scheduling** — Automatic start/stop based on time windows
- 🔒 **Manual Override** — User pause/resume overrides automatic scheduling
- 📊 **Queue Progress** — Overall progress bar for each queue

### Advanced Features

- 🌐 **Browser Extension** — Firefox & Chrome extension with smart connection handling
- 🔌 **aria2 Integration** — High-performance multi-connection downloads
- 🎨 **Modern UI** — Dark/Light theme with Papirus icons
- ⚡ **Speed Limit** — Global and per-queue download speed limiting
- 🖥️ **System Tray** — Minimize to tray with status indicator
- 🔄 **Download Interception** — Catch browser downloads automatically
- 🎬 **Splash Screen** — Beautiful loading animation with circular logo
- 🔧 **Systemd Service** — Run as background service
- 📥 **CLI Support** — Add URLs from command line with `--add`
- 🌐 **Proxy Support** — Global, per-queue, and per-download proxy configuration (HTTP/HTTPS/SOCKS5)
- 📦 **Independent Progress Windows** — Separate windows for download progress that stay open even when main window is closed
- 🟢 **Smart Extension** — Browser extension shows connection status with visual badges
- ⚡ **Smart Fallback** — When FelfelDM is not running, downloads proceed normally
- 💾 **Persistent State** — All downloads and queues are preserved between sessions
- 🔄 **Download Resume** — Resume interrupted downloads from where they stopped
- 🔄 **In-App Update** — Update FelfelDM directly from the application (Help → About → Update)

### YouTube Download Features

- 🎥 **Video Download** — Download videos in MP4, WebM formats
- 🎵 **Audio Extraction** — Extract audio as MP3, M4A
- 📐 **Quality Selection** — Choose from available qualities (1080p, 720p, 480p, etc.)
- 🔄 **Best Quality** — Automatically select the best available format
- 🍪 **Cookie Support** — Use browser cookies for age-restricted content
- 🌐 **Proxy Support** — Download YouTube videos through proxy
- 📊 **Real-time Progress** — Live progress, speed, and ETA for YouTube downloads
- ⏸️ **Pause/Resume** — Pause and resume YouTube downloads
- 🗑️ **Clean Removal** — Remove downloads and associated files
- 🎬 **YouTube Category** — YouTube downloads are visually distinguished in the queue
- 📁 **Custom Output** — Choose where to save downloaded files
- 🖥️ **Standalone Dialog** — Independent progress dialog for YouTube downloads

---

## 🛠️ Installation

### Quick Install (Recommended)

```bash
bash <(curl -s https://raw.githubusercontent.com/hoomaanf/FelfelDM/main/install.sh)
```

### Manual Install

```bash
git clone https://github.com/hoomaanf/FelfelDM.git
cd FelfelDM
./install.sh
```

### Uninstall

```bash
bash <(curl -s https://raw.githubusercontent.com/hoomaanf/FelfelDM/main/uninstall.sh)
```

---

## 🔄 Update

### Update from within the app

1. Run FelfelDM
2. Go to **Help → About**
3. Click the **Update** button
4. A dialog will show the update progress
5. Restart the app when prompted

### Update from terminal

```bash
FelfelDM --update
```

Or manually:

```bash
bash <(curl -s https://raw.githubusercontent.com/hoomaanf/FelfelDM/main/install.sh)
```

---

## 🚀 Usage

### Running the Application

```bash
# Normal mode
FelfelDM

# Add URLs from command line
FelfelDM --add "https://example.com/file.zip" "https://example.com/file2.zip"

# Run as daemon (background service)
FelfelDM --daemon

# Clear all data and reset settings
FelfelDM --clear

# Update FelfelDM
FelfelDM --update
```

### Adding Downloads

#### Regular Downloads:
1. Click **Download** button or press `Ctrl+N`
2. Enter URLs (one per line)
3. Select queue and options
4. Click OK

#### YouTube Downloads:
1. Click **YouTube** button in the toolbar
2. Paste the YouTube URL
3. Select quality and format
4. Choose queue and save location
5. Click Download

### YouTube Download

FelfelDM supports downloading videos and audio from YouTube with advanced features:

**Quality Selection:**
- **Dynamic Quality List** — Automatically fetches available qualities for each video
- **Video Formats** — MP4, WebM with various resolutions (1080p, 720p, 480p, etc.)
- **Audio Formats** — MP3, M4A with bitrate options
- **Best Quality** — Automatically selects the best available format

**Requirements:**
- yt-dlp must be installed
- For age-restricted or private videos, export cookies from your browser

### Queue Status

FelfelDM shows the current status of each queue in the sidebar:

| Status | Description |
|--------|-------------|
| **▶ Running** | Queue is active and at least one download is in progress |
| **⏸ Paused** | Queue is manually paused by the user |
| **⏳ Idle** | Queue has downloads but none are active (all complete/error) |
| **📭 Empty** | Queue has no downloads |
| **✅ Complete** | All downloads in the queue are complete |
| **▶ Running (🕐 Scheduled)** | Queue is running within its scheduled time window |
| **⏸ Paused (🕐 Scheduled)** | Queue is paused but within its scheduled time window |
| **⏰ Waiting for Schedule** | Queue is waiting for its scheduled time to start |

### Proxy Configuration

FelfelDM supports proxy configuration at three levels:

| Level | Description | Where to Configure |
|-------|-------------|-------------------|
| **Global Proxy** | Applies to all downloads by default | Settings → Proxy Settings |
| **Queue Proxy** | Overrides global proxy for a specific queue | Right-click queue → Settings → Proxy Settings |
| **Download Proxy** | Overrides all other proxy settings for a single download | Add Download dialog → Proxy Settings or right-click → Proxy Settings |

**Supported Proxy Types:**
- HTTP/HTTPS Proxy (`http://proxy:port`)
- SOCKS5 Proxy (`socks5://proxy:port`)
- Authentication supported via `user:pass@host:port`

**YouTube Proxy Support:**
- YouTube downloads also support proxy configuration
- Proxy settings from the main dialog are automatically applied to the download progress window
- No need to re-enter proxy details in the progress dialog

### Keyboard Shortcuts

| Shortcut | Action              |
| -------- | ------------------- |
| `Ctrl+N` | Add downloads       |
| `Ctrl+Q` | Quit application    |
| `Ctrl+,` | Open settings       |
| `F5`     | Refresh table       |
| `Esc`    | Close splash screen |

---

## 🌐 Browser Extension

### Firefox Add-on

```
https://addons.mozilla.org/en-US/firefox/addon/felfeldm/
```

### Manual Installation

```bash
cd FelfelDM-extension
./install.sh
```

### Extension Features

- 📥 **One-click Download** — Add current page to FelfelDM
- 🖱️ **Context Menu** — Right-click links, images, videos
- 🔗 **Selected Links** — Download multiple links from selection
- 🎯 **Download Interception** — Auto-catch browser downloads
- 🔔 **Notifications** — Status updates and confirmations
- 🔄 **Toggle Switch** — Enable/disable download catching
- 📡 **Dual Port Support** — Works with both GUI and service modes
- 🟢 **Visual Badges** — Status indicators on extension icon:
  - **⬇️ Green** — Connected and ready
  - **⛔ Yellow** — Catch mode is off
  - **✕ Red** — Application is not running
- ⚠️ **Smart Fallback** — When FelfelDM is not running, downloads proceed normally instead of failing silently
- 📊 **Statistics** — Track intercepted and added downloads

### Extension Status Guide

The FelfelDM browser extension shows its status through visual badges on its icon:

| Badge | Color | Meaning |
|-------|-------|---------|
| **⬇️** | 🟢 Green | Connected to FelfelDM, ready to intercept downloads |
| **⛔** | 🟡 Yellow | Connected but download catching is disabled |
| **✕** | 🔴 Red | FelfelDM is not running |

**What happens when FelfelDM is not running:**
- Downloads will proceed normally (not intercepted)
- You'll receive a notification explaining why
- No downloads are lost or canceled

---

## 📁 Project Structure

```bash
FelfelDM/
├── core/                    # Core modules
│   ├── aria2_rpc.py        # aria2 JSON-RPC client
│   ├── data_store.py       # Data persistence
│   ├── download_updater.py # Download status updater
│   ├── file_size_fetcher.py# File size fetcher
│   ├── local_server.py     # Local HTTP server for extension
│   ├── proxy_manager.py    # Proxy configuration
│   ├── queue_model.py      # Queue data model
│   ├── temp_db.py          # Temporary in-memory database
│   ├── worker.py           # Background download worker
│   ├── youtube_downloader.py # YouTube download core
│   └── youtube_worker.py   # YouTube download worker
├── ui/                      # UI components
│   ├── delegates.py        # Custom table delegates
│   ├── dialogs.py          # Various dialogs
│   ├── download_proxy_dialog.py # Proxy configuration dialog
│   ├── main_window.py      # Main application window
│   ├── proxy_dialog.py     # Proxy settings dialog
│   ├── splash.py           # Splash screen
│   ├── table_model.py      # Download table model
│   ├── update_dialog.py    # Update dialog
│   └── youtube_progress.py # YouTube progress dialog
├── utils/                   # Utilities
│   ├── helpers.py          # Helper functions
│   └── style.py            # Theme styles
├── FelfelDM-extension/      # Browser extension
│   ├── background.js       # Extension background script
│   ├── content.js          # Content script
│   ├── popup.html          # Popup UI
│   ├── popup.js            # Popup logic
│   ├── install.sh          # Extension installer
│   ├── manifest-chrome.json # Chrome manifest
│   └── manifest-firefox.json # Firefox manifest
├── FelfelDM.git/            # Arch Linux package files
│   ├── felfeldm.install    # Arch install script
│   └── PKGBUILD            # Arch package build file
├── logo/                    # Application icons
│   └── icon512.png         # Main icon
├── screenshots/             # Application screenshots
│   └── main-window.png     # Main window screenshot
├── main.py                  # Entry point with CLI support
├── install.sh               # Installation script
├── uninstall.sh             # Uninstallation script
├── requirements.txt         # Python dependencies
└── README.md                # This file
```

---

## 🐛 Troubleshooting

### aria2 not found

```bash
# Arch / Manjaro
sudo pacman -S aria2 yt-dlp

# Debian / Ubuntu / Mint
sudo apt install aria2 yt-dlp

# Fedora
sudo dnf install aria2 yt-dlp
```

### Extension not connecting

1. Make sure FelfelDM is running
2. Test GUI: `curl http://localhost:8766/ping`
3. Test Service: `curl http://localhost:8765/ping`
4. Check service status: `systemctl --user status felfeldm.service`

### Extension shows "✕" badge

1. Make sure FelfelDM is running
2. Check if the application is listening on port 8766/8765
3. Test connection: `curl http://localhost:8766/ping`
4. If you see a red "✕" on the extension icon, it means FelfelDM is not running
5. Downloads will proceed normally (not intercepted) when the app is not running

### Extension shows "⛔" badge

1. Download catching is disabled
2. Click on the extension icon and toggle "Catch Downloads" to enable it
3. The badge will change to "⬇️" when enabled

### Extension not showing any badge

1. Try reloading the extension
2. Check if the extension is properly installed
3. Restart your browser

### Service not starting

```bash
# Reset service
systemctl --user stop felfeldm.service
systemctl --user disable felfeldm.service
rm -f ~/.config/systemd/user/felfeldm.service
systemctl --user daemon-reload
# Then reinstall from settings
```

### Permission denied

```bash
chmod +x main.py
chmod +x install.sh
chmod +x uninstall.sh
```

### YouTube download requires cookies

1. Install browser extension: [Get cookies.txt](https://github.com/rotemdan/ExportCookies)
2. Export cookies from YouTube
3. Use the cookie file in YouTube download dialog

### YouTube downloads not starting

1. Make sure yt-dlp is installed: `which yt-dlp`
2. Check if yt-dlp is up to date: `yt-dlp -U`
3. Try downloading without proxy first
4. Check the console output for error messages

### YouTube download speed not showing

1. YouTube downloads use yt-dlp for downloading
2. Speed is shown in the YouTube progress dialog
3. Total speed in the status bar includes both aria2 and YouTube downloads
4. Check the YouTube progress dialog for detailed information

### Proxy not working

1. Test proxy in terminal: `curl -x http://proxy:port https://www.google.com`
2. For SOCKS5, use: `curl -x socks5://proxy:port https://www.google.com`
3. Check authentication format: `http://user:pass@proxy:port`
4. Make sure proxy is enabled in Settings

### Queue scheduling not working

1. Make sure schedule is enabled in queue settings
2. Check the schedule time and days
3. Queue will automatically start/stop based on schedule
4. Manual pause/resume overrides automatic scheduling
5. Check console output for schedule debug messages

---

## 🔧 Development

### Setup Development Environment

```bash
git clone https://github.com/hoomaanf/FelfelDM.git
cd FelfelDM
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 main.py
```

### Building from Source

```bash
./install.sh
```

---

## 🙏 Acknowledgments

- [aria2](https://aria2.github.io/) — High-speed download utility
- [PyQt6](https://www.riverbankcomputing.com/software/pyqt/) — Python bindings for Qt6
- [Papirus](https://github.com/PapirusDevelopmentTeam/papirus-icon-theme) — Icon theme
- [systemd](https://systemd.io/) — Service management
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) — YouTube downloading

---

## 📞 Support

- 🐛 **Issues**: [GitHub Issues](https://github.com/hoomaanf/FelfelDM/issues)
- 💬 **Discussions**: [GitHub Discussions](https://github.com/hoomaanf/FelfelDM/discussions)
- 📧 **Email**: hoomaanfelfeli@gmail.com

---

<div align="center">
  <sub>Built with ❤️ and 🌶️</sub>
  <br>
  <sub>© 2026 FelfelDM Contributors</sub>
</div>
