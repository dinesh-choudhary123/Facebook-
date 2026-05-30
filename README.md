<div align="center">
  <br/>
  <h1>🍽️ Restaurant Social Media Automation</h1>
  <p><strong>AI-powered restaurant poster enhancement & Facebook posting pipeline</strong></p>

  <p>
    <a href="#features">Features</a> •
    <a href="#quick-start">Quick Start</a> •
    <a href="#project-structure">Structure</a> •
    <a href="#api-reference">API</a> •
    <a href="#documentation">Docs</a>
  </p>

  <p>
    <img alt="Python" src="https://img.shields.io/badge/python-3.11+-blue.svg">
    <img alt="License" src="https://img.shields.io/badge/license-MIT-green">
  </p>

  <br/>
</div>

## Overview

Automate your restaurant's social media workflow:

1. **Upload** a restaurant food poster image
2. **Extract** text (OCR), logo, and design structure
3. **Enhance** or **AI-generate** a professional image
4. **Generate** engaging captions using AI
5. **Post** directly to Facebook

**100% free & open-source stack.** No paid APIs required.

### How It Works

```
📸 Upload Poster → 🔍 OCR Text Extraction → 🎨 Image Enhancement
    ↓                                        ↓
📝 AI Caption Generation ← 🖼️ SDXL/Processed Image
    ↓
📤 Facebook Auto-Post
```

## Features

- **OCR Extraction**: Tesseract-based text detection for food titles, prices, and offers
- **Background Removal**: AI-powered (rembg) with OpenCV fallback
- **Image Processing**: OpenCV/Pillow-based enhancement with premium backgrounds, gradients, and lighting
- **AI Generation**: ComfyUI + SDXL + ControlNet support for AI-powered poster recreation
- **Smart Captions**: Groq API → Gemini API → Ollama (local) priority chain
- **Facebook Auto-Post**: Meta Graph API with OAuth authentication
- **Web Interface**: Beautiful FastAPI single-page app
- **Docker Support**: Full stack or minimal deployment
- **Retry Logic**: Automatic retries with exponential backoff
- **Comprehensive Logging**: Structured logs with rotation

## Quick Start

### Option 1: Local Python

```bash
# 1. Clone & setup
git clone <your-repo>
cd restaurant-social-automation
chmod +x scripts/setup.sh
./scripts/setup.sh

# 2. Configure API keys
cp .env.example .env
# Edit .env with your keys (see docs/api_keys.md)

# 3. Start server
source venv/bin/activate
uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload

# 4. Open browser
open http://localhost:8000
```

### Option 2: Docker

```bash
# Minimal (no GPU needed)
docker compose --profile minimal up -d

# Full stack (with GPU)
docker compose --profile full up -d
```

## Project Structure

```
restaurant-social-automation/
├── api/
│   └── app.py                 # FastAPI web server + beautiful frontend
├── modules/
│   ├── ocr.py                 # Tesseract OCR extraction
│   ├── background_removal.py  # rembg + OpenCV fallback
│   ├── image_processing.py    # Image enhancement & composition
│   ├── image_generation.py    # ComfyUI/SDXL API client
│   ├── caption_generation.py  # Groq/Gemini/Ollama AI captions
│   └── facebook_poster.py     # Meta Graph API posting
├── workflow/
│   └── pipeline.py            # Orchestrator with retry logic
├── config/
│   └── settings.py            # Environment configuration
├── utils/
│   ├── logger.py              # Structured logging
│   └── storage.py             # File management
├── comfyui/workflows/
│   └── restaurant_poster.json # SDXL workflow template
├── scripts/
│   ├── setup.sh               # One-command setup
│   └── run.sh                 # Start with options
├── docs/
│   ├── setup.md               # Local setup guide
│   ├── api_keys.md            # API key setup instructions
│   ├── docker.md              # Docker deployment
│   ├── gpu.md                 # GPU recommendations
│   ├── deployment.md          # Cloud deployment options
│   └── optimization.md        # Performance tuning
├── tests/
│   └── test_pipeline.py       # Comprehensive tests
├── static/
│   ├── uploads/               # Uploaded images
│   └── outputs/               # Generated images
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── .env.example
```

## API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Web interface |
| `/api/health` | GET | Health check |
| `/api/config` | GET | Configuration status |
| `/api/setup-guide` | GET | API setup guides |
| `/api/process` | POST | Run full pipeline |
| `/api/image/{filename}` | GET | Get output image |
| `/api/outputs` | GET | List all outputs |

### Process Endpoint

```bash
curl -X POST http://localhost:8000/api/process \
  -F "file=@restaurant_poster.jpg" \
  -F "restaurant_name=Pizza Paradise" \
  -F "post_to_facebook=true" \
  -F "use_ai_generation=false"
```

## API Keys Required

**You need at least one of these for captions:**

| Service | Free Tier | Sign Up |
|---------|-----------|---------|
| Groq API | ✅ 30 req/min, 500K tokens/day | [console.groq.com](https://console.groq.com) |
| Gemini API | ✅ 60 req/min | [aistudio.google.com](https://aistudio.google.com/app/apikey) |
| Ollama | 🆓 Fully free, local | [ollama.com](https://ollama.com) |

**For Facebook posting:**
- Meta Developer App + Page Access Token (free)
- [developers.facebook.com](https://developers.facebook.com/)

## License

MIT - Free for any use.

Built with ❤️ using open-source tools: Tesseract, rembg, OpenCV, Pillow, ComfyUI, SDXL, Groq, Gemini, Ollama, FastAPI.
