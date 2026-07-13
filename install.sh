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
# Detect distribution by package manager
# ============================================
detect_distro() {
    if command -v pacman &> /dev/null; then
        echo "arch"
    elif command -v apt &> /dev/null || command -v apt-get &> /dev/null; then
        echo "debian"
    elif command -v dnf &> /dev/null; then
        echo "fedora"
    elif command -v yum &> /dev/null; then
        echo "rhel"
    elif command -v zypper &> /dev/null; then
        echo "opensuse"
    elif command -v apk &> /dev/null; then
        echo "alpine"
    else
        echo "unknown"
    fi
}

DISTRO=$(detect_distro)

echo -e "${YELLOW}Detected package manager: $DISTRO${NC}"
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
    
    if ! command -v git &> /dev/null; then
        echo -e "${RED}❌ git not found. Installing...${NC}"
        case "$DISTRO" in
            arch)   $SUDO pacman -S --needed git --noconfirm ;;
            debian) $SUDO apt update && $SUDO apt install -y git ;;
            fedora|rhel) $SUDO dnf install -y git ;;
            opensuse) $SUDO zypper install -y git ;;
            alpine) $SUDO apk add git ;;
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
    arch)
        echo -e "${GREEN}Installing with pacman...${NC}"
        $SUDO pacman -Sy --needed \
            python \
            python-pip \
            python-pyqt6 \
            aria2 \
            git \
            papirus-icon-theme \
            yt-dlp \
            --noconfirm
        ;;
        
    debian)
        echo -e "${GREEN}Installing with apt...${NC}"
        $SUDO apt update
        $SUDO apt install -y \
            python3 \
            python3-pip \
            python3-pyqt6 \
            aria2 \
            git \
            papirus-icon-theme \
            yt-dlp
        ;;
        
    fedora)
        echo -e "${GREEN}Installing with dnf...${NC}"
        
        echo -e "${YELLOW}Enabling RPM Fusion for extra packages...${NC}"
        $SUDO dnf install -y \
            https://download1.rpmfusion.org/free/fedora/rpmfusion-free-release-$(rpm -E %fedora).noarch.rpm \
            https://download1.rpmfusion.org/nonfree/fedora/rpmfusion-nonfree-release-$(rpm -E %fedora).noarch.rpm 2>/dev/null || true
        
        $SUDO dnf install -y \
            python3 \
            python3-pip \
            python3-pyqt6 \
            python3-pyqt6-devel \
            aria2 \
            git \
            yt-dlp \
            papirus-icon-theme
        
        if ! rpm -q papirus-icon-theme &> /dev/null; then
            echo -e "${YELLOW}⚠ papirus-icon-theme not found, installing from pip...${NC}"
            pip3 install --user papirus-icon-theme 2>/dev/null || echo -e "${YELLOW}⚠ Could not install papirus-icon-theme${NC}"
        fi
        ;;
        
    rhel)
        echo -e "${GREEN}Installing with yum...${NC}"
        $SUDO yum install -y \
            python3 \
            python3-pip \
            aria2 \
            git
        echo -e "${YELLOW}⚠ papirus-icon-theme not available${NC}"
        echo -e "${YELLOW}⚠ yt-dlp not available, installing via pip${NC}"
        ;;
        
    opensuse)
        echo -e "${GREEN}Installing with zypper...${NC}"
        $SUDO zypper install -y \
            python3 \
            python3-pip \
            python3-qt6 \
            aria2 \
            git \
            yt-dlp
        ;;
        
    alpine)
        echo -e "${GREEN}Installing with apk...${NC}"
        $SUDO apk add \
            python3 \
            py3-pip \
            py3-pyqt6 \
            aria2 \
            git \
            yt-dlp
        ;;
        
    *)
        echo -e "${RED}❌ No supported package manager found!${NC}"
        echo "Please install dependencies manually:"
        echo "  - Python 3.10+"
        echo "  - PyQt6"
        echo "  - aria2"
        echo "  - git"
        echo "  - yt-dlp"
        exit 1
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
        if [ "$DISTRO" = "arch" ]; then
            pip3 install --break-system-packages "$pkg" 2>/dev/null || pip3 install --user "$pkg"
        else
            pip3 install --user "$pkg" 2>/dev/null || $SUDO pip3 install "$pkg"
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

$SUDO cp -r \
    "$SOURCE_DIR"/core \
    "$SOURCE_DIR"/ui \
    "$SOURCE_DIR"/utils \
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

[ -f "$SOURCE_DIR/logo/icon512.png" ] && $SUDO cp "$SOURCE_DIR/logo/icon512.png" /usr/share/icons/hicolor/256x256/apps/felfeldm.png
[ -f "$SOURCE_DIR/logo/icon512.png" ] && $SUDO cp "$SOURCE_DIR/logo/icon512.png" /usr/share/pixmaps/felfeldm.png

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
# Test
# ============================================
echo ""
echo -e "${YELLOW}🔍 Testing installation...${NC}"

if command -v FelfelDM >/dev/null; then
    echo -e "${GREEN}✅ Command 'FelfelDM' is available${NC}"
else
    echo -e "${RED}❌ Command 'FelfelDM' not found in PATH${NC}"
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