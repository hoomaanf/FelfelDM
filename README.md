**English** | [فارسی](./README.fa.md)

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
- 🕐 **Schedule that Works When Locked** — Schedules run in a separate thread, so downloads start on time even when the screen is locked
- 📊 **Real-time Progress** — Live download speed and progress tracking
- 🎯 **Download Rules** — Automatically apply queue, folder, connections, and speed limit based on URL pattern, extension, domain, or file size
- 🎯 **Smart Management** — Intelligent auto-retry with configurable delay, pause/resume, and error handling
- 🎯 **Single Source of Truth** — aria2 is the only source for a download's status and speed. The UI never invents state; if aria2 says `active`, the app shows `active`
- 🚫 **Smart Duplicate Detection** — The same URL cannot be added twice to the **same queue**, but is allowed across **different queues** (with a notification naming the queues that already have it)
- 🔄 **Smart Retry** — Automatically retry transient errors (timeout, DNS, connection, TLS packet, 5xx, 429) with a configurable delay; fail fast on permanent errors (404, 403, 401, certificate issues)
- 🔁 **Retry Counter Reset** — The failed-attempt counter resets to 0 in three cases: (a) after a configurable period of healthy downloading, (b) **when the queue is paused** (so a queue paused overnight doesn't stay blocked by counters from a momentary outage), and (c) **when the user clicks Start Queue** (an explicit user action beats the cap)
- ⏱️ **Countdown Retry** — Live countdown in the Status column while waiting between retry attempts (e.g. `🔄 Retrying in 5s... (2/5)`)
- 🗑️ **Safe Removal** — Remove from list, or delete files with a confirmation dialog that lists exactly what will be deleted (main file + aria2 sidecar + temp files)
- 🎵 **YouTube Download** — Download videos and audio from YouTube with dynamic quality selection
- 📋 **Details Panel** — View download details (name, size, downloaded, status, path) with quick actions including Retry for failed downloads
- 🔄 **Per-Download Retry** — A Retry button appears in the Details Panel when a download fails, re-adding it with a fresh aria2 gid
- 📜 **Live Log Viewer** — See the current session's log in a live window (`Ctrl+L` or `View → Show Logs`), with auto-scroll, clear, and refresh
- 🖱️ **Open Completed Files on Double-Click** — Double-click a completed download to open the file with the system default application (`Ctrl+Double-Click` opens the details dialog)
- 📥 **Drag & Drop** — Drag links, plain-text URLs, or `.txt` files containing URLs onto the downloads table to open the Add to Queue dialog
- ⌨️ **Keyboard Shortcuts** — Full keyboard navigation for power users

### Download Rules

Rules let you define conditions and actions that are applied automatically when a new download is added.

**Conditions (all must match — AND logic):**

| Condition        | Example                       | Description                                  |
| ---------------- | ----------------------------- | -------------------------------------------- |
| **URL contains** | `.iso`                        | Substring match (case-insensitive)           |
| **URL regex**    | `^https?://.*\.iso$`          | Regular expression match                     |
| **Extension is** | `iso`, `zip`, `mp4`           | File extension (with or without dot)         |
| **Domain is**    | `github.com` / `*.github.com` | Hostname (exact or subdomain match)          |
| **Size**         | `500M` to `5G`                | File size range (supports B, KB, MB, GB, TB) |

**Actions:**

| Action          | Example           | Description                                      |
| --------------- | ----------------- | ------------------------------------------------ |
| **Queue**       | `Linux ISOs`      | Send download to a specific queue                |
| **Folder**      | `~/Downloads/ISO` | Save to a specific folder (supports ~ expansion) |
| **Connections** | `8`               | Number of parallel connections                   |
| **Speed limit** | `500` KB/s        | Per-download speed limit                         |

**How it works:**

- Rules are evaluated **top-to-bottom**; the **first match wins**
- Rules are applied **only when adding a new download** (not to downloads already in progress)
- The matched rule's name is shown in the download list: `file.zip  [rule: Linux ISOs]`
- Rules survive app restarts and are re-applied automatically
- Rule speed limit **overrides** queue speed limit when both are set

**Where to configure:** Settings → General → Download Rules → Manage Rules...

### 🎯 Automatic Queue Selection

The Add Download dialog picks the right queue automatically based on how many URLs you paste:

| URL count | Selected queue | Notes |
|-----------|----------------|-------|
| **0 or 1** | **Direct Downloads** | Starts immediately, no queue |
| **2 or more** | **First real queue** | Direct Downloads is **removed from the list** (not just disabled) |

- If you manually pick a queue, auto-selection is disabled for that dialog session (your choice is respected)
- If you clear all URLs, auto-selection re-enables
- The **Save to** path always follows the selected queue's folder

### 🚫 Duplicate URL Handling

FelfelDM tracks every URL that's already in any queue. When you add a URL that already exists:

| Situation | Behavior |
|-----------|----------|
| **Same queue** — URL is already in the queue you're adding to | ⛔ **Blocked silently.** Notification: `This URL is already in queue 'X'. Nothing was added.` |
| **Different queue** — URL is in another queue, adding to a new one | ✅ **Allowed.** Notification: `ℹ️ already existed in 'X' — added anyway`. The file will be downloaded twice into two different folders. |
| **Multiple queues** — URL is in 2+ queues, adding to a third | ✅ Allowed, notification lists **all** existing queues |

**Why this design?**

- Same queue = no value in downloading the same file twice to the same folder
- Different queues = the user may want different proxy, speed limit, folder, or schedule
- Notifications make it clear **what** was skipped and **why**, so nothing silently fails

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

### 🗑️ Safe File Deletion

When you choose "Remove & Delete Files", FelfelDM shows a **confirmation dialog listing every file that will be deleted**:

- **Full file list** — main file, aria2 sidecar (`.aria2`), and any temp files (`.part`, `.ytdl`, `.f<digits>`)
- **Per-file details** — filename, size, and location
- **Total size** — see the total disk space that will be freed
- **Unrelated files are never touched** — only files matching this download (by name or gid) are collected
- **Instant for downloads that never started** — nothing on disk to delete

This fixes a previous issue where deleting one download could accidentally remove unrelated files sharing the same folder.

### 🖱️ Open Completed Downloads on Double-Click

Double-click a **completed** download in the main table to open it directly with the system default application (video player, PDF reader, etc.).

- `Ctrl+Double-Click` forces the details dialog (previous behavior)
- Falls back to the details dialog if the file is missing, or opens the folder if the path is a directory
- Active, paused, and errored downloads keep the previous behavior (details dialog)
- YouTube downloads always open the YouTube progress dialog

### 📥 Drag & Drop Links

Drag a link, text selection, or `.txt` file containing URLs onto the **downloads table** to open the **Add to Queue** dialog pre-filled with those URLs.

- Works with **Firefox**, **Chrome**, and **plain text** selections
- `.txt` files with URL lists are parsed automatically
- Non-URL text and non-`.txt` files are ignored
- A dashed overlay appears over the table while a drag hovers, so it's clear the drop is accepted
- The overlay only covers the downloads table, not the whole window

### 📜 Live Log Viewer

FelfelDM includes a built-in log viewer for debugging without leaving the app.

- **Live view** — see log output as it happens, no need to tail a file from a terminal
- **Open from** — `View → Show Logs` or press `Ctrl+L`
- **Auto-scroll** — follows new lines automatically (can be turned off)
- **Clear / Refresh** — manual controls for the log window
- **Persistent logs** — everything is also written to `~/.cache/felfelDM/logs/app.log`, with automatic rotation

**Where to open:** View → Show Logs (`Ctrl+L`)

### Queue Management

- 📋 **Queue Status** — Real-time status display for each queue (Running, Paused, Idle, Empty)
- 🔄 **Auto-Pause on Empty** — Queues automatically pause when empty
- ⏱️ **Smart Scheduling** — Automatic start/stop based on time windows
  - Queues start automatically at the scheduled time and pause when the window ends
  - Manual pause overrides the schedule until the next window
  - All downloads pause cleanly when the window ends (no flicker or partial states)
  - **Works even when the screen is locked** — schedule runs in a background thread independent of the Qt event loop
  - After unlocking, the UI reflects the real state automatically
- 🔒 **Manual Override** — User pause/resume overrides automatic scheduling
- 📊 **Queue Progress** — Overall progress bar for each queue

### Advanced Features

- 🌐 **Browser Extension** — Firefox & Chrome extension with smart connection handling
- 🔌 **aria2 Integration** — High-performance multi-connection downloads
- 🎯 **Owned aria2 Process** — FelfelDM starts its **own** `aria2c` in the foreground (no `--daemon`), so it knows the real PID. On quit — including crashes and `SIGKILL` — aria2 exits cleanly and saves its session. Other `aria2c` instances (e.g. one you started in a terminal) are **never** touched.
- 🎨 **Modern UI** — Dark/Light theme with Papirus icons
- ⚡ **Speed Limit** — Global, per-queue, and **per-download** speed limiting
  - **Global Speed Limit** — Limits the total speed of all downloads
  - **Queue Speed Limit** — Limits the total speed of a queue; the limit is split evenly across the active downloads in that queue (e.g. 100 KB/s across 3 active downloads → ~33 KB/s each)
  - **Per-Download Speed Limit** — Limits the speed of a single download; overrides the queue and global limits
  - **Priority** — Per-download > Queue > Global
- 🖥️ **System Tray** — Minimize to tray with status indicator
- 🛑 **Shutdown on Finish** — Automatically shut down the system when all downloads complete
  - Auto-unchecks when the queue becomes empty (so an empty queue never triggers shutdown)
  - Stays checked when downloads finish, so shutdown runs as expected
  - Uses DBus for passwordless shutdown (falls back to `systemctl` if needed)
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
- 📋 **Rules Manager UI** — Card-based interface to add/edit/delete/reorder rules with live preview
- 🎨 **Redesigned Progress Dialogs** — Tabbed layout (General / Speed Limit / Technical), striped progress bar for paused downloads, status-aware colors, error banner, speed-limit badge, and copy-to-clipboard for technical details
- 📜 **Built-in Log Viewer** — Open a live log window from `View → Show Logs` or press `Ctrl+L`. Useful for debugging without leaving the app.
- 💾 **Persistent Logs** — Logs are written to `~/.cache/felfelDM/logs/app.log` with automatic rotation

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
- 🎨 **Redesigned Progress Dialog** — Same tabbed layout as the regular download progress dialog

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

> ⚠️ **Running as a background service?** Restart it after every update so it reloads the new code:
>
> ```bash
> systemctl --user restart felfeldm.service
> ```
>
> Without a restart, the running process keeps the old Python code in memory — which can cause the new `--add` endpoint to crash with `QApplication failed to initialize`.

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

### Opening Completed Downloads

- **Double-click** a completed download to open the file with the system default application
- **Ctrl+Double-Click** to open the details dialog instead
- If the file was moved or deleted, FelfelDM shows a warning and falls back to the details dialog

### Drag & Drop

Drag links from your browser (or any text selection containing URLs) onto the downloads table to add them.

- The **Add to Queue** dialog opens with the dropped URLs pre-filled
- You can also drag a `.txt` file containing a list of URLs (one per line)
- A dashed overlay appears over the table while you're dragging

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
- **Retry** — Retry a failed download (re-adds it with a fresh aria2 gid)
- **Cancel** — Remove the download (with a confirmation dialog listing files to delete)
- **Open Folder** — Open the download folder
- **Copy URL** — Copy the download URL to clipboard

**Toggle Details Panel:**

- Press `Ctrl+D` or click the details button in the toolbar
- The panel is **open by default** on first launch

### Live Log Viewer

FelfelDM includes a built-in live log viewer:

- Open it from **View → Show Logs** or press **`Ctrl+L`**
- Log lines appear as they happen, with an **Auto-scroll** option
- Use **Live** to pause/resume the automatic refresh
- **Clear Log File** empties the on-disk log
- **Refresh** reloads the entire log from disk
- Logs are also written to `~/.cache/felfelDM/logs/app.log`

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

### Schedule Settings

FelfelDM schedules run in a **background thread**, independent of the main Qt event loop. This means:

- ✅ Downloads start on time **even when the screen is locked**
- ✅ Downloads pause cleanly when the scheduled window ends
- ✅ After unlocking, the UI shows the real state automatically
- ✅ Manual pause overrides the schedule until the next window

**Configure these in:** QueueSettings → Schedule

### Retry Settings

FelfelDM supports smart retry with configurable behavior:

| Setting                 | Default    | Description                                                                         |
| ----------------------- | ---------- | ----------------------------------------------------------------------------------- |
| **Max Retry Attempts**  | 5          | Maximum number of automatic retry attempts for failed downloads                     |
| **Retry Delay**         | 5 seconds  | Delay between retry attempts (only for transient errors)                            |
| **Reset Retries After** | 60 seconds | Reset the failed-attempt counter after N seconds of healthy downloading (0 = never) |
| **Max Tries (aria2)**   | 5          | aria2's internal retry count per download (separate from FelfelDM's retry)          |

