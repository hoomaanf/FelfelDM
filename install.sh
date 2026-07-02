#!/usr/bin/env bash
set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

APP_NAME="FelfelDM"
INSTALL_DIR="/usr/share/felfeldm"
REPO_URL="https://github.com/hoomaanf/FelfelDM.git"

echo -e "${BLUE}"
echo "=================================================="
echo "        $APP_NAME Installer"
echo "=================================================="
echo -e "${NC}"

# ============================================
# Check root
# ============================================
if [ "$EUID" -ne 0 ]; then
    SUDO="sudo"
else
    SUDO=""
fi

# ============================================
# Detect distribution
# ============================================
if [ -f /etc/os-release ]; then
    . /etc/os-release
    DISTRO="$ID"
elif [ -f /etc/arch-release ]; then
    DISTRO="arch"
elif [ -f /etc/fedora-release ]; then
    DISTRO="fedora"
elif [ -f /etc/debian_version ]; then
    DISTRO="debian"
elif [ -f /etc/redhat-release ]; then
    DISTRO="rhel"
else
    DISTRO="unknown"
fi

echo -e "${YELLOW}Detected: $DISTRO${NC}"
echo ""

# ============================================
# Check if running from git clone or standalone
# ============================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -f "$SCRIPT_DIR/main.py" ]; then
    echo -e "${GREEN}✓ Found local files in: $SCRIPT_DIR${NC}"
    SOURCE_DIR="$SCRIPT_DIR"
else
    echo -e "${YELLOW}⚠ Local files not found. Cloning from GitHub...${NC}"
    
    # Check git
    if ! command -v git &> /dev/null; then
        echo -e "${RED}❌ git not found. Installing...${NC}"
        case "$DISTRO" in
            arch)   $SUDO pacman -S --needed git --noconfirm ;;
            debian|ubuntu) $SUDO apt install -y git ;;
            fedora|rhel) $SUDO dnf install -y git ;;
            *) echo -e "${RED}Please install git manually${NC}"; exit 1 ;;
        esac
    fi
    
    TEMP_DIR=$(mktemp -d)
    echo -e "${YELLOW}📥 Cloning repository...${NC}"
    git clone --depth 1 "$REPO_URL" "$TEMP_DIR"
    SOURCE_DIR="$TEMP_DIR"
fi

# ============================================
# Install dependencies
# ============================================
echo -e "${YELLOW}📦 Installing dependencies...${NC}"
echo ""

case "$DISTRO" in
    arch|manjaro)
        $SUDO pacman -Sy --needed \
            python \
            python-pip \
            python-pyqt6 \
            aria2 \
            git \
            papirus-icon-theme \
            --noconfirm
        ;;
        
    debian|ubuntu|pop|linuxmint|elementary)
        $SUDO apt update
        $SUDO apt install -y \
            python3 \
            python3-pip \
            python3-pyqt6 \
            aria2 \
            git \
            papirus-icon-theme
        ;;
        
    fedora)
        $SUDO dnf install -y \
            python3 \
            python3-pip \
            python3-qt6 \
            aria2 \
            git \
            papirus-icon-theme
        ;;
        
    rhel|centos)
        $SUDO dnf install -y \
            python3 \
            python3-pip \
            aria2 \
            git
        # papirus-icon-theme maybe not available on RHEL
        echo -e "${YELLOW}⚠ papirus-icon-theme not available, using system icons${NC}"
        ;;
        
    opensuse*)
        $SUDO zypper install -y \
            python3 \
            python3-pip \
            python3-qt6 \
            aria2 \
            git
        ;;
        
    *)
        echo -e "${YELLOW}⚠ Unsupported distribution. Installing via pip...${NC}"
        $SUDO pip install -q PyQt6 requests
        ;;
esac

# ============================================
# Install required pip packages
# ============================================
echo -e "${YELLOW}📦 Installing pip packages...${NC}"

PIP_PACKAGES="requests keyring appdirs"

for pkg in $PIP_PACKAGES; do
    if ! python3 -c "import $pkg" >/dev/null 2>&1; then
        echo "Installing $pkg..."
        if [ "$DISTRO" = "arch" ] || [ "$DISTRO" = "manjaro" ]; then
            pip3 install --break-system-packages "$pkg"
        else
            pip3 install --user "$pkg"
        fi
    fi
done

# ============================================
# Install application
# ============================================
echo ""
echo -e "${GREEN}📁 Installing application...${NC}"

$SUDO rm -rf "$INSTALL_DIR"
$SUDO mkdir -p "$INSTALL_DIR"

