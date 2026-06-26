#!/bin/bash

echo "🌶️ FelfelDM Extension Installer"
echo "================================"
echo ""
echo "Which browser are you using?"
echo "1) Firefox"
echo "2) Chrome/Chromium"
echo "3) Brave/Edge/Opera (Chromium-based)"
echo ""
read -p "Enter choice [1-3]: " choice

case $choice in
  1)
    echo "📦 Preparing for Firefox..."
    cp manifest-firefox.json manifest.json
    echo ""
    echo "✅ Ready for Firefox!"
    echo ""
    echo "📖 Installation steps:"
    echo "1. Open Firefox"
    echo "2. Go to about:debugging"
    echo "3. Click 'This Firefox'"
    echo "4. Click 'Load Temporary Add-on'"
    echo "5. Select: $(pwd)/manifest.json"
    ;;
  2|3)
    echo "📦 Preparing for Chromium-based browser..."
    cp manifest-chrome.json manifest.json
    echo ""
    echo "✅ Ready for Chrome/Chromium!"
    echo ""
    echo "📖 Installation steps:"
    echo "1. Open your browser"
    echo "2. Go to chrome://extensions/"
    echo "3. Enable 'Developer mode'"
    echo "4. Click 'Load unpacked'"
    echo "5. Select folder: $(pwd)"
    ;;
  *)
    echo "❌ Invalid choice!"
    exit 1
    ;;
esac

echo ""
echo "🌶️ FelfelDM extension is ready!"