**How it works:**

- **Transient errors** (timeout, DNS, connection, TLS packet, 5xx, 429) → automatically retried with the configured delay
- **Permanent errors** (404, 403, 401, certificate issues) → fail immediately, no retry
- **Countdown display** — While waiting, the Status column shows `🔄 Retrying in 5s... (2/5)`
- **Counter reset on healthy** — If a download stays healthy for the configured period, its failed-attempt counter resets to 0
- **Counter reset on pause** — Pausing a queue (manually or by schedule) resets all failed-attempt counters to 0. Starting the queue again gives every download a fresh budget. This prevents a queue paused overnight from staying blocked the next morning because of an outage that has long since been fixed.
- **Counter reset on Start Queue** — Clicking Start on a queue that already has errored downloads resets their counters before retrying, so the automatic cap doesn't silently block the retry the user explicitly requested.

**Configure these in:** Settings → General → Download

### Speed Limit Settings

FelfelDM supports speed limiting at three levels:

| Level                      | Description                                | Where to Configure                                     |
| -------------------------- | ------------------------------------------ | ------------------------------------------------------ |
| **Global Speed Limit**     | Limits the total speed of all downloads    | Settings → Speed                                       |
| **Queue Speed Limit**      | Limits the total speed of a specific queue | Right-click queue → Settings → Speed                   |
| **Per-Download Speed Limit** | Limits the speed of a single download    | Progress dialog → Speed Limit tab, or Add Download dialog → Speed Limit |

