#!/usr/bin/env bash
#
# Restaurant Social Media Automation - Setup Script
# ==================================================
# This script installs all dependencies for the automation pipeline.
#
# Usage:
#   chmod +x scripts/setup.sh
#   ./scripts/setup.sh              # Full setup
#   ./scripts/setup.sh --minimal    # Minimal setup (no ComfyUI/Ollama)
#   ./scripts/setup.sh --docker     # Docker-based setup
#   ./scripts/setup.sh --gpu        # Setup with GPU support

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

echo "============================================"
echo "  Restaurant Social Media Automation"
echo "  Setup Script"
echo "============================================"
echo ""

# Parse arguments
MODE="${1:-full}"

echo "📦 Project directory: $PROJECT_DIR"
echo "🔧 Mode: $MODE"
echo ""

install_system_deps() {
    echo "📦 Installing system dependencies..."

    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        if command -v brew &>/dev/null; then
            brew install tesseract || echo "⚠️  Could not install tesseract via brew"
        else
            echo "⚠️  Homebrew not found. Install from: https://brew.sh"
        fi

    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        # Linux
        if command -v apt-get &>/dev/null; then
            sudo apt-get update
            sudo apt-get install -y \
                tesseract-ocr \
                tesseract-ocr-eng \
                libgl1-mesa-glx \
                libglib2.0-0 \
                || echo "⚠️  Some system deps may have failed"
        elif command -v yum &>/dev/null; then
            sudo yum install -y tesseract || echo "⚠️  Could not install tesseract"
        else
            echo "⚠️  Unknown package manager. Install tesseract manually."
        fi
    fi

    echo "✅ System dependencies installed"
    echo ""
}

install_python_deps() {
    echo "🐍 Installing Python dependencies..."

    # Create virtual environment if not exists
    if [[ ! -d "venv" ]]; then
        echo "Creating virtual environment..."
        python3 -m venv venv
    fi

    source venv/bin/activate

    # Upgrade pip
    pip install --upgrade pip

    # Install core requirements
    pip install -r requirements.txt

    # Install rembg (CPU version by default)
    if [[ "$MODE" == "--gpu" ]]; then
        echo "Installing rembg with GPU support..."
        pip install "rembg[gpu]"
    else
        echo "Installing rembg with CPU support..."
        pip install "rembg[cpu]"
    fi

    echo "✅ Python dependencies installed"
    echo ""
}

setup_environment() {
    echo "🔑 Setting up environment..."

    if [[ ! -f ".env" ]]; then
        cp .env.example .env
        echo "Created .env file from .env.example"
        echo "⚠️  Please edit .env with your API keys!"
        echo ""
        echo "Required (for full functionality):"
        echo "  - GROQ_API_KEY or GEMINI_API_KEY (for captions)"
        echo "  - META_PAGE_ID + META_PAGE_ACCESS_TOKEN (for Facebook posting)"
        echo "Optional:"
        echo "  - COMFYUI_HOST/COMFYUI_PORT (for AI image generation)"
        echo ""
    else
        echo ".env file already exists"
    fi
}

setup_docker() {
    echo "🐳 Setting up Docker environment..."

    if ! command -v docker &>/dev/null; then
        echo "❌ Docker not found. Install from: https://docs.docker.com/get-docker/"
        exit 1
    fi

    # Build and start
    docker compose build
    echo ""
    echo "To start the services:"
    echo "  docker compose up -d"
    echo "  docker compose logs -f"
    echo ""

    # Setup .env
    if [[ ! -f ".env" ]]; then
        cp .env.example .env
        echo "Created .env file. Please edit it with your API keys."
    fi
}

create_directories() {
    echo "📁 Creating required directories..."
    mkdir -p static/uploads static/outputs logs
    echo "✅ Directories created"
    echo ""
}

check_comfyui() {
    echo "🔍 Checking ComfyUI..."

    if command -v curl &>/dev/null; then
        if curl -s http://127.0.0.1:8188/system_stats &>/dev/null; then
            echo "✅ ComfyUI is running at http://127.0.0.1:8188"
        else
            echo "⚠️  ComfyUI not detected at http://127.0.0.1:8188"
            echo "   To use AI image generation, start ComfyUI:"
            echo "   cd ComfyUI && python main.py --listen"
        fi
    fi
    echo ""
}

# Main setup flow
case "$MODE" in
    --minimal)
        create_directories
        install_system_deps
        install_python_deps
        setup_environment
        ;;
    --docker)
        create_directories
        setup_environment
        setup_docker
        ;;
    --gpu)
        create_directories
        install_system_deps
        install_python_deps
        setup_environment
        echo "🎮 For GPU acceleration, ensure CUDA toolkit is installed."
        echo "   See: https://developer.nvidia.com/cuda-downloads"
        ;;
    full|--full)
        create_directories
        install_system_deps
        install_python_deps
        setup_environment
        check_comfyui
        ;;
    *)
        echo "Usage: $0 [--minimal|--docker|--gpu|--full]"
        echo ""
        echo "  (default)  Full local setup"
        echo "  --minimal  Skip ComfyUI/GitHub-specific checks"
        echo "  --docker   Setup using Docker containers"
        echo "  --gpu      Setup with NVIDIA GPU support"
        exit 1
        ;;
esac

echo ""
echo "============================================"
echo "  Setup Complete! 🎉"
echo "============================================"
echo ""
echo "Next steps:"
echo "  1. Edit .env with your API keys"
echo "  2. Start the server:"
echo "     source venv/bin/activate"
echo "     uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload"
echo "  3. Open http://localhost:8000 in your browser"
echo "  4. Upload a restaurant poster image"
echo ""
echo "For detailed documentation:"
echo "  cat docs/setup.md"
echo "  cat docs/api_keys.md"
echo ""
