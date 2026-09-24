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
    <img src="https://img.shields.io/badge/AUR-available-blue?style=for-the-badge&logo=arch-linux" alt="AUR">
    <img src="https://img.shields.io/badge/Firefox-FF7139?style=for-the-badge&logo=firefox" alt="Firefox">
    <img src="https://img.shields.io/badge/Chrome-4285F4?style=for-the-badge&logo=google-chrome" alt="Chrome">
  </p>
</div>

---

## 📸 Screenshot

<div align="center">
  <img src="screenshots/main-window.png" alt="FelfelDM Main Window" width="800">
  <p><em>Main Interface - Dark Theme with Details Panel</em></p>
</div>

---

## 🚀 Quick Install

### AUR (Arch Linux / Manjaro)

```bash
# Git version (latest updates)
yay -S felfeldm-git

# Or with paru
paru -S felfeldm-git
```

### Other Distributions

```bash
bash <(curl -s https://raw.githubusercontent.com/hoomaanf/FelfelDM/main/install.sh)
```

---

## ✨ Features

### Core Features

- 🚀 **Multiple Queues** — Create and manage multiple download queues
- ⏰ **Scheduled Downloads** — Set time windows for automatic downloads
- 📊 **Real-time Progress** — Live download speed and progress tracking
- 🎯 **Smart Management** — Intelligent auto-retry with configurable delay, pause/resume, and error handling
- 🔄 **Smart Retry** — Automatically retry transient errors (timeout, 5xx, 429) with a configurable delay; fail fast on permanent errors (404, 403, 401, TLS/certificate issues)
- ⏱️ **Countdown Retry** — Live countdown in the Status column while waiting between retry attempts (e.g. `🔄 Retrying in 5s... (2/5)`)
- 🗑️ **Safe Removal** — Remove from list or delete files permanently
- 🎵 **YouTube Download** — Download videos and audio from YouTube with dynamic quality selection
- 📋 **Details Panel** — View download details (name, size, downloaded, status, path) with quick actions
- ⌨️ **Keyboard Shortcuts** — Full keyboard navigation for power users

### 🎯 Preview Sizes Before Downloading

No need to add the file to see its size! When you enter URLs:

- **Full file list with exact sizes** — See every file with its precise size before downloading
- **Per-row checkbox** — Select only the files you want (click anywhere in the cell)
- **Select All / Deselect All** — Quick selection buttons
- **Total selected size** — See the total size of your selection at the bottom of the dialog
- **Smart Add button** — The Download button is only enabled when at least one file is selected

### ⚡ Parallel Size Fetching

Previously, file sizes were fetched one by one with delays. Now, with **5 parallel threads**:

- All file sizes are fetched in just a few seconds
- Works both in the Add Download dialog **and** in the main window table
- Uses the full `FileSizeFetcher` logic (HEAD → RANGE → STREAM → yt-dlp fallback)

### 🗑️ Delete Files Without UI Freezing

The "Remove & Delete Files" operation no longer freezes the UI:

- **Instant operations** for downloads that never started (nothing on disk to delete)
- **Background deletion** for partial downloads — files are deleted in a separate thread
- **Batch RPC** to aria2 instead of dozens of individual requests
- **Progress feedback** in the status bar during deletion

### Queue Management

- 📋 **Queue Status** — Real-time status display for each queue (Running, Paused, Idle, Empty)
- 🔄 **Auto-Pause on Empty** — Queues automatically pause when empty
- ⏱️ **Smart Scheduling** — Automatic start/stop based on time windows
  - Queues start automatically at the scheduled time and pause when the window ends
  - Manual pause overrides the schedule until the next window
  - All downloads pause cleanly when the window ends (no flicker or partial states)
- 🔒 **Manual Override** — User pause/resume overrides automatic scheduling
- 📊 **Queue Progress** — Overall progress bar for each queue

### Advanced Features