# Copy all files
$SUDO cp -r \
    "$SOURCE_DIR"/core \
    "$SOURCE_DIR"/ui \
    "$SOURCE_DIR"/utils \
    "$SOURCE_DIR"/icons \
    "$SOURCE_DIR"/logo \
    "$SOURCE_DIR"/FelfelDM-extension \
    "$INSTALL_DIR" 2>/dev/null || true

[ -f "$SOURCE_DIR/main.py" ] && $SUDO cp "$SOURCE_DIR/main.py" "$INSTALL_DIR"
[ -f "$SOURCE_DIR/README.md" ] && $SUDO cp "$SOURCE_DIR/README.md" "$INSTALL_DIR"
[ -f "$SOURCE_DIR/requirements.txt" ] && $SUDO cp "$SOURCE_DIR/requirements.txt" "$INSTALL_DIR"

# ============================================
# Create launcher
# ============================================
cat <<'EOF' | $SUDO tee /usr/local/bin/FelfelDM >/dev/null
#!/bin/sh
exec python3 /usr/share/felfeldm/main.py "$@"
EOF

$SUDO chmod +x /usr/local/bin/FelfelDM

# ============================================
# Install icons
# ============================================
echo -e "${YELLOW}🎨 Installing icons...${NC}"

$SUDO mkdir -p /usr/share/icons/hicolor/{256x256,128x128,64x64,48x48,32x32,16x16}/apps

[ -f "$SOURCE_DIR/logo/icon256.png" ] && $SUDO cp "$SOURCE_DIR/logo/icon256.png" /usr/share/icons/hicolor/256x256/apps/felfeldm.png
[ -f "$SOURCE_DIR/logo/icon128.png" ] && $SUDO cp "$SOURCE_DIR/logo/icon128.png" /usr/share/icons/hicolor/128x128/apps/felfeldm.png
[ -f "$SOURCE_DIR/logo/icon64.png" ] && $SUDO cp "$SOURCE_DIR/logo/icon64.png" /usr/share/icons/hicolor/64x64/apps/felfeldm.png
[ -f "$SOURCE_DIR/logo/icon48.png" ] && $SUDO cp "$SOURCE_DIR/logo/icon48.png" /usr/share/icons/hicolor/48x48/apps/felfeldm.png
[ -f "$SOURCE_DIR/logo/icon32.png" ] && $SUDO cp "$SOURCE_DIR/logo/icon32.png" /usr/share/icons/hicolor/32x32/apps/felfeldm.png
[ -f "$SOURCE_DIR/logo/icon16.png" ] && $SUDO cp "$SOURCE_DIR/logo/icon16.png" /usr/share/icons/hicolor/16x16/apps/felfeldm.png

# Fallback for older systems
[ -f "$SOURCE_DIR/logo/icon256.png" ] && $SUDO cp "$SOURCE_DIR/logo/icon256.png" /usr/share/pixmaps/felfeldm.png

# ============================================
# Create desktop file
# ============================================
echo -e "${YELLOW}📁 Creating desktop entry...${NC}"

cat <<'EOF' | $SUDO tee /usr/share/applications/felfeldm.desktop >/dev/null
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

# ============================================
# Update caches
# ============================================
if command -v update-desktop-database >/dev/null; then
    $SUDO update-desktop-database /usr/share/applications 2>/dev/null || true
fi

if command -v gtk-update-icon-cache >/dev/null; then
    $SUDO gtk-update-icon-cache -f /usr/share/icons/hicolor 2>/dev/null || true
fi

# ============================================
# Cleanup
# ============================================
if [ -d "$TEMP_DIR" ] && [ "$SOURCE_DIR" = "$TEMP_DIR" ]; then
    rm -rf "$TEMP_DIR"
    echo -e "${GREEN}✓ Cleaned up temporary files${NC}"
fi

# ============================================
# Done
# ============================================
echo ""
echo -e "${GREEN}====================================${NC}"
echo -e "${GREEN} ✅ Installation completed successfully${NC}"
echo -e "${GREEN}====================================${NC}"
echo ""
echo -e "${YELLOW}📖 How to run:${NC}"
echo ""
echo -e "  ${GREEN}1. From terminal:${NC}"
echo "     FelfelDM"
echo ""
echo -e "  ${GREEN}2. From application menu:${NC}"
echo "     Search for 'FelfelDM'"
echo ""
echo -e "  ${GREEN}3. Browser extension:${NC}"
echo "     Found in: $INSTALL_DIR/FelfelDM-extension"
echo ""
echo -e "${GREEN}🌶️  Enjoy FelfelDM!${NC}"