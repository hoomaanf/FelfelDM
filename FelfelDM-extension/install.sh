#!/bin/bash
set -euo pipefail

# Prepares a browser-specific manifest for FelfelDM.
#
# The generated manifest is written to a build/ directory instead of the
# source tree, so running this script never dirties the git working copy
# and the previous choice is never silently overwritten.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="$SCRIPT_DIR/build"

echo "🌶️ FelfelDM Extension Installer"
echo "================================"
echo ""
echo "Which browser are you using?"
echo "1) Firefox"
echo "2) Chrome/Chromium"
echo "3) Brave/Edge/Opera (Chromium-based)"
echo ""
read -r -p "Enter choice [1-3]: " choice

case "$choice" in
  1)
    SOURCE_MANIFEST="manifest-firefox.json"
    BROWSER_NAME="Firefox"
    LOAD_STEPS=$(cat <<'EOF'
1. Open Firefox
2. Go to about:debugging#/runtime/this-firefox
3. Click 'Load Temporary Add-on'
4. Select the manifest.json inside the build/ folder
EOF
)
    ;;
  2|3)
    SOURCE_MANIFEST="manifest-chrome.json"
    BROWSER_NAME="Chrome/Chromium"
    LOAD_STEPS=$(cat <<'EOF'
1. Open your browser
2. Go to chrome://extensions/
3. Enable 'Developer mode'
4. Click 'Load unpacked' and select the build/ folder
EOF
)
    ;;
  *)
    echo "❌ Invalid choice!" >&2
    exit 1
    ;;
esac

if [ ! -f "$SCRIPT_DIR/$SOURCE_MANIFEST" ]; then
  echo "❌ Missing $SOURCE_MANIFEST" >&2
  exit 1
fi

# Build a self-contained, loadable extension directory. Everything the
# manifest references must be copied, not just the manifest itself.
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"

cp "$SCRIPT_DIR/$SOURCE_MANIFEST" "$BUILD_DIR/manifest.json"
for asset in background.js popup.html popup.js icons; do
  if [ -e "$SCRIPT_DIR/$asset" ]; then
    cp -r "$SCRIPT_DIR/$asset" "$BUILD_DIR/"
  else
    echo "⚠️  Missing asset: $asset" >&2
  fi
done

echo ""
echo "✅ Prepared for $BROWSER_NAME"
echo ""
echo "📖 Installation steps:"
echo "$LOAD_STEPS"
echo ""
echo "📁 Extension folder: $BUILD_DIR"
echo ""
echo "🌶️ FelfelDM extension is ready!"