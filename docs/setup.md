# Local Setup Guide

## Prerequisites

- **Python 3.11+**
- **Tesseract OCR** (for text extraction)
- **~8GB RAM** minimum (16GB recommended for AI generation)
- **Optional: NVIDIA GPU** with 8GB+ VRAM (for SDXL generation via ComfyUI)

## Quick Install (One Command)

```bash
chmod +x scripts/setup.sh
./scripts/setup.sh
```

## Manual Step-by-Step Installation

### 1. System Dependencies

#### macOS
```bash
brew install tesseract
```

#### Ubuntu/Debian
```bash
sudo apt-get update
sudo apt-get install -y tesseract-ocr tesseract-ocr-eng libgl1-mesa-glx libglib2.0-0
```

#### Fedora/RHEL
```bash
sudo yum install -y tesseract
```

#### Windows
- Download from: https://github.com/UB-Mannheim/tesseract/wiki
- Add to PATH
- Or use Docker (recommended for Windows)

### 2. Python Setup

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Upgrade pip
pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt

# Install background removal
pip install "rembg[cpu]"    # For CPU
# OR
pip install "rembg[gpu]"    # For NVIDIA GPU (requires CUDA)

# Install Groq SDK (for AI captions)
pip install groq
```

### 3. Environment Configuration

```bash
cp .env.example .env
# Edit .env with your API keys:
# - GROQ_API_KEY or GEMINI_API_KEY
# - META_PAGE_ID and META_PAGE_ACCESS_TOKEN
```

### 4. Start the Server

```bash
# Development mode (with hot reload)
uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload

# Production mode
uvicorn api.app:app --host 0.0.0.0 --port 8000 --workers 4
```

### 5. Open the Web Interface

Navigate to: **http://localhost:8000**

## Verify Installation

```bash
python -c "
from modules.ocr import RestaurantOCRExtractor
ocr = RestaurantOCRExtractor()
print('✅ OCR module ready')

from modules.background_removal import BackgroundRemover
bg = BackgroundRemover()
print('✅ Background removal ready')

from modules.caption_generation import CaptionGenerator
cg = CaptionGenerator()
print('✅ Caption generation ready')
"
```

## Quick Test

Upload any restaurant poster image through the web interface at `http://localhost:8000` and click "Run Automation Pipeline". The system will:
1. Extract text via OCR
2. Remove background
3. Enhance the image
4. Generate AI captions (if API keys configured)
5. (Optional) Post to Facebook

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `pytesseract.pytesseract.TesseractNotFoundError` | Install Tesseract OCR (see above) |
| `ModuleNotFoundError: rembg` | Run `pip install "rembg[cpu]"` |
| `Connection refused` on ComfyUI | Start ComfyUI or set `use_ai_generation=false` |
| `403` from Facebook API | Refresh your Page Access Token |
