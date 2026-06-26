# 🌶️ FelfelDM

<div align="center">
  <img src="logo/icon128.png" alt="FelfelDM Logo" width="128" height="128">
  <br>
  <strong>A Modern Download Manager for Linux</strong>
  <br>
  <br>
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&logo=python" alt="Python">
  <img src="https://img.shields.io/badge/PyQt6-6.8%2B-blue?style=flat-square&logo=qt" alt="PyQt6">
  <img src="https://img.shields.io/badge/aria2-1.37%2B-blue?style=flat-square&logo=aria2" alt="aria2">
  <img src="https://img.shields.io/badge/License-MIT-green?style=flat-square" alt="License">
  <br>
  <img src="https://img.shields.io/badge/Platform-Linux-FCC624?style=flat-square&logo=linux" alt="Platform">
  <img src="https://img.shields.io/badge/Status-Active-success?style=flat-square" alt="Status">
  <br>
  <img src="https://img.shields.io/badge/Firefox-FF7139?style=flat-square&logo=firefox" alt="Firefox">
  <img src="https://img.shields.io/badge/Chrome-4285F4?style=flat-square&logo=google-chrome" alt="Chrome">
</div>

---

## 📋 Table of Contents
- [Features](#-features)
- [Installation](#-installation)
  - [Quick Install](#quick-install)
  - [Manual Install](#manual-install)
  - [Uninstall](#uninstall)
- [Usage](#-usage)
- [Browser Extension](#-browser-extension)
- [Building from Source](#-building-from-source)
- [Configuration](#-configuration)
- [Contributing](#-contributing)
- [License](#-license)

---

## ✨ Features

### Core Features
- 🚀 **Multiple Queues** - Create and manage multiple download queues
- ⏰ **Scheduled Downloads** - Set time windows for automatic downloads
- 📊 **Real-time Progress** - Live download speed and progress tracking
- 🎯 **Smart Management** - Auto-retry, pause/resume, and error handling
- 🗑️ **Safe Removal** - Remove from list or delete files permanently

### Advanced Features
- 🌐 **Browser Extension** - Firefox/Chrome extension for one-click downloads
- 🔌 **aria2 Integration** - High-performance multi-connection downloads
- 🎨 **Modern UI** - Dark theme with Papirus icons
- ⚡ **Speed Limit** - Global download speed limiting
- 🧹 **Auto Cleanup** - Auto-remove completed downloads
- 🖥️ **System Tray** - Minimize to tray with status indicator
- 🔄 **Download Interception** - Catch browser downloads automatically

---

## 🛠️ Installation

### Prerequisites
```bash
# Arch Linux
sudo pacman -S python python-pip aria2 git

# Debian/Ubuntu
sudo apt update
sudo apt install python3 python3-pip aria2 git

# Fedora
sudo dnf install python3 python3-pip aria2 git
```

### Quick Install

**One-line installation:**
```bash
bash <(curl -s https://raw.githubusercontent.com/hoomaanf/FelfelDM/main/build_and_install.sh)
```

**Or manually:**
```bash
# 1. Clone the repository
git clone https://github.com/hoomaanf/FelfelDM.git
cd FelfelDM

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run
python3 main.py
```

### Uninstall

```bash
bash <(curl -s https://raw.githubusercontent.com/hoomaanf/FelfelDM/main/uninstall.sh)
```

---

## 🚀 Usage

### Running the Application
```bash
# From terminal
python3 main.py

# Or after installation
FelfelDM
```

### Adding Downloads
1. Click **Add** button or press `Ctrl+N`
2. Enter URLs (one per line)
3. Select queue and options
4. Click OK

### Managing Queues
- **Start/Pause**: Control entire queues
- **Schedule**: Set time windows for downloads
- **Priority**: Create queues for different categories

### Download Controls
- **Pause/Resume**: Individual download control
- **Remove**: From list or delete files
- **Clear Completed**: Remove finished downloads

### Keyboard Shortcuts
| Shortcut | Action |
|----------|--------|
| `Ctrl+N` | Add downloads |
| `Ctrl+Q` | Quit application |
| `Ctrl+,` | Open settings |
| `F5` | Refresh table |

---

## 🌐 Browser Extension

### Features
- 📥 **One-click Download** - Add current page to FelfelDM
- 🖱️ **Context Menu** - Right-click links, images, videos
- 🔗 **Selected Links** - Download multiple links from selection
- 🎯 **Download Interception** - Auto-catch browser downloads
- 🔔 **Notifications** - Status updates and confirmations

### Installation

#### Firefox
1. Open `about:debugging`
2. Click **This Firefox**
3. Click **Load Temporary Add-on**
4. Select `FelfelDM-extension/manifest-firefox.json`

#### Chrome/Chromium
1. Open `chrome://extensions/`
2. Enable **Developer mode**
3. Click **Load unpacked**
4. Select `FelfelDM-extension` folder

---

## 🔧 Building from Source

### With PyInstaller
```bash
# Install dependencies
pip install pyinstaller

# Build
pyinstaller --onefile --windowed --name FelfelDM --icon=logo/icon256.png --add-data "logo:logo" --add-data "icons:icons" --add-data "ui:ui" --add-data "core:core" --add-data "utils:utils" --hidden-import=PyQt6 --collect-all PyQt6 main.py

# Run
./dist/FelfelDM
```

### With Nuitka
```bash
# Install Nuitka
pip install nuitka

# Build
python -m nuitka --standalone --onefile --enable-plugin=pyqt6 --include-package=PyQt6 --include-data-dir=logo=logo --include-data-dir=icons=icons --include-data-dir=ui=ui --include-data-dir=core=core --include-data-dir=utils=utils --linux-onefile-icon=logo/icon256.png --lto=yes --output-dir=dist_nuitka --output-filename=FelfelDM main.py

# Run
./dist_nuitka/FelfelDM
```

---

## ⚙️ Configuration

### Application Settings
- **aria2 RPC**: Host, port, and secret key
- **Download Options**: Max concurrent, retry attempts
- **Speed Limit**: Global download speed limit
- **Auto Cleanup**: Auto-remove completed downloads

### Queue Settings
- **Save Path**: Custom download directory
- **Max Concurrent**: Maximum parallel downloads
- **Schedule**: Time windows and days

### Configuration File
Location: `~/.config/dlmanager/data.json`

---

## 📁 Project Structure

```
FelfelDM/
├── core/              # Core modules
│   ├── aria2_rpc.py   # aria2 RPC client
│   ├── data_store.py  # Data persistence
│   ├── queue_model.py # Queue model
│   └── worker.py      # Background worker
├── ui/                # UI components
│   ├── main_window.py # Main window
│   ├── dialogs.py     # Dialog windows
│   ├── table_model.py # Table model
│   └── delegates.py   # Custom delegates
├── utils/             # Utilities
│   ├── helpers.py     # Helper functions
│   └── style.py       # UI styling
├── icons/             # Application icons
├── logo/              # Logo files
├── FelfelDM-extension/ # Browser extension
├── main.py            # Entry point
├── requirements.txt   # Python dependencies
├── install.sh         # Installation script
└── uninstall.sh       # Uninstallation script
```

---

## 🐛 Troubleshooting

### aria2 not found
```bash
# Arch
sudo pacman -S aria2

# Debian/Ubuntu
sudo apt install aria2
```

### Module not found
```bash
pip install -r requirements.txt
```

### Extension not connecting
1. Make sure FelfelDM is running
2. Check local server: `curl http://localhost:8765/ping`
3. Restart the application

### Permission denied
```bash
chmod +x main.py
```

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing`)
5. Open a Pull Request

---

## 📄 License

MIT License - see [LICENSE](LICENSE) file for details

---

## 🙏 Acknowledgments

- [aria2](https://aria2.github.io/) - High-speed download utility
- [PyQt6](https://www.riverbankcomputing.com/software/pyqt/) - Python bindings for Qt6
- [Papirus](https://github.com/PapirusDevelopmentTeam/papirus-icon-theme) - Icon theme

---

## 📞 Support

- 🐛 **Issues**: [GitHub Issues](https://github.com/hoomaanf/FelfelDM/issues)
- 💬 **Discussions**: [GitHub Discussions](https://github.com/hoomaanf/FelfelDM/discussions)

---

<div align="center">
  <sub>Built with ❤️ and 🌶️</sub>
  <br>
  <sub>© 2026 FelfelDM Contributors</sub>
</div>
```
