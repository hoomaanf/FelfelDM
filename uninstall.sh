#!/bin/bash
set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}╔════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║     🗑️  FelfelDM Uninstaller                  ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════╝${NC}"
echo ""

echo -e "${YELLOW}⚠️  This will remove FelfelDM and all its data!${NC}"
echo ""
read -p "Are you sure? (y/N): " confirm

if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo -e "${GREEN}Uninstall cancelled.${NC}"
    exit 0
fi

echo ""

echo -e "${YELLOW}🗑️  Removing program files...${NC}"

# پوشه برنامه
INSTALL_DIR="$HOME/.local/share/felfeldm"
if [ -d "$INSTALL_DIR" ]; then
    rm -rf "$INSTALL_DIR"
    echo -e "${GREEN}✅ Removed: $INSTALL_DIR${NC}"
fi

echo -e "${YELLOW}🗑️  Removing launcher...${NC}"

if [ -f "$HOME/.local/bin/felfeldm" ]; then
    rm -f "$HOME/.local/bin/felfeldm"
    echo -e "${GREEN}✅ Removed: $HOME/.local/bin/felfeldm${NC}"
fi

echo -e "${YELLOW}🗑️  Removing icons...${NC}"

ICON_PATHS=(
    "$HOME/.local/share/icons/hicolor/256x256/apps/felfeldm.png"
    "$HOME/.local/share/icons/hicolor/128x128/apps/felfeldm.png"
    "$HOME/.local/share/icons/hicolor/64x64/apps/felfeldm.png"
    "$HOME/.local/share/icons/hicolor/48x48/apps/felfeldm.png"
    "$HOME/.local/share/pixmaps/felfeldm.png"
)

for icon in "${ICON_PATHS[@]}"; do
    if [ -f "$icon" ]; then
        rm -f "$icon"
        echo -e "${GREEN}✅ Removed: $icon${NC}"
    fi
done

if command -v gtk-update-icon-cache &> /dev/null; then
    gtk-update-icon-cache -f "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
fi

echo -e "${YELLOW}🗑️  Removing desktop entry...${NC}"

DESKTOP_FILES=(
    "$HOME/.local/share/applications/felfeldm.desktop"
    "$HOME/Desktop/felfeldm.desktop"
    "/usr/share/applications/felfeldm.desktop"
)

for desktop in "${DESKTOP_FILES[@]}"; do
    if [ -f "$desktop" ]; then
        sudo rm -f "$desktop" 2>/dev/null || rm -f "$desktop"
        echo -e "${GREEN}✅ Removed: $desktop${NC}"
    fi
done

if command -v update-desktop-database &> /dev/null; then
    update-desktop-database "$HOME/.local/share/applications/" 2>/dev/null || true
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
echo -e "${YELLOW}📦 Optional: Remove Python packages...${NC}"
read -p "Remove PyQt6 and requests? (y/N): " remove_packages

if [[ "$remove_packages" =~ ^[Yy]$ ]]; then
    pip uninstall -y PyQt6 requests 2>/dev/null || true
    echo -e "${GREEN}✅ Packages removed${NC}"
fi

echo ""
echo -e "${YELLOW}🔄 Cleaning PATH...${NC}"

if [ -f "$HOME/.bashrc" ]; then
    sed -i '/export PATH="$HOME\/.local\/bin:$PATH"/d' "$HOME/.bashrc"
    echo -e "${GREEN}✅ Updated: .bashrc${NC}"
fi

if [ -f "$HOME/.zshrc" ]; then
    sed -i '/export PATH="$HOME\/.local\/bin:$PATH"/d' "$HOME/.zshrc"
    echo -e "${GREEN}✅ Updated: .zshrc${NC}"
fi

echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║     ✅  FelfelDM Uninstalled!                 ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}📝 Note:${NC}"
echo "  - Your downloads folder is untouched"
echo "  - aria2 is still installed (if you want to remove it: sudo pacman -R aria2)"
echo ""
echo -e "${GREEN}Thanks for using FelfelDM! 🌶️${NC}"