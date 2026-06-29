#!/bin/bash
# Run this ONCE on Void Rig to bootstrap the server.
# Usage: bash setup_server.sh <OPENAI_API_KEY> <PINECONE_API_KEY>
set -e

OPENAI_KEY="${1:?Pass OpenAI key as arg 1}"
PINECONE_KEY="${2:?Pass Pinecone key as arg 2}"
REPO="https://github.com/Sekki-vi/warframe.git"
APP_DIR="/home/azureuser/warframe"

echo "=== [1/6] Installing system packages ==="
sudo apt-get update -qq
sudo apt-get install -y python3 python3-pip git curl

echo "=== [2/6] Cloning repo ==="
if [ -d "$APP_DIR" ]; then
    echo "Repo already exists, pulling..."
    cd "$APP_DIR" && git pull origin main
else
    git clone "$REPO" "$APP_DIR"
    cd "$APP_DIR"
fi

echo "=== [3/6] Installing Python dependencies ==="
pip3 install -r requirements.txt --break-system-packages -q

echo "=== [4/6] Writing .env ==="
cat > "$APP_DIR/.env" <<EOF
OPENAI_API_KEY=${OPENAI_KEY}
BACKEND_URL=http://localhost:8602
AGENT_PUBLIC_URL=http://localhost:8602
MANAGER_CHAT_MODEL=gpt-4o-mini
CHAT_MODEL=gpt-4o-mini
OPENAI_MODEL=gpt-4.1-mini
PINECONE_API_KEY=${PINECONE_KEY}
PINECONE_INDEX=warframe
PINECONE_NAMESPACE=warframe
EMBED_MODEL=text-embedding-3-small
EMBED_DIMENSIONS=1536
BATCH_SIZE=100
TOP_K=5
TEMPERATURE=0.3
MAX_HISTORY=20
EOF
chmod 600 "$APP_DIR/.env"

echo "=== [5/6] Installing systemd services ==="
sudo cp "$APP_DIR/deploy/warframe-manager.service" /etc/systemd/system/
sudo cp "$APP_DIR/deploy/warframe-ui.service"      /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable warframe-manager warframe-ui
sudo systemctl restart warframe-manager warframe-ui

echo "=== [6/6] Health check ==="
sleep 5
curl -sf http://localhost:8602/health && echo ""
echo "✓ Setup complete! Manager: http://$(curl -s ifconfig.me):8602  UI: http://$(curl -s ifconfig.me):8603"
