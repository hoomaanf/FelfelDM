#!/bin/bash
set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║     🗑️  FelfelDM - Uninstaller (Complete)                    ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

read -p "Are you sure you want to completely uninstall FelfelDM? (y/N): " confirm

if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo -e "${GREEN}Uninstall cancelled.${NC}"
    exit 0
fi

# ============================================
# 0. Stop FelfelDM processes
# ============================================
# Match only the installed entry points. A bare `pkill -f "main.py"` (the
# previous behaviour) SIGKILLs ANY python program whose script happens to
# be named main.py - e.g. an unrelated local web server - which loses the
# user's unsaved work.
echo -e "${YELLOW}🛑 Stopping FelfelDM processes...${NC}"
for pattern in \
    "/usr/share/felfeldm/main.py" \
    "/usr/local/share/felfeldm/main.py" \
    "/usr/bin/FelfelDM" \
    "/usr/local/bin/FelfelDM"
do
    pkill -f "$pattern" 2>/dev/null || true
done
# SIGTERM first; only force-kill FelfelDM's own aria2 if it lingers.
sleep 1
for pattern in \
    "/usr/share/felfeldm/main.py" \
    "/usr/local/share/felfeldm/main.py" \
    "/usr/bin/FelfelDM" \
    "/usr/local/bin/FelfelDM"
do
    pkill -9 -f "$pattern" 2>/dev/null || true
done
echo -e "${GREEN}✅ Done${NC}"
echo ""

# ============================================
# 1. Remove AUR package
# ============================================
echo -e "${YELLOW}🗑️  Removing AUR package...${NC}"

if pacman -Q felfeldm-git &>/dev/null; then
    sudo pacman -Rsn felfeldm-git --noconfirm 2>/dev/null || true
    echo -e "${GREEN}✅ AUR package removed${NC}"
else
    echo -e "${YELLOW}⏭️  AUR package not installed${NC}"
fi
echo ""

# ============================================
# 2. Remove systemd service
# ============================================
echo -e "${YELLOW}🗑️  Removing systemd service...${NC}"

systemctl --user stop felfeldm.service 2>/dev/null || true
systemctl --user disable felfeldm.service 2>/dev/null || true
rm -f ~/.config/systemd/user/felfeldm.service
systemctl --user daemon-reload 2>/dev/null || true
systemctl --user reset-failed 2>/dev/null || true

echo -e "${GREEN}✅ Service removed${NC}"
echo ""

# ============================================
# 3. Remove all executable files
# ============================================
echo -e "${YELLOW}🗑️  Removing executables...${NC}"

# Remove from all possible locations
sudo rm -f /usr/local/bin/FelfelDM
sudo rm -f /usr/bin/FelfelDM
sudo rm -f /usr/local/bin/felfeldm
sudo rm -f /usr/bin/felfeldm
sudo rm -f ~/.local/bin/FelfelDM
sudo rm -f ~/.local/bin/felfeldm

echo -e "${GREEN}✅ Executables removed${NC}"
echo ""

# ============================================
# 4. Remove application files
# ============================================
echo -e "${YELLOW}🗑️  Removing application files...${NC}"

# Main application directory
sudo rm -rf /usr/share/felfeldm
sudo rm -rf /usr/local/share/felfeldm
sudo rm -rf ~/.local/share/felfeldm

# Any other possible locations
sudo rm -rf /opt/felfeldm

echo -e "${GREEN}✅ Application files removed${NC}"
echo ""

# ============================================
# 5. Remove desktop entries
# ============================================
echo -e "${YELLOW}🗑️  Removing desktop entries...${NC}"

sudo rm -f /usr/share/applications/felfeldm.desktop
sudo rm -f ~/.local/share/applications/felfeldm.desktop
sudo rm -f ~/Desktop/felfeldm.desktop
sudo rm -f /usr/share/applications/felfeldm-git.desktop

# Update desktop database
update-desktop-database ~/.local/share/applications/ 2>/dev/null || true
update-desktop-database /usr/share/applications/ 2>/dev/null || true

echo -e "${GREEN}✅ Desktop entries removed${NC}"
echo ""

# ============================================
# 6. Remove icons
# ============================================
echo -e "${YELLOW}🗑️  Removing icons...${NC}"

# Remove from all icon locations
sudo rm -f /usr/share/pixmaps/felfeldm.png
sudo rm -f /usr/share/icons/hicolor/*/apps/felfeldm.png
sudo rm -f ~/.local/share/icons/hicolor/*/apps/felfeldm.png
sudo find /usr/share/icons -name "felfeldm.png" -delete 2>/dev/null || true
sudo find ~/.local/share/icons -name "felfeldm.png" -delete 2>/dev/null || true

