#!/bin/bash
set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║     🗑️  FelfelDM Uninstaller                              ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

echo -e "${YELLOW}⚠️  This will remove FelfelDM and all its data!${NC}"
echo ""
read -p "Are you sure? (y/N): " confirm

if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo -e "${GREEN}Uninstall cancelled.${NC}"
    exit 0
fi

echo ""

echo -e "${YELLOW}🗑️  Removing executable...${NC}"

if [ -f "/usr/local/bin/FelfelDM" ]; then
    sudo rm -f /usr/local/bin/FelfelDM
    echo -e "${GREEN}✅ Removed: /usr/local/bin/FelfelDM${NC}"
fi

if [ -f "$HOME/.local/bin/felfeldm" ]; then
    rm -f "$HOME/.local/bin/felfeldm"
    echo -e "${GREEN}✅ Removed: $HOME/.local/bin/felfeldm${NC}"
fi

echo -e "${YELLOW}🗑️  Removing icons...${NC}"

sudo rm -f /usr/share/icons/hicolor/256x256/apps/felfeldm.png
sudo rm -f /usr/share/icons/hicolor/128x128/apps/felfeldm.png
sudo rm -f /usr/share/icons/hicolor/64x64/apps/felfeldm.png
sudo rm -f /usr/share/icons/hicolor/48x48/apps/felfeldm.png
sudo rm -f /usr/share/icons/hicolor/32x32/apps/felfeldm.png
sudo rm -f /usr/share/icons/hicolor/16x16/apps/felfeldm.png
sudo rm -f /usr/share/pixmaps/felfeldm.png

rm -f "$HOME/.local/share/icons/hicolor/256x256/apps/felfeldm.png"
rm -f "$HOME/.local/share/icons/hicolor/128x128/apps/felfeldm.png"
rm -f "$HOME/.local/share/icons/hicolor/64x64/apps/felfeldm.png"
rm -f "$HOME/.local/share/icons/hicolor/48x48/apps/felfeldm.png"
rm -f "$HOME/.local/share/icons/hicolor/32x32/apps/felfeldm.png"
rm -f "$HOME/.local/share/icons/hicolor/16x16/apps/felfeldm.png"
rm -f "$HOME/.local/share/pixmaps/felfeldm.png"

if command -v gtk-update-icon-cache &> /dev/null; then
    sudo gtk-update-icon-cache -f /usr/share/icons/hicolor 2>/dev/null || true
    gtk-update-icon-cache -f "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
fi

echo -e "${GREEN}✅ Icons removed${NC}"

echo -e "${YELLOW}🗑️  Removing desktop entries...${NC}"

sudo rm -f /usr/share/applications/felfeldm.desktop
rm -f "$HOME/.local/share/applications/felfeldm.desktop"
rm -f "$HOME/Desktop/felfeldm.desktop"

if command -v update-desktop-database &> /dev/null; then
    sudo update-desktop-database /usr/share/applications/ 2>/dev/null || true
    update-desktop-database "$HOME/.local/share/applications/" 2>/dev/null || true
fi

echo -e "${GREEN}✅ Desktop entries removed${NC}"

echo -e "${YELLOW}🗑️  Removing program files...${NC}"

if [ -d "$HOME/.local/share/felfeldm" ]; then
    rm -rf "$HOME/.local/share/felfeldm"
    echo -e "${GREEN}✅ Removed: $HOME/.local/share/felfeldm${NC}"
fi

if [ -d "$HOME/FelfelDM" ]; then
    rm -rf "$HOME/FelfelDM"
    echo -e "${GREEN}✅ Removed: $HOME/FelfelDM${NC}"
fi

echo ""
echo -e "${YELLOW}🗑️  Removing user data...${NC}"

CONFIG_DIR="$HOME/.config/dlmanager"
if [ -d "$CONFIG_DIR" ]; then
    read -p "Remove configuration and download history? (y/N): " remove_config
    if [[ "$remove_config" =~ ^[Yy]$ ]]; then
        rm -rf "$CONFIG_DIR"
        echo -e "${GREEN}✅ Removed: $CONFIG_DIR${NC}"
    else
        echo -e "${YELLOW}⏭️  Skipped: $CONFIG_DIR${NC}"
    fi
fi

echo ""
echo -e "${YELLOW}🔄 Cleaning PATH...${NC}"

if [ -f "$HOME/.bashrc" ]; then
    sed -i '/export PATH="$HOME\/.local\/bin:$PATH"/d' "$HOME/.bashrc"
    sed -i '/export PATH="\/usr\/local\/bin:$PATH"/d' "$HOME/.bashrc"
    echo -e "${GREEN}✅ Updated: .bashrc${NC}"
fi

if [ -f "$HOME/.zshrc" ]; then
    sed -i '/export PATH="$HOME\/.local\/bin:$PATH"/d' "$HOME/.zshrc"
    sed -i '/export PATH="\/usr\/local\/bin:$PATH"/d' "$HOME/.zshrc"
    echo -e "${GREEN}✅ Updated: .zshrc${NC}"
fi

echo ""
echo -e "${YELLOW}📦 Optional: Remove Python packages...${NC}"
read -p "Remove PyQt6 and requests? (y/N): " remove_packages

if [[ "$remove_packages" =~ ^[Yy]$ ]]; then
    pip uninstall -y PyQt6 requests 2>/dev/null || true
    pip uninstall -y pyinstaller nuitka 2>/dev/null || true
    echo -e "${GREEN}✅ Packages removed${NC}"
fi

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║           ✅  FelfelDM Uninstalled!                        ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}📝 Note:${NC}"
echo "  - Your downloads folder is untouched"
echo "  - aria2 is still installed (remove with: sudo pacman -R aria2)"
echo ""
echo -e "${GREEN}Thanks for using FelfelDM! 🌶️${NC}"