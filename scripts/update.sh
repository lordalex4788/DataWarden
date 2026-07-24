#!/bin/bash
# DataWarden2 - Update Script
# Pulls git updates and upgrades Python dependencies

set -e

VENV_DIR=".venv"
CONFIG_FILE="config/paths.conf"

# Load custom venv path if config exists
if [ -f "$CONFIG_FILE" ]; then
    source "$CONFIG_FILE"
fi

VENV_PATH="$VENV_DIR"

echo "🔄 DataWarden2 Update"
echo "===================="

# 1. Git Pull
echo "📥 Git Pull..."
if [ -d ".git" ]; then
    git pull origin main 2>/dev/null || git pull origin master 2>/dev/null || echo "   Kein Remote 'origin' konfiguriert - überspringe git pull"
else
    echo "   Kein Git-Repository gefunden - initialisiere..."
    git init
    git add .
    git commit -m "Initial commit" 2>/dev/null || true
fi

# 2. Check venv
if [ ! -d "$VENV_PATH" ]; then
    echo "❌ Virtual Environment nicht gefunden: $VENV_PATH"
    echo "   Führe zuerst ./setup.sh aus"
    exit 1
fi

# 3. Activate venv
source "$VENV_PATH/bin/activate"

# 4. Upgrade pip
echo "📦 Pip upgraden..."
pip install --upgrade pip

# 5. Upgrade dependencies
echo "📦 Dependencies aktualisieren..."
pip install --upgrade -r requirements.txt

# 6. Optional: Update pre-commit hooks
if [ -f ".pre-commit-config.yaml" ]; then
    echo "🔧 Pre-commit hooks aktualisieren..."
    pre-commit autoupdate
fi

deactivate

echo ""
echo "✅ Update erfolgreich abgeschlossen!"
echo "   Starte DataWarden2 mit: ./start.sh"