#!/bin/bash
# DataWarden2 - Start Script
# Activates venv, runs app, deactivates venv on exit

set -e

# Default venv directory
VENV_DIR=".venv"
CONFIG_FILE="config/paths.conf"

# Load custom venv path if config exists
if [ -f "$CONFIG_FILE" ]; then
    source "$CONFIG_FILE"
fi

VENV_PATH="$VENV_DIR"

# Check if venv exists
if [ ! -d "$VENV_PATH" ]; then
    echo "❌ Virtual Environment nicht gefunden: $VENV_PATH"
    echo "   Führe zuerst ./setup.sh aus"
    exit 1
fi

echo "🚀 DataWarden2 wird gestartet..."
echo "   Venv: $VENV_PATH"

# Activate venv
source "$VENV_PATH/bin/activate"

# Show Python info (debug)
echo "   Python: $(which python)"
python -c "import textual; print(f'   Textual: {textual.__version__}')" 2>/dev/null || echo "   Textual: nicht installiert"

# Run main application
python main.py

# Capture exit code
EXIT_CODE=$?

# Deactivate venv
deactivate

echo ""
echo "👋 DataWarden2 beendet (Exit Code: $EXIT_CODE)"
exit $EXIT_CODE