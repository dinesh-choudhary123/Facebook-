#!/usr/bin/env bash
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }

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
info "Installing core dependencies..."
sudo apt-get install -y python3 python3-pip python3-venv git curl wget tesseract-ocr libgl1 libglib2.0-0 build-essential ffmpeg libsm6 libxext6 || {
    err "Failed to install core dependencies. Check apt sources."
    exit 1
}
ok "Core dependencies installed"

if [[ -d "$APP_DIR" ]]; then
    cd "$APP_DIR" && git pull
else
    git clone "$REPO_URL" "$APP_DIR"
    cd "$APP_DIR"
fi
ok "Repository ready at $APP_DIR"

info "Setting up Python virtual environment..."
python3 -m venv venv 2>/dev/null || true
source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q
pip install "uvicorn[standard]" gunicorn -q || warn "Some optional packages failed"
ok "Python dependencies installed"

mkdir -p static/uploads static/outputs logs

if [[ ! -f ".env" ]]; then
    if [[ -f ".env.example" ]]; then
        cp .env.example .env
        warn "Created .env from .env.example — EDIT IT with your keys: nano $APP_DIR/.env"
    else
        warn "No .env found. Create one with your Facebook keys."
    fi
fi

SERVICE_FILE="/etc/systemd/system/restaurant-social-automation.service"
USERNAME="$APP_USER"
APP_DIR_ESCAPED="$APP_DIR"
sudo tee "$SERVICE_FILE" > /dev/null << SERVICEEOF
[Unit]
Description=Restaurant Social Automation API
After=network.target

[Service]
Type=simple
User=$USERNAME
Group=$USERNAME
WorkingDirectory=$APP_DIR_ESCAPED
Environment=PATH=$APP_DIR_ESCAPED/venv/bin:/usr/bin:/bin
Environment=PYTHONUNBUFFERED=1
ExecStart=$APP_DIR_ESCAPED/venv/bin/uvicorn api.app:app --host 0.0.0.0 --port $APP_PORT --workers 2 --proxy-headers --forwarded-allow-ips='*'
Restart=always
RestartSec=5
LimitNOFILE=65536
LimitNPROC=4096
StandardOutput=append:$APP_DIR_ESCAPED/logs/app.log
StandardError=append:$APP_DIR_ESCAPED/logs/app.log
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true
ReadWritePaths=$APP_DIR_ESCAPED

[Install]
WantedBy=multi-user.target
SERVICEEOF

sudo systemctl daemon-reload
sudo systemctl enable restaurant-social-automation
sudo systemctl start restaurant-social-automation
ok "systemd service created and started"

info "Configuring firewall..."
sudo apt-get install -y ufw 2>/dev/null || true
sudo ufw --force reset 2>/dev/null || true
sudo ufw default deny incoming 2>/dev/null || true
sudo ufw default allow outgoing 2>/dev/null || true
sudo ufw allow ssh 2>/dev/null || true
sudo ufw allow $APP_PORT/tcp 2>/dev/null || true
sudo ufw --force enable 2>/dev/null && ok "Firewall configured (port $APP_PORT open)" || warn "Could not enable ufw — check manually"

sleep 5
RETRIES=0
while [[ $RETRIES -lt 6 ]]; do
    if curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:$APP_PORT/" 2>/dev/null | grep -q 200; then
        PUBLIC_IP=$(curl -s ifconfig.me 2>/dev/null || echo "<IP>")
        echo ""
        echo -e "${GREEN}========================================${NC}"
        echo -e "${GREEN}  ✅ DEPLOYMENT SUCCESSFUL!${NC}"
        echo -e "${GREEN}========================================${NC}"
        echo -e "  Public:   http://$PUBLIC_IP:$APP_PORT"
        echo -e "  Logs:     tail -f $APP_DIR/logs/app.log"
        echo -e "  Restart:  sudo systemctl restart restaurant-social-automation"
        echo -e "  Status:   sudo systemctl status restaurant-social-automation"
        echo -e "${GREEN}========================================${NC}"
        exit 0
    fi
    RETRIES=$((RETRIES + 1))
    sleep 5
done

err "App failed to start after 30 seconds."
err "Check: sudo journalctl -u restaurant-social-automation --no-pager -n 60"
