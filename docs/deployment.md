# Deployment Guide

## Local Deployment

### Production Server

```bash
# Using Gunicorn + Uvicorn workers
pip install gunicorn
gunicorn api.app:app \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:8000 \
    --workers 4 \
    --timeout 120 \
    --max-requests 1000 \
    --max-requests-jitter 100
```

### Systemd Service (Linux)

```ini
# /etc/systemd/system/restaurant-automation.service
[Unit]
Description=Restaurant Social Media Automation
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/restaurant-social-automation
EnvironmentFile=/home/ubuntu/restaurant-social-automation/.env
ExecStart=/home/ubuntu/restaurant-social-automation/venv/bin/gunicorn \
    api.app:app \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:8000 \
    --workers 4
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable restaurant-automation
sudo systemctl start restaurant-automation
sudo systemctl status restaurant-automation
```

### Nginx Reverse Proxy

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        client_max_body_size 50M;
    }

    location /static/ {
        alias /home/ubuntu/restaurant-social-automation/static/;
        expires 7d;
    }
}
```

```bash
# Enable HTTPS with Certbot
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

---

## Free Cloud Deployment Options

### 1. Hugging Face Spaces (Free)

1. Create account at https://huggingface.co
2. Create a new Space → Docker → SDXL
3. Add `Dockerfile` and `docker-compose.yml`
4. Set secrets in Space Settings:
   - `GROQ_API_KEY`
   - `META_PAGE_ACCESS_TOKEN`
5. Space auto-deploys on git push

**Limitations:** CPU only, 16GB RAM, sleeps on inactivity

### 2. Google Cloud Run (Free Tier)

```bash
# Build and push to Google Container Registry
gcloud builds submit --tag gcr.io/your-project/restaurant-auto

# Deploy
gcloud run deploy restaurant-auto \
    --image gcr.io/your-project/restaurant-auto \
    --platform managed \
    --region us-central1 \
    --allow-unauthenticated \
    --memory 2Gi \
    --cpu 2 \
    --timeout 300 \
    --set-env-vars "GROQ_API_KEY=your_key,META_PAGE_ID=your_id"
```

**Free Tier:** 2M requests/month, 1GB RAM, 360K GB-seconds

### 3. Fly.io (Free Tier)

```bash
# Install flyctl
curl -L https://fly.io/install.sh | sh

# Launch
fly launch

# Deploy
fly deploy

# Set secrets
fly secrets set GROQ_API_KEY=your_key META_PAGE_ACCESS_TOKEN=your_token
```

**Free Tier:** 3 VMs with 256MB RAM, 1-3GB storage

### 4. Render (Free Tier)

1. Create account at https://render.com
2. New Web Service → Connect repository
3. Settings:
   - Build Command: `pip install -r requirements.txt && pip install "rembg[cpu]"`
   - Start Command: `uvicorn api.app:app --host 0.0.0.0 --port $PORT`
4. Add environment variables
5. Deploy

**Free Tier:** 512MB RAM, sleeps after 15min inactivity

### 5. Railway (Free Tier)

```bash
railway login
railway init
railway up
```

**Free Tier:** $5 credit, 512MB RAM, 1GB storage

### 6. Replit (Free)

1. Create account at https://replit.com
2. Import from GitHub
3. Add secrets in Replit Secrets
4. Run: `uvicorn api.app:app --host 0.0.0.0 --port 8000`

**Free Tier:** Limited CPU/RAM, always-on with hacker plan

---

## Deployment Comparison

| Platform | Free Tier | GPU | Always On | Best For |
|----------|-----------|-----|-----------|----------|
| Local | ✅ | ✅ | ✅ | Full control |
| Hugging Face | ✅ | ❌ | ❌ | Quick demo |
| Google Cloud Run | ✅ | ❌ | ✅ | API deployment |
| Fly.io | ✅ | ❌ | ✅ | Small deployments |
| Render | ✅ | ❌ | ❌ | Easy setup |
| Railway | ✅ | ❌ | ✅ | Simple apps |
| Replit | ✅ | ❌ | ❌ | Development |

**Recommendation for production:** Use Google Cloud Run or Fly.io with Groq API for captions (no GPU needed for core functionality). Add GPU via RunPod or Vast.ai for image generation.

## Monitoring

```bash
# Health check
curl http://localhost:8000/api/health

# View logs
tail -f logs/automation.log

# Monitor API status
curl http://localhost:8000/api/config

# Check outputs
curl http://localhost:8000/api/outputs
```
