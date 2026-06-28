#!/bin/bash

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║     🔨  FelfelDM - Build & Install                        ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

# مطمئن بشیم venv وجود داره
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}📦 Creating venv...${NC}"
    python3 -m venv venv
fi

# نصب همه دپندنسی‌ها توی venv
echo -e "${YELLOW}📦 Installing dependencies in venv...${NC}"
venv/bin/pip install -r requirements.txt
venv/bin/pip install pyinstaller

echo -e "${YELLOW}🧹 Cleaning previous builds...${NC}"
sudo rm -rf build dist __pycache__ *.spec

echo -e "${YELLOW}🔨 Building with PyInstaller from venv...${NC}"

PYTHON_VERSION=$(venv/bin/python -c "import sys; print(f'python{sys.version_info.major}.{sys.version_info.minor}')")
SITE_PACKAGES="venv/lib/${PYTHON_VERSION}/site-packages"

echo -e "${BLUE}Using: venv/bin/python (${PYTHON_VERSION})${NC}"
echo -e "${BLUE}Site-packages: ${SITE_PACKAGES}${NC}"

venv/bin/python -m PyInstaller \
    --onefile \
    --windowed \
    --name FelfelDM \
    --icon=logo/icon256.png \
    --paths="${SITE_PACKAGES}" \
    --add-data "logo:logo" \
    --add-data "icons:icons" \
    --add-data "ui:ui" \
    --add-data "core:core" \
    --add-data "utils:utils" \
    --hidden-import=PyQt6.QtCore \
    --hidden-import=PyQt6.QtGui \
    --hidden-import=PyQt6.QtWidgets \
    --hidden-import=PyQt6.QtNetwork \
    --hidden-import=requests \
    --hidden-import=appdirs \
    --hidden-import=keyring \
    --hidden-import=jeepney \
    --hidden-import=secretstorage \
    main.py 2>&1 | grep -v "already satisfies"

if [ ! -f "dist/FelfelDM" ]; then
    echo -e "${RED}❌ Build failed!${NC}"
    exit 1
fi

SIZE=$(du -h dist/FelfelDM | cut -f1)
echo -e "${GREEN}✅ Build complete!${NC}"
echo -e "📁 File: ${GREEN}dist/FelfelDM${NC}"
echo -e "📊 Size: ${GREEN}$SIZE${NC}"
echo ""

read -p "Install FelfelDM to system? (y/N): " install_it

if [[ "$install_it" =~ ^[Yy]$ ]]; then

    echo -e "${YELLOW}📦 Installing executable...${NC}"
    sudo cp dist/FelfelDM /usr/local/bin/
    sudo chmod +x /usr/local/bin/FelfelDM
    echo -e "${GREEN}✅ Installed to /usr/local/bin/FelfelDM${NC}"
    echo ""

    echo -e "${YELLOW}🎨 Installing icons...${NC}"
    sudo mkdir -p /usr/share/icons/hicolor/{256x256,128x128,64x64,48x48,32x32,16x16}/apps

    sudo cp logo/icon256.png /usr/share/icons/hicolor/256x256/apps/felfeldm.png
    sudo cp logo/icon128.png /usr/share/icons/hicolor/128x128/apps/felfeldm.png 2>/dev/null || true
    sudo cp logo/icon64.png /usr/share/icons/hicolor/64x64/apps/felfeldm.png 2>/dev/null || true
    sudo cp logo/icon48.png /usr/share/icons/hicolor/48x48/apps/felfeldm.png 2>/dev/null || true
    sudo cp logo/icon32.png /usr/share/icons/hicolor/32x32/apps/felfeldm.png 2>/dev/null || true
    sudo cp logo/icon16.png /usr/share/icons/hicolor/16x16/apps/felfeldm.png 2>/dev/null || true
    sudo cp logo/icon256.png /usr/share/pixmaps/felfeldm.png 2>/dev/null || true

    if command -v gtk-update-icon-cache &> /dev/null; then
        sudo gtk-update-icon-cache -f /usr/share/icons/hicolor 2>/dev/null || true
    fi
    echo -e "${GREEN}✅ Icons installed!${NC}"
    echo ""

    echo -e "${YELLOW}📁 Creating desktop entry...${NC}"
    cat << 'DESKTOP' | sudo tee /usr/share/applications/felfeldm.desktop > /dev/null
[Desktop Entry]
Version=1.0.0
Type=Application
Name=FelfelDM
Comment=Modern Download Manager
Exec=FelfelDM
Icon=felfeldm
Terminal=false
StartupNotify=true
Categories=Network;FileTransfer;
Keywords=download;manager;aria2;
StartupWMClass=FelfelDM
MimeType=x-scheme-handler/magnet;
DESKTOP

    mkdir -p ~/.local/share/applications
    cat << 'DESKTOP' > ~/.local/share/applications/felfeldm.desktop
[Desktop Entry]
Version=1.0.0
Type=Application
Name=FelfelDM
Comment=Modern Download Manager
Exec=/usr/local/bin/FelfelDM
Icon=felfeldm
Terminal=false
StartupNotify=true
Categories=Network;FileTransfer;
Keywords=download;manager;aria2;
StartupWMClass=FelfelDM
MimeType=x-scheme-handler/magnet;
DESKTOP

    if command -v update-desktop-database &> /dev/null; then
        sudo update-desktop-database /usr/share/applications/ 2>/dev/null || true
        update-desktop-database ~/.local/share/applications/ 2>/dev/null || true
    fi
    echo -e "${GREEN}✅ Desktop entry created!${NC}"

    echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║           ✅  Installation Complete!                       ║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "  🚀  Run: ${GREEN}FelfelDM${NC}"
    echo ""

else
    echo -e "${YELLOW}⏭️  Skipping installation.${NC}"
    echo -e "You can run: ${GREEN}./dist/FelfelDM${NC}"
fi

echo -e "${GREEN}🌶️  Enjoy FelfelDM!${NC}"