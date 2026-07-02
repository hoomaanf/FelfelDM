#!/usr/bin/env bash
set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

APP_NAME="FelfelDM"
INSTALL_DIR="/usr/share/felfeldm"

echo -e "${BLUE}"
echo "=================================================="
echo "        $APP_NAME Installer"
echo "=================================================="
echo -e "${NC}"

if [ "$EUID" -ne 0 ]; then
    echo "Restarting with sudo..."
    exec sudo bash "$0" "$@"
fi

if [ -f /etc/arch-release ]; then
    DISTRO="arch"
elif [ -f /etc/fedora-release ]; then
    DISTRO="fedora"
elif [ -f /etc/debian_version ]; then
    DISTRO="debian"
else
    DISTRO="unknown"
fi

echo -e "${YELLOW}Detected: $DISTRO${NC}"

case "$DISTRO" in

arch)

pacman -Sy --needed \
python \
python-pip \
python-requests \
python-keyring \
aria2 \
git \
papirus-icon-theme \
python-pyqt6

;;

debian)

apt update

apt install -y \
python3 \
python3-pip \
python3-requests \
python3-keyring \
python3-pyqt6 \
aria2 \
git \
papirus-icon-theme

;;

fedora)

dnf install -y \
python3 \
python3-pip \
python3-requests \
python3-keyring \
python3-qt6 \
aria2 \
git \
papirus-icon-theme

;;

*)

echo -e "${RED}Unsupported distribution.${NC}"
exit 1

;;

esac

echo
echo -e "${GREEN}Installing application...${NC}"

rm -rf "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR"

cp main.py "$INSTALL_DIR"

cp -r \
core \
ui \
utils \
icons \
logo \
FelfelDM-extension \
"$INSTALL_DIR"

[ -f README.md ] && cp README.md "$INSTALL_DIR"
[ -f requirements.txt ] && cp requirements.txt "$INSTALL_DIR"

if ! python3 -c "import appdirs" >/dev/null 2>&1; then
    echo
    echo "Installing missing Python package: appdirs"
    pip3 install appdirs
fi

cat >/usr/local/bin/FelfelDM <<EOF
#!/bin/sh
exec python3 /usr/share/felfeldm/main.py "\$@"
EOF

chmod +x /usr/local/bin/FelfelDM"

mkdir -p /usr/share/icons/hicolor/256x256/apps
mkdir -p /usr/share/icons/hicolor/128x128/apps
mkdir -p /usr/share/icons/hicolor/64x64/apps

cp logo/icon256.png /usr/share/icons/hicolor/256x256/apps/felfeldm.png
cp logo/icon128.png /usr/share/icons/hicolor/128x128/apps/felfeldm.png
cp logo/icon64.png /usr/share/icons/hicolor/64x64/apps/felfeldm.png

cat >/usr/share/applications/felfeldm.desktop <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=FelfelDM
Comment=Modern Download Manager
Exec=FelfelDM
Icon=felfeldm
Terminal=false
Categories=Network;Utility;
MimeType=x-scheme-handler/magnet;
StartupWMClass=FelfelDM
EOF

command -v update-desktop-database >/dev/null && \
update-desktop-database /usr/share/applications

command -v gtk-update-icon-cache >/dev/null && \
gtk-update-icon-cache -f /usr/share/icons/hicolor

echo
echo -e "${GREEN}====================================${NC}"
echo -e "${GREEN} Installation completed successfully${NC}"
echo -e "${GREEN}====================================${NC}"
echo
echo "Run:"
echo
echo "    FelfelDM"
echo