**Priority:** Per-download > Queue > Global

**How Queue Speed Limit works:**

When a queue has a speed limit (e.g. 100 KB/s) and multiple downloads are active:

- The limit is **split evenly** across all active downloads in that queue
- Example: 100 KB/s with 3 active downloads → ~33 KB/s per download
- When a download completes, the remaining downloads automatically get a larger share
- Queue Speed Limit **overrides** Global Speed Limit when set

**How Per-Download Speed Limit works:**

- Set from the **Speed Limit** tab in the progress dialog (applies immediately)
- Overrides both queue and global limits for that download
- Set to `0` to fall back to the queue's limit
- Persisted across app restarts

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
| `Ctrl+L`         | Show logs               |

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
- 🎯 **YouTube Inline Button** — A small FelfelDM icon appears on YouTube and YouTube Music pages; click it to send the URL straight to the yt-dlp dialog
- 🔔 **Notifications** — Status updates and confirmations
- 🎨 **Cleaner Notifications** — Fewer icons in the extension popup, so status and action feedback is easier to read at a glance
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

### Download Rules Flow

```
Add Download
    ↓
rule_engine.find_match(url)
    ↓
[Rule matched]
    ↓
Override queue / folder / connections / speed limit
    ↓
Store matched rule name + speed limit in _all_downloads[download_id]
    ↓
[Restart]
    ↓
Re-apply rule on restore — matched_rule survives
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

### File Deletion Flow

```
Remove & Delete Files
    ↓
