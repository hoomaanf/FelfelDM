#!/bin/bash
set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║     🔨  FelfelDM - System Package Installer                  ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

if [ -f /etc/arch-release ]; then
    DISTRO="arch"
elif [ -f /etc/debian_version ]; then
    DISTRO="debian"
elif [ -f /etc/fedora-release ]; then
    DISTRO="fedora"
else
    DISTRO="unknown"
fi

echo -e "${YELLOW}📦 Installing system dependencies...${NC}"

case $DISTRO in
    arch)
        sudo pacman -S --needed python python-pip aria2 git papirus-icon-theme
        ;;
    debian|ubuntu)
        sudo apt update
        sudo apt install -y python3 python3-pip python3-pyqt6 aria2 git papirus-icon-theme
        ;;
    fedora)
        sudo dnf install -y python3 python3-pip python3-qt6 aria2 git papirus-icon-theme
        ;;
    *)
        sudo apt update || true
        sudo apt install -y python3 python3-pip python3-pyqt6 aria2 git papirus-icon-theme || true
        sudo dnf install -y python3 python3-pip python3-qt6 aria2 git papirus-icon-theme || true
        sudo pacman -S --needed python python-pip aria2 git papirus-icon-theme || true
        ;;
esac

echo -e "${YELLOW}📦 Installing Python dependencies...${NC}"

if [ -f /etc/arch-release ]; then
    pip3 install --break-system-packages requests keyring appdirs
else
    pip3 install --user requests keyring appdirs
fi

INSTALL_DIR="/usr/share/felfeldm"
echo -e "${YELLOW}📁 Installing to ${INSTALL_DIR}...${NC}"
sudo rm -rf $INSTALL_DIR
sudo mkdir -p $INSTALL_DIR

sudo cp -r ./* $INSTALL_DIR/ 2>/dev/null || true
sudo cp -r core ui utils logo icons $INSTALL_DIR/ 2>/dev/null || true

echo -e "${YELLOW}🔧 Creating launcher...${NC}"
cat << 'EOF' | sudo tee /usr/local/bin/FelfelDM > /dev/null
#!/bin/bash
cd /usr/share/felfeldm
exec python3 main.py "$@"
EOF

sudo chmod +x /usr/local/bin/FelfelDM

echo -e "${YELLOW}🎨 Installing icons...${NC}"
sudo mkdir -p /usr/share/icons/hicolor/{256x256,128x128,64x64}/apps
sudo cp logo/icon256.png /usr/share/icons/hicolor/256x256/apps/felfeldm.png 2>/dev/null || true
sudo cp logo/icon128.png /usr/share/icons/hicolor/128x128/apps/felfeldm.png 2>/dev/null || true
sudo cp logo/icon64.png /usr/share/icons/hicolor/64x64/apps/felfeldm.png 2>/dev/null || true

echo -e "${YELLOW}📋 Creating desktop entry...${NC}"
cat << 'DESKTOP' | sudo tee /usr/share/applications/felfeldm.desktop > /dev/null
[Desktop Entry]
Version=1.0
Type=Application
Name=FelfelDM
Comment=Modern Download Manager for Linux
Exec=FelfelDM
Icon=felfeldm
Terminal=false
Categories=Network;FileTransfer;Utility;
Keywords=download;manager;aria2;felfel;
StartupWMClass=FelfelDM
MimeType=x-scheme-handler/magnet;
DESKTOP

update-desktop-database ~/.local/share/applications/ 2>/dev/null || true
gtk-update-icon-cache -f /usr/share/icons/hicolor 2>/dev/null || true

echo ""
echo -e "${GREEN}✅ Installation completed successfully!${NC}"
echo -e "🚀 Run with: ${GREEN}FelfelDM${NC}"
echo ""
echo -e "${GREEN}🌶️ Enjoy FelfelDM!${NC}"
