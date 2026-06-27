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

if [ -d "venv" ]; then
    echo -e "${YELLOW}📦 Activating venv...${NC}"
    source venv/bin/activate
fi

export PATH="$HOME/.local/bin:$PATH"

echo -e "${YELLOW}📦 Installing PyInstaller...${NC}"

if ! command -v pyinstaller &> /dev/null; then
    if [ -d "venv" ]; then
        pip install pyinstaller
    else
        pip install --user --break-system-packages pyinstaller
    fi
fi

echo -e "${YELLOW}🧹 Cleaning previous builds...${NC}"
sudo rm -rf build dist __pycache__ *.spec

echo -e "${YELLOW}🔨 Building with PyInstaller...${NC}"

PYINSTALLER_BIN="pyinstaller"
if [ -f "venv/bin/pyinstaller" ]; then
    PYINSTALLER_BIN="venv/bin/pyinstaller"
fi

$PYINSTALLER_BIN \
    --onefile \
    --windowed \
    --name FelfelDM \
    --icon=logo/icon256.png \
    --add-data "logo:logo" \
    --add-data "icons:icons" \
    --add-data "ui:ui" \
    --add-data "core:core" \
    --add-data "utils:utils" \
    --exclude-module PyQt6.QtWebEngineCore \
    --exclude-module PyQt6.QtWebEngineWidgets \
    --exclude-module PyQt6.Qt3DCore \
    --exclude-module PyQt6.QtQuick \
    --exclude-module PyQt6.QtNetworkWidgets \
    --exclude-module PyQt6.QtBluetooth \
    --hidden-import=PyQt6.QtCore \
    --hidden-import=PyQt6.QtGui \
    --hidden-import=PyQt6.QtWidgets \
    --hidden-import=PyQt6.QtNetwork \
    --hidden-import=requests \
    --hidden-import=appdirs \
    --hidden-import=keyring \
    --hidden-import=jeepney \
    --hidden-import=secretstorage \
    main.py 2>&1 | grep -v "WARNING:" | grep -v "already satisfies"

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
    sudo mkdir -p /usr/share/icons/hicolor/256x256/apps
    sudo mkdir -p /usr/share/icons/hicolor/128x128/apps
    sudo mkdir -p /usr/share/icons/hicolor/64x64/apps
    sudo mkdir -p /usr/share/icons/hicolor/48x48/apps
    sudo mkdir -p /usr/share/icons/hicolor/32x32/apps
    sudo mkdir -p /usr/share/icons/hicolor/16x16/apps

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
    
    # استفاده از tee به همراه sudo برای حل مشکل Permission Denied
    cat << 'EOF' | sudo tee /usr/share/applications/felfeldm.desktop > /dev/null
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
EOF

    mkdir -p ~/.local/share/applications
    cat << 'EOF' > ~/.local/share/applications/felfeldm.desktop
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
EOF

    if command -v update-desktop-database &> /dev/null; then
        sudo update-desktop-database /usr/share/applications/ 2>/dev/null || true
        update-desktop-database ~/.local/share/applications/ 2>/dev/null || true
    fi
    echo -e "${GREEN}✅ Desktop entry created!${NC}"
    echo ""

    echo -e "${YELLOW}📁 Creating desktop shortcut...${NC}"
    read -p "Create desktop shortcut? (y/N): " create_shortcut
    if [[ "$create_shortcut" =~ ^[Yy]$ ]]; then
        cat > ~/Desktop/felfeldm.desktop << EOF
[Desktop Entry]
Version=1.0.0
Type=Application
Name=FelfelDM
Comment=Modern Download Manager
Exec=/usr/local/bin/FelfelDM
Icon=/usr/share/icons/hicolor/256x256/apps/felfeldm.png
Terminal=false
StartupNotify=true
Categories=Network;FileTransfer;
EOF
        chmod +x ~/Desktop/felfeldm.desktop
        echo -e "${GREEN}✅ Desktop shortcut created!${NC}"
    fi
    echo ""

    if ! echo "$PATH" | grep -q "/usr/local/bin"; then
        echo 'export PATH="/usr/local/bin:$PATH"' >> ~/.bashrc
        echo 'export PATH="/usr/local/bin:$PATH"' >> ~/.zshrc 2>/dev/null || true
    fi

    echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║           ✅  Installation Complete!                       ║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${BLUE}📋 Installation Summary:${NC}"
    echo ""
    echo -e "  🚀  Command:     ${GREEN}FelfelDM${NC}"
    echo -e "  📁  Location:    ${GREEN}/usr/local/bin/FelfelDM${NC}"
    echo -e "  🎨  Icon:        ${GREEN}/usr/share/icons/hicolor/256x256/apps/felfeldm.png${NC}"
    echo -e "  📂  Desktop:     ${GREEN}FelfelDM${NC} in application menu"
    echo ""
    echo -e "${YELLOW}📖 How to run:${NC}"
    echo ""
    echo -e "  ${GREEN}1. From terminal:${NC}"
    echo "     FelfelDM"
    echo ""
    echo -e "  ${GREEN}2. From application menu:${NC}"
    echo "     Search for 'FelfelDM'"
    echo ""
    echo -e "  ${GREEN}3. From desktop:${NC}"
    echo "     Double-click the FelfelDM icon"
    echo ""

else
    echo -e "${YELLOW}⏭️  Skipping installation.${NC}"
    echo -e "You can run: ${GREEN}./dist/FelfelDM${NC}"
fi

echo -e "${GREEN}🌶️  Enjoy FelfelDM!${NC}"

if [ -d "venv" ]; then
    deactivate 2>/dev/null || true
fi