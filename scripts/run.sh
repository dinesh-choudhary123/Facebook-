#!/usr/bin/env bash
#
# Restaurant Social Media Automation - Run Script
# ================================================
#
# Usage:
#   ./scripts/run.sh              # Start using local Python
#   ./scripts/run.sh --docker     # Start using Docker
#   ./scripts/run.sh --dev        # Development mode (hot reload)
#   ./scripts/run.sh --help       # Show help

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

show_help() {
    echo "Restaurant Social Media Automation - Run Script"
    echo ""
    echo "Usage: ./scripts/run.sh [OPTION]"
    echo ""
    echo "Options:"
    echo "  --help       Show this help message"
    echo "  --docker     Run with Docker Compose (full stack)"
    echo "  --dev        Run in development mode (hot reload)"
    echo "  --test       Run the test suite"
    echo "  (default)    Run in production mode"
    echo ""
    echo "Environment file:"
    echo "  Edit .env to configure API keys and settings"
    echo "  See .env.example for all options"
    echo ""
    echo "Quick start:"
    echo "  1. cp .env.example .env"
    echo "  2. Edit .env with your API keys"
    echo "  3. ./scripts/run.sh --dev"
    echo "  4. Open http://localhost:8000"
    echo ""
}

case "${1:-}" in
    --help)
        show_help
        ;;

    --docker)
        echo "🐳 Starting with Docker Compose..."
        docker compose up -d
        echo ""
        echo "Services starting:"
        echo "  - Automation App: http://localhost:8000"
        echo "  - ComfyUI: http://localhost:8188"
        echo "  - Ollama: http://localhost:11434"
        echo ""
        echo "View logs: docker compose logs -f"
        echo "Stop: docker compose down"
        ;;

    --dev)
        echo "🚀 Starting in development mode..."
        echo ""

        # Activate virtual environment if it exists
        if [[ -d "venv" ]]; then
            source venv/bin/activate
        fi

        # Check for .env
        if [[ ! -f ".env" ]]; then
            echo "⚠️  No .env file found. Creating from .env.example..."
            cp .env.example .env
            echo "⚠️  Please edit .env with your API keys!"
        fi

        echo "📡 Server: http://localhost:8000"
        echo "📚 API Docs: http://localhost:8000/docs"
        echo ""

        uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload
        ;;

    --test)
        echo "🧪 Running tests..."
        if [[ -d "venv" ]]; then
            source venv/bin/activate
        fi
        python -m pytest tests/ -v --tb=short 2>/dev/null || \
            echo "⚠️  pytest not found. Install with: pip install pytest"
        ;;

    *)
        echo "🚀 Starting in production mode..."
        echo ""

        if [[ -d "venv" ]]; then
            source venv/bin/activate
        fi

        if [[ ! -f ".env" ]]; then
            echo "⚠️  No .env file found."
            exit 1
        fi

        echo "📡 Server: http://localhost:8000"
        echo ""

        uvicorn api.app:app --host 0.0.0.0 --port 8000 --workers 2
        ;;
esac
