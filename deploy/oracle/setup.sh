#!/usr/bin/env bash
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()   { echo -e "${RED}[ERROR]${NC} $*"; }

REPO_URL="https://github.com/dinesh-choudhary123/Facebook-.git"
APP_DIR="$HOME/restaurant-social-automation"
APP_USER="$USER"
APP_PORT=8000
DOMAIN=""

if [[ $EUID -eq 0 ]]; then
    err "Do NOT run this script as root."
    exit 1
fi

info "Starting Oracle Cloud VM setup..."

sudo apt-get update -qq
sudo apt-get install -y -qq python3 python3-pip python3-venv git curl wget tesseract-ocr libgl1 libglib2.0-0 nginx certbot python3-certbot-nginx build-essential ffmpeg libsm6 libxext6 2>&1 | tail -3
ok "System dependencies installed"

if [[ -d "$APP_DIR" ]]; then
    cd "$APP_DIR" && git pull
else
    git clone "$REPO_URL" "$APP_DIR"
    cd "$APP_DIR"
fi
ok "Repository ready"

python3 -m venv venv 2>/dev/null || true
source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q
pip install "uvicorn[standard]" gunicorn -q
ok "Python deps installed"

mkdir -p static/uploads static/outputs logs

if [[ ! -f ".env" ]]; then
    [[ -f ".env.example" ]] && cp .env.example .env || warn "No .env found"
fi

SERVICE_FILE="/etc/systemd/system/restaurant-social-automation.service"
sudo tee "$SERVICE_FILE" > /dev/null << SERVICEEOF
[Unit]
Description=Restaurant Social Automation API
After=network.target

[Service]
Type=simple
User=$APP_USER
WorkingDirectory=$APP_DIR
Environment=PATH=$APP_DIR/venv/bin:/usr/bin:/bin
ExecStart=$APP_DIR/venv/bin/uvicorn api.app:app --host 0.0.0.0 --port $APP_PORT --workers 2
Restart=always
RestartSec=5
StandardOutput=append:$APP_DIR/logs/app.log
StandardError=append:$APP_DIR/logs/app.log

[Install]
WantedBy=multi-user.target
SERVICEEOF

sudo systemctl daemon-reload
sudo systemctl enable restaurant-social-automation
sudo systemctl start restaurant-social-automation
ok "Service started"

sleep 3
if curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:$APP_PORT/" 2>/dev/null | grep -q 200; then
    PUBLIC_IP=$(curl -s ifconfig.me 2>/dev/null || echo "<IP>")
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  ✅ DEPLOYMENT SUCCESSFUL!${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo -e "  Public:   http://$PUBLIC_IP:$APP_PORT"
    echo -e "  Logs:     tail -f $APP_DIR/logs/app.log"
else
    err "Check logs: sudo journalctl -u restaurant-social-automation -n 50"
fi
