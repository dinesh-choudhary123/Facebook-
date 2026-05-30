# Docker Setup Guide

Run the entire restaurant automation stack using Docker containers.

## Prerequisites

- Docker Engine 24.0+
- Docker Compose 2.20+
- For GPU support: NVIDIA Container Toolkit

## Quick Start

```bash
# Start the full stack
docker compose --profile full up -d

# Or start minimal (no GPU needed)
docker compose --profile minimal up -d

# View logs
docker compose logs -f
```

## Services

| Service | Port | Description | GPU Required |
|---------|------|-------------|-------------|
| Automation App | 8000 | FastAPI web interface | No |
| ComfyUI | 8188 | SDXL image generation | Yes |
| Ollama | 11434 | Local LLM for captions | No |

## Profiles

### Full Stack (with GPU)
```bash
docker compose --profile full up -d
```
Starts all services including ComfyUI and Ollama. Requires NVIDIA GPU.

### Minimal Stack (CPU only)
```bash
docker compose --profile minimal up -d
```
Starts only the automation app. Uses image processing fallback instead of SDXL.

## Docker Commands

```bash
# Build images
docker compose build

# Start services
docker compose up -d

# View logs
docker compose logs -f
docker compose logs app
docker compose logs comfyui

# Stop services
docker compose down

# Restart a service
docker compose restart app

# Run commands in container
docker compose exec app python -c "print('hello')"

# View resource usage
docker stats
```

## GPU Setup

For ComfyUI with GPU acceleration:

1. **Install NVIDIA Container Toolkit:**
   ```bash
   # Ubuntu/Debian
   sudo apt-get install -y nvidia-container-toolkit
   sudo systemctl restart docker

   # macOS
   # Docker Desktop with Apple Silicon supports GPU natively
   ```

2. **Verify GPU access:**
   ```bash
   docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
   ```

3. **Start with GPU support:**
   ```bash
   docker compose --profile full up -d
   ```

## Environment Variables

Create a `.env` file in the project root (copy from `.env.example`):

```bash
# Required for API features
GROQ_API_KEY=gsk_your_key
META_PAGE_ID=your_page_id
META_PAGE_ACCESS_TOKEN=your_token

# Service URLs (Docker network)
COMFYUI_HOST=http://comfyui
OLLAMA_HOST=http://ollama
```

## Volumes

| Volume | Path | Description |
|--------|------|-------------|
| uploads | /app/static/uploads | Uploaded images |
| outputs | /app/static/outputs | Generated images |
| comfyui-models | /workspace/models | SDXL model files |
| ollama-models | /root/.ollama | LLM model files |

## Troubleshooting Docker

**Port already in use:**
```bash
# Check what's using the port
lsof -i :8000
# Change port in docker-compose.yml
```

**Out of disk space:**
```bash
docker system prune -a --volumes
```

**GPU not available:**
```bash
# Check if nvidia-toolkit is installed
docker info | grep -i nvidia
# Install: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html
```