# Update icon cache
gtk-update-icon-cache -f /usr/share/icons/hicolor 2>/dev/null || true
gtk-update-icon-cache -f ~/.local/share/icons/hicolor 2>/dev/null || true

echo -e "${GREEN}✅ Icons removed${NC}"
echo ""

# ============================================
# 7. Remove configuration and data
# ============================================
# The queue list and download history live here, so this is the one step
# that destroys user data. Ask explicitly and default to keeping it.
echo -e "${YELLOW}🗑️  Configuration and data${NC}"
echo "  Location: ~/.config/felfelDM (queues, rules, proxies, history)"
read -p "Delete your FelfelDM settings and download history? (y/N): " remove_config

if [[ "$remove_config" =~ ^[Yy]$ ]]; then
    rm -rf ~/.config/felfelDM
    echo -e "${GREEN}✅ Configuration and data removed${NC}"
else
    rm -rf ~/.cache/felfelDM
    rm -rf ~/.cache/yay/felfeldm-git
    rm -rf ~/.local/share/felfelDM
    echo -e "${YELLOW}⏭️  Configuration kept at ~/.config/felfelDM${NC}"
fi

# Stale temp files from the updater, always safe to drop.
rm -f /tmp/felfeldm_install.sh
rm -f /tmp/felfeldm_update.sh

echo ""

# ============================================
# 8. Remove from PATH
# ============================================
echo -e "${YELLOW}🗑️  Cleaning PATH...${NC}"

# Remove from .bashrc
if [ -f "$HOME/.bashrc" ]; then
    sed -i '/export PATH="\$HOME\/.local\/bin:\$PATH"/d' "$HOME/.bashrc" 2>/dev/null || true
    sed -i '/export PATH="\/usr\/local\/bin:\$PATH"/d' "$HOME/.bashrc" 2>/dev/null || true
    sed -i '/# FelfelDM/d' "$HOME/.bashrc" 2>/dev/null || true
fi

# Remove from .zshrc
if [ -f "$HOME/.zshrc" ]; then
    sed -i '/export PATH="\$HOME\/.local\/bin:\$PATH"/d' "$HOME/.zshrc" 2>/dev/null || true
    sed -i '/export PATH="\/usr\/local\/bin:\$PATH"/d' "$HOME/.zshrc" 2>/dev/null || true
    sed -i '/# FelfelDM/d' "$HOME/.zshrc" 2>/dev/null || true
fi

# Remove from .profile
if [ -f "$HOME/.profile" ]; then
    sed -i '/export PATH="\$HOME\/.local\/bin:\$PATH"/d' "$HOME/.profile" 2>/dev/null || true
    sed -i '/# FelfelDM/d' "$HOME/.profile" 2>/dev/null || true
fi

echo -e "${GREEN}✅ PATH cleaned${NC}"
echo ""

# ============================================
# 9. Optional: Remove Python packages
# ============================================
# PyQt6, requests, cryptography and keyring are general-purpose libraries
# that other applications depend on. Removing them (and especially
# `pacman -Rsn`, which also deletes their dependency chain) can break
# unrelated software, so this is opt-in, non-recursive, and only touches
# the packages FelfelDM itself needs.
echo -e "${YELLOW}📦 Remove Python packages that FelfelDM depends on?${NC}"
echo -e "${RED}⚠️  PyQt6, requests, cryptography and keyring may be used by other${NC}"
echo -e "${RED}    applications on this system. Only do this if you are sure.${NC}"
read -p "Remove PyQt6, requests, yt-dlp, keyring, appdirs? (y/N): " remove_packages

if [[ "$remove_packages" =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}Removing packages...${NC}"

    # --user only: never touch system site-packages from an uninstaller.
    pip3 uninstall -y --user PyQt6 requests yt-dlp keyring appdirs 2>/dev/null || true

    if command -v pacman >/dev/null 2>&1; then
        # -R without -s: no cascading removal of shared dependencies.
        sudo pacman -R --noconfirm python-pyqt6 python-requests yt-dlp 2>/dev/null || true
    fi

    echo -e "${GREEN}✅ Packages removed${NC}"
    echo -e "${YELLOW}ℹ️  aria2 was left installed (it is a standalone tool).${NC}"
else
    echo -e "${YELLOW}⏭️  Packages kept${NC}"
fi

echo ""

# ============================================
# 10. Final message
# ============================================
echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║           ✅  FelfelDM Completely Uninstalled!              ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}📝 Note:${NC}"
echo "  - Your downloads folder (~/Downloads) is untouched"
echo "  - aria2 is still installed (it is a standalone tool, not bundled here)"
echo "  - FelfelDM application files, caches and desktop entries were removed"
echo ""
echo -e "${GREEN}Thanks for using FelfelDM! 🌶️${NC}"