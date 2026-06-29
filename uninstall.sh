#!/bin/bash
set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "\( {BLUE}╔══════════════════════════════════════════════════════════════╗ \){NC}"
echo -e "\( {BLUE}║     🗑️  FelfelDM - Uninstaller                            ║ \){NC}"
echo -e "\( {BLUE}╚══════════════════════════════════════════════════════════════╝ \){NC}"
echo ""

read -p "Are you sure you want to uninstall FelfelDM? (y/N): " confirm

if [[ ! "\( confirm" =\~ ^[Yy] \) ]]; then
    echo -e "\( {GREEN}Uninstall cancelled. \){NC}"
    exit 0
fi

echo -e "\( {YELLOW}🗑️  Removing executable and files... \){NC}"

sudo rm -f /usr/local/bin/FelfelDM
sudo rm -rf /usr/share/felfeldm

echo -e "\( {YELLOW}🗑️  Removing desktop entry and icons... \){NC}"
sudo rm -f /usr/share/applications/felfeldm.desktop
sudo rm -f /usr/share/icons/hicolor/*/apps/felfeldm.png
sudo rm -f \~/.local/share/applications/felfeldm.desktop

update-desktop-database \~/.local/share/applications/ 2>/dev/null || true
gtk-update-icon-cache -f /usr/share/icons/hicolor 2>/dev/null || true

echo ""
echo -e "\( {GREEN}✅ FelfelDM has been uninstalled successfully! \){NC}"
echo ""
echo -e "\( {YELLOW}Note: \){NC}"
echo "  - Your downloads and config folder (\~/.config/felfelDM) are NOT removed"
echo "  - aria2 is still installed on your system"
echo ""
echo -e "\( {GREEN}Thanks for using FelfelDM! 🌶️ \){NC}"