- 🌐 **Browser Extension** — Firefox & Chrome extension with smart connection handling
- 🔌 **aria2 Integration** — High-performance multi-connection downloads
- 🎨 **Modern UI** — Dark/Light theme with Papirus icons
- ⚡ **Speed Limit** — Global and per-queue download speed limiting
  - **Global Speed Limit** — Limits the total speed of all downloads
  - **Queue Speed Limit** — Limits the total speed of a queue; the limit is split evenly across the active downloads in that queue (e.g. 100 KB/s across 3 active downloads → ~33 KB/s each)
  - **Queue overrides Global** — When a queue has its own speed limit, it takes priority over the global one
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
- ⚡ **Optimized Performance** — Reduced RPC calls for better responsiveness
- 🚀 **Parallel Size Fetching** — Fetch sizes for multiple URLs in parallel
- 🎯 **Preview Before Download** — See file sizes and select files before adding them
- 🏗️ **Robust Download Tracking** — UUID-based internal identifiers keep downloads stable across retries and restarts

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
- 🪟 **Multiple Dialogs** — Open multiple YouTube progress dialogs simultaneously

---

## 🛠️ Installation

### AUR (Arch Linux / Manjaro)

```bash
# Git version (latest updates)
yay -S felfeldm-git

# Or with paru
paru -S felfeldm-git

# Or manually
git clone https://aur.archlinux.org/felfeldm-git.git
cd felfeldm-git
makepkg -si
```

### Quick Install (Other Distributions)

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

#### From AUR:

```bash
sudo pacman -Rsn felfeldm-git
```

#### From other installations:

```bash
bash <(curl -s https://raw.githubusercontent.com/hoomaanf/FelfelDM/main/uninstall.sh)
```

---

## 🔄 Update

### Update from inside the app

Open the **About** dialog from the Help menu → click the **Update** button. The updater will download and install the latest version automatically.

### Update from terminal

