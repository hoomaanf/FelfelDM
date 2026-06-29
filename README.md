# =============================================================================
# README.md
# =============================================================================
# FelfelDM

**FelfelDM** is a modern, feature-rich download manager for Linux and Windows, built with Python and PyQt6. It leverages the powerful `aria2` as its backend, providing high-speed multi-connection downloads, torrent support, scheduling, and a beautiful user interface.

## Key Features

- 🚀 **High-speed downloads** – uses `aria2` with multi-connection and split support.
- 📋 **Queue scheduling** – schedule downloads for specific dates, times, or days.
- 🔍 **Search & filter** – quickly find downloads by name.
- 🌙 **Dark/Light theme** – automatically adapts to your system theme.
- 🖥️ **Browser extension** – integrate with your browser to send downloads directly.
- ⚙️ **Speed limiting** – set global download/upload limits.
- 💾 **Persistent storage** – downloads and queues are saved and restored across sessions.
- 🧩 **Modular codebase** – built with separation of concerns and testability in mind.

## Requirements

- Python 3.10 or higher
- `aria2` installed on your system (`sudo apt install aria2` on Debian/Ubuntu, or download from https://aria2.github.io/)
- PyQt6 and other Python dependencies (see `requirements.txt`)

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/hoomaanf/FelfelDM.git
   cd FelfelDM
   git checkout v3.0.0   # or latest stable branch
