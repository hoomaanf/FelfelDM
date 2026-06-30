# 🌶️ FelfelDM

<div align="center">
  <img src="logo/icon256.png" alt="FelfelDM Logo" width="180">
  <h2>A Modern Download Manager for Linux</h2>

  <p>
    <img src="https://img.shields.io/badge/Python-3.10%2B-blue?style=for-the-badge&logo=python" alt="Python">
    <img src="https://img.shields.io/badge/PyQt6-6.11-blue?style=for-the-badge&logo=qt" alt="PyQt6">
    <img src="https://img.shields.io/badge/aria2-1.37-blue?style=for-the-badge&logo=aria2" alt="aria2">
    <img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License">
  </p>
</div>

---

## ✨ Features

### Core Features
- **Multiple Queues** — Create and manage multiple download queues
- **Scheduled Downloads** — Set time windows for automatic downloads
- **Real-time Progress** — Live download speed and progress tracking
- **Smart Management** — Auto-retry, pause/resume, and error handling
- **Safe Removal** — Remove from list or delete files permanently

### Advanced Features
- **Browser Extension** — Firefox & Chrome extension for one-click downloads
- **aria2 Integration** — High-performance multi-connection downloads
- **Modern UI** — Dark theme with Papirus icons
- **Speed Limit** — Global download speed limiting
- **System Tray** — Minimize to tray with status indicator
- **Download Interception** — Catch browser downloads automatically

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

## 🚀 Usage

### Running the Application
```bash
FelfelDM
```

### Adding Downloads
1. Click **Add** button or press `Ctrl+N`
2. Enter URLs (one per line)
3. Select queue and options
4. Click OK

### Keyboard Shortcuts
| Shortcut | Action |
|----------|--------|
| `Ctrl+N` | Add downloads |
| `Ctrl+Q` | Quit application |
| `Ctrl+,` | Open settings |
| `F5`     | Refresh table |

---

## 🌐 Browser Extension

The `FelfelDM-extension` folder contains:
- `install.sh` — Auto install script
- `manifest-firefox.json` & `manifest-chrome.json`

### Install Extension
```bash
cd FelfelDM-extension
./install.sh
```

---

## 📁 Project Structure

```bash
FelfelDM/
├── core/                    # Core modules (aria2, worker, ...)
├── ui/                      # UI components
├── utils/                   # Utilities
├── FelfelDM-extension/      # Browser extension
├── logo/ & icons/           # Icons
├── main.py                  # Entry point
├── install.sh               # Installation
├── uninstall.sh             # Uninstallation
└── requirements.txt
```

---

## 🐛 Troubleshooting

**aria2 not found:**
```bash
sudo pacman -S aria2    # Arch
```

**Extension not connecting:**
1. Make sure FelfelDM is running
2. Test: `curl http://localhost:8765/ping`

---

<div align="center">
  <sub>Built with ❤️ and 🌶️</sub><br>
  <sub>© 2026 FelfelDM Contributors</sub>
</div>

---