```bash
# Via AUR (Arch Linux)
yay -Suy felfeldm-git

# Via built-in updater
FelfelDM --update

# Or manually
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
3. Wait for file sizes to be fetched (a few seconds)
4. Review the list and select the files you want
5. Choose queue and options
6. Click **Download** or **Add to Queue**

#### YouTube Downloads:

1. Click **YouTube** button in the toolbar
2. Paste the YouTube URL
3. Select quality and format
4. Choose queue and save location
5. Click Download

### Preview Sizes Before Downloading

When you paste multiple URLs into the Add Download dialog:

- The dialog splits into a **left panel** (URLs) and a **right panel** (file list)
- Each file is displayed in a table with its **name**, **size**, and **status**
- You can **check/uncheck** files individually (click anywhere in the checkbox column)
- Use **Select All / Deselect All** for bulk operations
- The **total size** of your selection is shown at the bottom
- The **Add to Queue / Download** button is only enabled when at least one file is selected

The **progress bar** at the top shows fetch progress. When all sizes are fetched, it shows "✅ All sizes fetched".

### Details Panel

The details panel provides quick access to download information and actions:

- **File**: Download name
- **Size**: Total file size
- **Downloaded**: Downloaded size
- **Status**: Current download status
- **Path**: Download folder location

**Quick Actions:**

- **Pause/Resume** — Control the selected download
- **Cancel** — Remove the download (with option to delete files)
- **Open Folder** — Open the download folder
- **Copy URL** — Copy the download URL to clipboard

**Toggle Details Panel:**

- Press `Ctrl+D` or click the details button in the toolbar

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

| Status                       | Description                                                  |
| ---------------------------- | ------------------------------------------------------------ |
| **▶ Running**                | Queue is active and at least one download is in progress     |
| **⏸ Paused**                 | Queue is manually paused by the user                         |
| **⏳ Idle**                  | Queue has downloads but none are active (all complete/error) |
| **📭 Empty**                 | Queue has no downloads                                       |
| **✅ Complete**              | All downloads in the queue are complete                      |
| **▶ Running (🕐 Scheduled)** | Queue is running within its scheduled time window            |
| **⏸ Paused (🕐 Scheduled)**  | Queue is paused but within its scheduled time window         |
| **⏰ Waiting for Schedule**  | Queue is waiting for its scheduled time to start             |

### Retry Settings

FelfelDM supports smart retry with configurable behavior:

| Setting                | Default   | Description                                                                |
| ---------------------- | --------- | -------------------------------------------------------------------------- |
| **Max Retry Attempts** | 5         | Maximum number of automatic retry attempts for failed downloads            |
| **Retry Delay**        | 5 seconds | Delay between retry attempts (only for transient errors)                   |
| **Max Tries (aria2)**  | 5         | aria2's internal retry count per download (separate from FelfelDM's retry) |

**How it works:**

- **Transient errors** (timeout, connection reset, 5xx, 429) → automatically retried with the configured delay
- **Permanent errors** (404, 403, 401, TLS/certificate issues) → fail immediately, no retry
- **Countdown display** — While waiting, the Status column shows `🔄 Retrying in 5s... (2/5)`

**Configure these in:** Settings → General → Download

### Speed Limit Settings

FelfelDM supports speed limiting at two levels:

| Level                  | Description                                | Where to Configure                   |
| ---------------------- | ------------------------------------------ | ------------------------------------ |
| **Global Speed Limit** | Limits the total speed of all downloads    | Settings → Speed                     |
| **Queue Speed Limit**  | Limits the total speed of a specific queue | Right-click queue → Settings → Speed |

**How Queue Speed Limit works:**

When a queue has a speed limit (e.g. 100 KB/s) and multiple downloads are active:

- The limit is **split evenly** across all active downloads in that queue
- Example: 100 KB/s with 3 active downloads → ~33 KB/s per download
- When a download completes, the remaining downloads automatically get a larger share
- Queue Speed Limit **overrides** Global Speed Limit when set

### Proxy Configuration

FelfelDM supports proxy configuration at three levels:

| Level              | Description                                              | Where to Configure                                                   |
| ------------------ | -------------------------------------------------------- | -------------------------------------------------------------------- |
| **Global Proxy**   | Applies to all downloads by default                      | Settings → Proxy Settings                                            |
| **Queue Proxy**    | Overrides global proxy for a specific queue              | Right-click queue → Settings → Proxy Settings                        |
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

FelfelDM supports comprehensive keyboard shortcuts for efficient usage:

| Shortcut         | Action                  |
| ---------------- | ----------------------- |
| `Ctrl+N`         | Add Downloads           |
| `Ctrl+U`         | Add URL                 |
| `Space`          | Pause/Resume selected   |
| `Ctrl+P`         | Pause selected          |
| `Ctrl+R`         | Resume selected         |
| `Delete`         | Remove selected         |
| `Shift+Delete`   | Remove and delete files |
| `Ctrl+D`         | Toggle details panel    |
| `Ctrl+F`         | Focus search            |
| `Escape`         | Clear search            |
| `Ctrl+Tab`       | Next queue              |
| `Ctrl+Shift+Tab` | Previous queue          |
| `Ctrl+,`         | Settings                |
| `F5`             | Refresh                 |
| `F1`             | Show shortcuts          |

Press `F1` at any time to view all keyboard shortcuts.

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

| Badge  | Color     | Meaning                                             |
| ------ | --------- | --------------------------------------------------- |
| **⬇️** | 🟢 Green  | Connected to FelfelDM, ready to intercept downloads |
| **⛔** | 🟡 Yellow | Connected but download catching is disabled         |
| **✕**  | 🔴 Red    | FelfelDM is not running                             |

**What happens when FelfelDM is not running:**

- Downloads will proceed normally (not intercepted)
- You'll receive a notification explaining why
- No downloads are lost or canceled

---

## 🏗️ Architecture

FelfelDM uses a **UUID-based download identity** for stability across retries, restarts, and GID changes:

- Each download gets a permanent `download_id` (UUID) when added
- aria2's GID is stored as a separate field (`aria2_gid`) and can change freely during retries
- When a retry replaces the aria2 GID, all references (queue, progress dialogs, storage) stay intact
- This makes retry, pause/resume, restart, and scheduled start/stop robust and race-free

### Data Flow

```
Add Download
    ↓
download_id = uuid4().hex[:16]  (permanent)
aria2_gid = "<gid from aria2>"
    ↓
q.downloads.append(download_id)
_all_downloads[download_id] = {aria2_gid, status, ...}
    ↓
[Retry / GID change]
    ↓
_all_downloads[download_id]["aria2_gid"] = new_gid
# Only one field changes — everything else stays intact
```

### Retry State Machine

```
         error detected
              ↓
        ┌─────────────┐
        │  retrying   │  ← countdown: "🔄 Retrying in 5s... (2/5)"
        └──────┬──────┘
               │ delay expires
               ↓
        ┌─────────────┐
        │  re-add URL │
        └──────┬──────┘
               │
               ↓
        ┌─────────────┐
        │   active    │  ← downloading
        └──────┬──────┘
               │ error again
               ↓
             (loop)