_collect_files_for_gids(gids)  ← build list, no deletion yet
    ↓
[No files found]  → skip, nothing on disk
    ↓
DeleteFilesConfirmationDialog  ← user reviews and confirms
    ↓
[User cancels] → stop, nothing removed
    ↓
[User confirms] → delete only the listed files
    ↓
Files matching by name or gid only — unrelated files are never touched
```

### Speed Limit Priority

```
Per-Download Speed Limit  (highest priority)
        ↓ overrides
Queue Speed Limit
        ↓ overrides
Global Speed Limit        (lowest priority)
```

### MainWindow Composition

The `MainWindow` class is assembled from 17 mixins, each handling a single area of responsibility. Every method in every mixin runs on the composed `MainWindow` instance, so mixins can freely call methods from other mixins via `self`. This keeps a ~7,000-line class navigable without changing any behavior:

| Mixin | Responsibility |
|-------|----------------|
| `ui_builders` | Widgets, tray, shortcuts |
| `details_panel` | Details panel |
| `table_view` | Table, filter, context menu |
| `status_display` | Labels, buttons, speed indicators |
| `stats_sync` | aria2 polling → UI updates |
| `aria2_control` | Start/stop aria2, commands, speed limits, proxy |
| `queues` | Queues and scheduling |
| `add_download` | Drag & drop, add-download dialog |
| `youtube` | YouTube downloads |
| `progress_dialogs` | Per-download progress dialogs |
| `download_actions` | Manual pause/resume/retry |
| `retry` | Automatic retry |
| `removal` | Download and file removal |
| `file_actions` | Open file/folder, copy link |
| `settings_dialogs` | Settings, about, log viewer, export |
| `shutdown` | "Shutdown after finish" |
| `lifecycle` | Restore, save, close, quit |

The three name-based slots (`_delayed_ui_update`, `_add_from_extension`, `_open_dialog_from_extension`) stay on `MainWindow` itself because `QMetaObject.invokeMethod` only resolves slots defined on the class — not inherited from mixins.

### aria2 Process Lifecycle

FelfelDM launches its own `aria2c` and keeps full control over its lifetime.

**Why this exists:**

- aria2 has no `--pid-file` option, and starting it with `--daemon` forks it away — the app has no way to learn the real PID
- `pkill -f aria2c` (the old cleanup) also killed user's own aria2 instances
- A daemonised aria2 outlived the app, leaving downloads running silently

**What FelfelDM does instead (`core/aria2_process.py`):**

- Starts `aria2c` in the **foreground** as a child of the app — its PID is known and written to `~/.config/felfelDM/aria2.pid`
- Passes `--stop-with-process=<app_pid>` so aria2 **exits on its own** when the app dies for any reason (crash, `SIGKILL`, closed terminal)
- On normal quit, sends `SIGTERM` first so aria2 saves its session, then `SIGKILL` if it doesn't exit within 3 seconds
- **Only stops aria2 instances started with *our* config file** (`--conf-path=~/.config/felfelDM/aria2.conf`); any other `aria2c` on the machine is left alone
- Verifies PID identity via `/proc/<pid>/cmdline` before killing, so a stale PID file cannot hit an unrelated process
- Registers `atexit` cleanup so even an unhandled exception still stops aria2

**What this fixes:**

| Old behavior | New behavior |
|--------------|--------------|
| `pkill -f aria2c` killed every aria2 on the system | Only FelfelDM's aria2 is stopped |
| `--daemon` forked aria2 away, no PID known | Foreground child, PID written to `aria2.pid` |
| aria2 survived app crashes and kept downloading | `--stop-with-process` makes aria2 exit when the app does |
| Session wasn't always saved | `SIGTERM` gives aria2 time to save the session |

---

## 📁 Project Structure

```bash
FelfelDM/
    ├── core/                          # Core modules
    │   ├── __init__.py
    │   ├── aria2_handler.py           # aria2 handler
    │   ├── aria2_process.py           # Spawns aria2c as our own child (no --daemon),
    │   │                              #   knows its PID, stops only aria2 instances we started
    │   ├── aria2_rpc.py               # aria2 JSON-RPC client
    │   ├── data_store.py              # Data persistence (UUID-based)
    │   ├── error_classifier.py        # Classifies aria2 errors (transient vs permanent)
    │   ├── file_size_fetcher.py       # File size fetcher (HEAD → RANGE → STREAM → yt-dlp)
    │   ├── local_server.py            # Local HTTP server for extension
    │   ├── proxy_manager.py           # Proxy configuration
    │   ├── queue_worker.py            # Queue operation worker
    │   ├── schedule_manager.py        # Schedule thread
    │   ├── rule_engine.py             # Download rules engine
    │   ├── size_fetcher_worker.py     # Parallel size fetcher (5 threads)
    │   ├── worker.py                  # Background download worker
    │   └── youtube_worker.py          # YouTube download worker
    ├── ui/                            # UI components
    │   ├── __init__.py
    │   ├── delegates.py               # Custom table delegates
    │   ├── dialogs.py                 # Various dialogs (with unified AddDownloadDialog and DeleteFilesConfirmationDialog)
    │   ├── download_proxy_dialog.py
    │   ├── export_dialog.py           # Export dialog
    │   ├── export_manager.py          # Export manager
    │   ├── log_viewer.py              # Live log viewer dialog
    │   ├── main_window/               # Main window (split by responsibility)
    │   │   ├── __init__.py            # Package entry — re-exports MainWindow
    │   │   ├── window.py              # MainWindow class — constructor, slots, orchestration
    │   │   ├── ui_builders.py         # Widgets, tray, shortcuts
    │   │   ├── details_panel.py       # Details panel
    │   │   ├── table_view.py          # Table, filter, context menu
    │   │   ├── status_display.py      # Labels, buttons, speed indicators
    │   │   ├── stats_sync.py          # aria2 polling → UI updates
    │   │   ├── aria2_control.py       # Start/stop aria2, commands, speed limits, proxy
    │   │   ├── queues.py              # Queues and scheduling
    │   │   ├── add_download.py        # Drag & drop, add-download dialog
    │   │   ├── youtube.py             # YouTube downloads
    │   │   ├── progress_dialogs.py    # Per-download progress dialogs
    │   │   ├── download_actions.py    # Manual pause/resume/retry
    │   │   ├── retry.py               # Automatic retry
    │   │   ├── removal.py             # Download and file removal
    │   │   ├── file_actions.py        # Open file/folder, copy link
    │   │   ├── settings_dialogs.py    # Settings, about, log viewer, export
    │   │   ├── shutdown.py            # "Shutdown after finish"
    │   │   └── lifecycle.py           # Restore, save, close, quit
    │   ├── proxy_dialog.py            # Proxy settings dialog
    │   ├── rules_dialog.py            # Rules manager dialog
    │   ├── splash.py                  # Splash screen
    │   ├── table_model.py             # Download table model
    │   ├── update_dialog.py           # Update dialog
    │   ├── widgets.py                 # Reusable widgets (DropOverlay)
    │   └── youtube_progress.py        # YouTube progress dialog
    ├── utils/                         # Utilities
    │   ├── __init__.py
    │   ├── helpers.py                 # Helper functions
    │   ├── logger.py                  # Logging setup (file + UI)
    │   └── style.py                   # Theme styles
    ├── FelfelDM-extension/            # Browser extension
    │   ├── background.js
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

