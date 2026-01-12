#!/bin/bash
# CineRecord Build Script for Mac
# Creates a standalone .app bundle

set -e

echo "🔧 CineRecord Build Script"
echo "=========================="

# Check if PyInstaller is installed
if ! pip show pyinstaller &> /dev/null; then
    echo "📦 Installing PyInstaller..."
    pip install pyinstaller
fi

# Clean previous builds
echo "🧹 Cleaning previous builds..."
rm -rf build dist

# Build the application
echo "🏗️ Building CineRecord..."
PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    PYTHON_BIN=python
fi
"$PYTHON_BIN" -m PyInstaller CineRecord.spec --clean --noconfirm

echo ""
echo "✅ Build complete!"
echo ""
echo "📁 Output: dist/CineRecord.app"
echo ""
echo "To run: open dist/CineRecord.app"
echo ""
echo "💡 Tip: You can also copy the .app to your Applications folder"