Permanent errors (404, 403, ...) skip the loop and fail immediately.
```

---

## 📁 Project Structure

```bash
FelfelDM/
    ├── core/                          # Core modules
    │   ├── __init__.py
    │   ├── aria2_handler.py           # aria2 handler
    │   ├── aria2_rpc.py               # aria2 JSON-RPC client
    │   ├── data_store.py              # Data persistence (UUID-based)
    │   ├── file_size_fetcher.py       # File size fetcher (HEAD → RANGE → STREAM → yt-dlp)
    │   ├── local_server.py            # Local HTTP server for extension
    │   ├── proxy_manager.py           # Proxy configuration
    │   ├── queue_model.py             # Queue data model
    │   ├── queue_worker.py            # Queue operation worker
    │   ├── size_fetcher_worker.py     # Parallel size fetcher (5 threads)
    │   ├── temp_db.py                 # Temporary in-memory database
    │   ├── worker.py                  # Background download worker
    │   ├── youtube_downloader.py      # YouTube download core
    │   └── youtube_worker.py          # YouTube download worker
    ├── ui/                            # UI components
    │   ├── __init__.py
    │   ├── delegates.py               # Custom table delegates
    │   ├── dialogs.py                 # Various dialogs (with unified AddDownloadDialog)
    │   ├── download_proxy_dialog.py
    │   ├── export_dialog.py           # Export dialog
    │   ├── export_manager.py          # Export manager
    │   ├── main_window.py             # Main application window
    │   ├── proxy_dialog.py            # Proxy settings dialog
    │   ├── splash.py                  # Splash screen
    │   ├── table_model.py             # Download table model
    │   ├── update_dialog.py           # Update dialog
    │   └── youtube_progress.py        # YouTube progress dialog
    ├── utils/                         # Utilities
    │   ├── __init__.py
    │   ├── helpers.py                 # Helper functions
    │   └── style.py                   # Theme styles
    ├── FelfelDM-extension/            # Browser extension
    │   ├── background.js
    │   ├── content.js
    │   ├── icons/
    │   ├── popup.html
    │   ├── popup.js
    │   ├── install.sh
    │   ├── manifest-chrome.json
    │   └── manifest-firefox.json
    ├── FelfelDM.git/                  # Arch Linux package files
    │   ├── felfeldm.install
    │   └── PKGBUILD
    ├── logo/                          # Application icons
    │   ├── icon512.png
    │   └── tray-active.png
    ├── screenshots/                   # Application screenshots
    │   └── main-window.png
    ├── main.py                        # Entry point
    ├── install.sh                     # Installation script
    ├── uninstall.sh                   # Uninstallation script
    ├── requirements.txt               # Python dependencies
    └── README.md                      # This file
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

### Downloads stuck in "Waiting" after restart

1. This is expected behavior — after a restart, all downloads are set to **Paused** so you can review them before starting
2. Press **Start** on the queue to resume
3. Downloads that were active before the restart will continue from where they stopped

### Retry not working as expected

1. Check **Settings → General → Download → Max Retry Attempts** and **Retry Delay**
2. Permanent errors (404, 403, 401, TLS) are **not** retried by design
3. Transient errors (timeout, 5xx) are retried with the configured delay
4. The Status column shows the countdown: `🔄 Retrying in 5s... (2/5)`

### Speed limit not being applied

1. **Queue Speed Limit overrides Global Speed Limit** — if a queue has its own limit, the global one is ignored
2. The Queue Speed Limit is **split across active downloads** (e.g. 100 KB/s ÷ 3 active downloads = ~33 KB/s each)
3. Restart the download after changing speed limits to ensure the new limit is applied
4. Check the console for `⚡ [SpeedLimit]` messages

### File size shows as unknown

1. Some servers don't return size via HEAD or RANGE requests
2. The file will still download, but size won't be shown before downloading
3. Try a different server or download the file and check the size afterward

### UI freezes when removing files

This has been fixed in the latest version. Update FelfelDM to get the fix.

### Wrong file size (e.g., 3.00 GB for all files)

1. This may happen if an incorrect size was cached earlier
2. Update FelfelDM to the latest version — new sizes are fetched from the server
3. If the issue persists, delete the cache files in `~/.config/felfelDM/` and restart

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
</div>
```