### Service crashes after update (`--add` fails with `QApplication failed`)

After updating the app or extension, the background service may still be running the **old code in memory**. When a new `--add` request arrives, it tries to construct a `QApplication` inside the service cgroup — where `DISPLAY` and `WAYLAND_DISPLAY` don't exist — and Qt aborts with `QApplication failed to initialize`.

**Fix:**

```bash
systemctl --user restart felfeldm.service
```

**Always run this after `FelfelDM --update` or `yay -Suy felfeldm-git` if you use the service.** The `.py` files on disk get replaced, but the running Python process doesn't re-import them.

### Permission denied: `/usr/share/felfeldm/main.py`

If `FelfelDM` fails with `Permission denied` after an install or update:

```bash
sudo find /usr/share/felfeldm -type f -exec chmod 644 {} \;
```

`main.py` and any other Python file should be readable by your user (`644`). If `ls -la /usr/share/felfeldm/` shows `-rw-------` for `main.py`, `README.md`, or `requirements.txt`, that's the bug — likely caused by `install -m 600` or `umask 077` in `PKGBUILD` / `install.sh`.

### aria2 keeps running after FelfelDM quits

In older versions this was expected — aria2 was daemonised and the app had no way to stop it.

In the current version, FelfelDM:

- starts aria2 in the foreground as its own child
- passes `--stop-with-process=<app_pid>` so aria2 exits when the app does
- cleans up explicitly via `SIGTERM` (then `SIGKILL` after 3 s) on quit

