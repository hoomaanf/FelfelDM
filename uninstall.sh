#!/bin/bash
set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║     🗑️  FelfelDM - Uninstaller                               ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

read -p "Are you sure you want to uninstall FelfelDM? (y/N): " confirm

if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo -e "${GREEN}Uninstall cancelled.${NC}"
    exit 0
fi

# ============================================
# 1. Stop and remove systemd service
# ============================================
echo -e "${YELLOW}🗑️  Removing systemd service...${NC}"

# Kill any running processes
pkill -9 -f "main.py --daemon" 2>/dev/null || true
pkill -9 -f "FelfelDM --daemon" 2>/dev/null || true

# Stop and disable service
systemctl --user stop felfeldm.service 2>/dev/null || true
systemctl --user disable felfeldm.service 2>/dev/null || true

# Remove service file
rm -f ~/.config/systemd/user/felfeldm.service

# Reload systemd
systemctl --user daemon-reload 2>/dev/null || true
systemctl --user reset-failed 2>/dev/null || true

echo -e "${GREEN}✅ Service removed${NC}"
echo ""

# ============================================
# 2. Remove executable and files
# ============================================
echo -e "${YELLOW}🗑️  Removing executable and files...${NC}"

sudo rm -f /usr/local/bin/FelfelDM
sudo rm -rf /usr/share/felfeldm

echo -e "${GREEN}✅ Files removed${NC}"
echo ""

# ============================================
# 3. Remove desktop entry and icons
# ============================================
echo -e "${YELLOW}🗑️  Removing desktop entry and icons...${NC}"

sudo rm -f /usr/share/applications/felfeldm.desktop
sudo rm -f /usr/share/icons/hicolor/*/apps/felfeldm.png
sudo rm -f ~/.local/share/applications/felfeldm.desktop
sudo rm -f ~/Desktop/felfeldm.desktop

update-desktop-database ~/.local/share/applications/ 2>/dev/null || true
gtk-update-icon-cache -f /usr/share/icons/hicolor 2>/dev/null || true

echo -e "${GREEN}✅ Desktop entries removed${NC}"
echo ""

# ============================================
# 4. Remove config
# ============================================
CONFIG_DIR="$HOME/.config/felfelDM"
if [ -d "$CONFIG_DIR" ]; then
    read -p "Remove configuration and download history (~/.config/felfelDM)? (y/N): " remove_config
    if [[ "$remove_config" =~ ^[Yy]$ ]]; then
        rm -rf "$CONFIG_DIR"
        echo -e "${GREEN}✅ Configuration folder removed.${NC}"
    else
        echo -e "${YELLOW}⏭️  Configuration folder kept.${NC}"
    fi
fi

echo ""

# ============================================
# 5. Remove from PATH (bashrc/zshrc)
# ============================================
echo -e "${YELLOW}🗑️  Cleaning PATH...${NC}"

if [ -f "$HOME/.bashrc" ]; then
    sed -i '/export PATH="$HOME\/.local\/bin:$PATH"/d' "$HOME/.bashrc" 2>/dev/null || true
fi

if [ -f "$HOME/.zshrc" ]; then
    sed -i '/export PATH="$HOME\/.local\/bin:$PATH"/d' "$HOME/.zshrc" 2>/dev/null || true
fi

echo -e "${GREEN}✅ PATH cleaned${NC}"
echo ""

# ============================================
# 6. Optional: Remove Python packages
# ============================================
echo -e "${YELLOW}📦 Remove Python packages?${NC}"
read -p "Remove PyQt6, requests, yt-dlp, keyring, appdirs? (y/N): " remove_packages

if [[ "$remove_packages" =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}Removing packages...${NC}"
    pip uninstall -y PyQt6 requests yt-dlp keyring appdirs websocket-client 2>/dev/null || true
    echo -e "${GREEN}✅ Packages removed${NC}"
else
    echo -e "${YELLOW}⏭️  Packages kept${NC}"
fi

echo ""

# ============================================
# 7. Final message
# ============================================
echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║           ✅  FelfelDM Uninstalled!                          ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}📝 Note:${NC}"
echo "  - Your downloads folder is untouched"
echo "  - aria2 is still installed on your system"
echo "  - Configuration kept at: ~/.config/felfelDM (if not removed)"
echo ""
echo -e "${GREEN}Thanks for using FelfelDM! 🌶️${NC}"