#!/bin/bash
echo "================================"
echo "  POLY BOT - Local Server"
echo "================================"

# Install deps
pip install -r requirements.txt --quiet

# Get local IP (works Mac + Linux)
if [[ "$OSTYPE" == "darwin"* ]]; then
    LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "unknown")
else
    LOCAL_IP=$(hostname -I | awk '{print $1}')
fi

echo ""
echo " Server starting..."
echo " Local:    http://localhost:5000"
echo " Mobile:   http://$LOCAL_IP:5000"
echo ""
echo " (must be on same WiFi for mobile)"
echo " For external: ngrok http 5000"
echo ""

python app.py