If aria2 still survives, check that the app isn't being killed with `SIGKILL` on the *parent shell* (which would bypass Python's cleanup). Even then, `--stop-with-process` should make aria2 exit within a second or two. You can confirm with:

```bash
pgrep -a aria2c
```

If the leftover `aria2c` was **not** started by FelfelDM (no `--conf-path=~/.config/felfelDM/aria2.conf`), it's not ours and FelfelDM will deliberately not touch it. Stop it yourself.

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
3. Transient errors (timeout, DNS, connection, TLS packet, 5xx) are retried with the configured delay
4. The Status column shows the countdown: `🔄 Retrying in 5s... (2/5)`
5. **Reset Retries After** controls when the failed-attempt counter resets to 0 (0 = never)
6. Pausing the queue (or clicking Start again) also resets the counters — so a queue paused overnight won't stay blocked after you restart it

### Rules not being applied

1. Check that the rule is **enabled** in Settings → Download Rules
2. Rules are evaluated **top-to-bottom**; the first match wins — make sure no earlier rule matches first
3. Rules only apply to **new downloads** — downloads already in progress are not affected
4. Check the console for `🎯 [Rules] '<name>' matched for ...` messages
5. If the rule has a regex, make sure it's valid (the dialog shows a live validation indicator)

### Rule speed limit not working

