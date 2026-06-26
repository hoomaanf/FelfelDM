#!/bin/bash
set -e


GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}╔════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║     🌶️  FelfelDM Installer                    ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════╝${NC}"
echo ""

echo -e "${YELLOW}📋 Checking prerequisites...${NC}"

# Git
if ! command -v git &> /dev/null; then
    echo -e "${RED}❌ Git not found!${NC}"
    echo "Install git: sudo apt install git  or  sudo pacman -S git"
    exit 1
fi

# Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python3 not found!${NC}"
    exit 1
fi

# pip
if ! command -v pip &> /dev/null && ! command -v pip3 &> /dev/null; then
    echo -e "${RED}❌ pip not found!${NC}"
    exit 1
fi

# aria2
if ! command -v aria2c &> /dev/null; then
    echo -e "${YELLOW}⚠️  aria2 not found. Installing...${NC}"
    if command -v pacman &> /dev/null; then
        sudo pacman -S aria2 --noconfirm
    elif command -v apt &> /dev/null; then
        sudo apt update && sudo apt install aria2 -y
    else
        echo -e "${YELLOW}⚠️  Please install aria2 manually:${NC}"
        echo "  sudo apt install aria2  or  sudo pacman -S aria2"
    fi
fi

echo ""
echo -e "${YELLOW}📥 Cloning FelfelDM...${NC}"

INSTALL_DIR="$HOME/.local/share/felfeldm"

rm -rf "$INSTALL_DIR"

git clone https://github.com/hoomaanf/FelfelDM.git "$INSTALL_DIR"

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Failed to clone!${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Clone complete!${NC}"

echo ""
echo -e "${YELLOW}📦 Installing dependencies...${NC}"

cd "$INSTALL_DIR"

if [ -f "requirements.txt" ]; then
    pip install --user -r requirements.txt
else
    pip install --user PyQt6 requests
fi

echo -e "${GREEN}✅ Dependencies installed!${NC}"

echo ""
echo -e "${YELLOW}🚀 Creating launcher...${NC}"

mkdir -p "$HOME/.local/bin"

cat > "$HOME/.local/bin/felfeldm" << EOF
#!/bin/bash
cd "$INSTALL_DIR"
python3 main.py "\$@"
EOF

chmod +x "$HOME/.local/bin/felfeldm"

# اضافه کردن به PATH
if ! echo "$PATH" | grep -q "$HOME/.local/bin"; then
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.zshrc" 2>/dev/null || true
fi

echo -e "${GREEN}✅ Launcher created!${NC}"

echo ""
echo -e "${YELLOW}🎨 Installing icon...${NC}"

mkdir -p "$HOME/.local/share/icons/hicolor/256x256/apps"
cp "$INSTALL_DIR/logo/icon256.png" "$HOME/.local/share/icons/hicolor/256x256/apps/felfeldm.png"

if command -v gtk-update-icon-cache &> /dev/null; then
    gtk-update-icon-cache -f "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
fi

echo -e "${GREEN}✅ Icon installed!${NC}"

echo ""
echo -e "${YELLOW}📁 Creating desktop entry...${NC}"

mkdir -p "$HOME/.local/share/applications"

cat > "$HOME/.local/share/applications/felfeldm.desktop" << EOF
[Desktop Entry]
Version=1.0.0
Type=Application
Name=FelfelDM
Comment=Modern Download Manager
Exec=$HOME/.local/bin/felfeldm
Icon=felfeldm
Terminal=false
StartupNotify=true
Categories=Network;FileTransfer;
Keywords=download;manager;aria2;
StartupWMClass=FelfelDM
MimeType=x-scheme-handler/magnet;
EOF

if command -v update-desktop-database &> /dev/null; then
    update-desktop-database "$HOME/.local/share/applications/" 2>/dev/null || true
fi

echo -e "${GREEN}✅ Desktop entry created!${NC}"

echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║     ✅  Installation Complete!                ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${BLUE}📋 Installation Summary:${NC}"
echo ""
echo -e "  📁  Location:    $INSTALL_DIR"
echo -e "  🚀  Command:     ${GREEN}felfeldm${NC}"
echo -e "  📂  Desktop:     ${GREEN}FelfelDM${NC} in application menu"
echo ""
echo -e "${YELLOW}📖 How to run:${NC}"
echo ""
echo -e "  ${GREEN}1. From terminal:${NC}"
echo "     felfeldm"
echo ""
echo -e "  ${GREEN}2. From application menu:${NC}"
echo "     Search for 'FelfelDM'"
echo ""
echo -e "  ${GREEN}3. From desktop:${NC}"
echo "     Click the FelfelDM icon"
echo ""
echo -e "${GREEN}🌶️  Enjoy FelfelDM!${NC}"