1. Rule speed limit **overrides** queue speed limit — if both are set, the rule's value wins
2. Make sure the rule is matched (check `[rule: ...]` badge next to the download name)
3. Check the console for `⚡ [SpeedLimit]` messages

### Speed limit not being applied

1. **Per-Download Speed Limit overrides Queue and Global** — if a download has its own limit, the others are ignored
2. **Queue Speed Limit overrides Global** — if a queue has its own limit, the global one is ignored
3. The Queue Speed Limit is **split across active downloads** (e.g. 100 KB/s ÷ 3 active downloads = ~33 KB/s each)
4. Restart the download after changing speed limits to ensure the new limit is applied
5. Check the console for `⚡ [SpeedLimit]` messages

### Per-download speed limit not working

1. Open the download's progress dialog and go to the **Speed Limit** tab
2. Set the limit and click **Apply**
3. The badge next to the speed shows the active per-download limit
4. Set to `0` to fall back to the queue's speed limit
5. Check the console for `⚡ [SpeedLimit]` messages

### File size shows as unknown

1. Some servers don't return size via HEAD or RANGE requests
2. The file will still download, but size won't be shown before downloading
3. Try a different server or download the file and check the size afterward

### Duplicate URL not being added

This is expected behavior for the same queue — FelfelDM will not add the same URL twice to the **same** queue. If you want a second copy:

- Add it to a **different** queue (allowed, with a notification)
- Or remove the existing one first, then add it again

Cross-queue duplicates are intentionally allowed and reported in the notification, so the behavior is never silent.

### UI freezes when removing files

This has been fixed in the latest version. Update FelfelDM to get the fix.

### Unrelated files got deleted when removing a download

1. This was a bug in older versions — fixed in the latest version
2. Update FelfelDM to get the fix
3. The delete operation now shows a confirmation dialog listing exactly which files will be removed, and only files matching the download (by name or gid) are included

### Wrong file size (e.g., 3.00 GB for all files)

1. This may happen if an incorrect size was cached earlier
2. Update FelfelDM to the latest version — new sizes are fetched from the server
3. If the issue persists, delete the cache files in `~/.config/felfelDM/` and restart

### Where are the logs?

FelfelDM writes logs to `~/.cache/felfelDM/logs/app.log`. You can open a live view from **View → Show Logs** or press **`Ctrl+L`** without leaving the app.

The log file rotates automatically to keep it small.

To send logs for a bug report, open the log window and copy the relevant lines, or attach the `app.log` file directly.

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