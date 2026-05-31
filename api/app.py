"""
FastAPI Web Application - Provides a web interface for the restaurant
social media automation pipeline with image upload and status tracking.
"""

import os
import json
from pathlib import Path
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

# Import project modules
from config.settings import settings, setup_logging
from utils.logger import get_logger
from utils.storage import StorageManager
from modules.ocr import RestaurantOCRExtractor
from modules.caption_generation import CaptionGenerator
from modules.facebook_poster import FacebookPoster
from modules.batch_scheduler import BatchScheduler
from workflow.pipeline import RestaurantPipeline, PipelineResult

logger = get_logger(__name__)

# Global state
pipeline: Optional[RestaurantPipeline] = None
storage: Optional[StorageManager] = None
app_config = {}
batch_scheduler: Optional[BatchScheduler] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and cleanup application resources."""
    global pipeline, storage, app_config, batch_scheduler

    logger.info("🚀 Starting Restaurant Social Media Automation API")
    logger.info(f"Caption Provider: {settings.caption_provider()}")
    logger.info(f"Facebook: {'Configured' if settings.facebook_configured else 'Not Configured'}")

    # Initialize storage
    storage = StorageManager(
        temp_dir=str(settings.TEMP_DIR),
        output_dir=str(settings.OUTPUT_DIR),
    )

    # Initialize modules
    ocr = RestaurantOCRExtractor()
    caption_gen = CaptionGenerator(
        groq_api_key=settings.GROQ_API_KEY,
        gemini_api_key=settings.GEMINI_API_KEY,
        ollama_host=settings.OLLAMA_HOST,
        ollama_port=settings.OLLAMA_PORT,
        ollama_model=settings.OLLAMA_MODEL,
    )
    fb_poster = None
    if settings.facebook_configured:
        fb_poster = FacebookPoster(
            page_id=settings.META_PAGE_ID,
            page_access_token=settings.META_PAGE_ACCESS_TOKEN,
            api_version=settings.META_API_VERSION,
            app_id=settings.META_APP_ID,
            app_secret=settings.META_APP_SECRET,
        )

    # Initialize pipeline (simplified — no image processing or AI generation)
    pipeline = RestaurantPipeline(
        ocr_extractor=ocr,
        caption_generator=caption_gen,
        facebook_poster=fb_poster,
        storage=storage,
    )

    # Initialize batch scheduler
    batch_dir = Path(__file__).parent.parent / "batch"
    batch_scheduler = BatchScheduler(batch_dir=str(batch_dir), fb_poster=fb_poster)
    logger.info(f"📁 Batch folder: {batch_dir} ({batch_scheduler._count_queued()} pairs queued)")

    # Check for missing API keys
    missing = settings.get_missing_keys()
    if missing:
        logger.info(f"Optional keys not configured: {', '.join(missing)}")

    app_config = {
        "groq_available": settings.groq_available,
        "gemini_available": settings.gemini_available,
        "facebook_configured": settings.facebook_configured,
    }

    yield


app = FastAPI(
    title="Restaurant Social Media Automation",
    description="Automated restaurant poster processing and Facebook posting pipeline",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files
app.mount("/static", StaticFiles(directory="static"), name="static")


# --- API Routes ---

@app.get("/", response_class=HTMLResponse)
async def index():
    """Main page with upload form."""
    return HTMLResponse(INDEX_HTML)


@app.get("/api/config")
async def get_config():
    """Get application configuration status."""
    missing_keys = []
    if not settings.GROQ_API_KEY:
        missing_keys.append({"key": "GROQ_API_KEY", "doc": "https://console.groq.com"})
    if not settings.GEMINI_API_KEY:
        missing_keys.append({"key": "GEMINI_API_KEY", "doc": "https://aistudio.google.com/app/apikey"})
    if not settings.META_PAGE_ACCESS_TOKEN:
        missing_keys.append({"key": "META_PAGE_ACCESS_TOKEN", "doc": "https://developers.facebook.com/"})

    return JSONResponse({
        "status": "running",
        "config": app_config,
        "message": "Original image is posted directly to Facebook with AI-generated captions",
        "missing_api_keys": missing_keys,
        "api_keys_docs": {
            "groq": "https://console.groq.com",
            "gemini": "https://aistudio.google.com/app/apikey",
            "meta": "https://developers.facebook.com/docs/facebook-login/access-tokens",
        }
    })


@app.post("/api/process")
async def process_image(
    file: UploadFile = File(...),
    restaurant_name: str = Form(""),
    post_to_facebook: bool = Form(True),
):
    """
    Upload image and run the full automation pipeline.

    Args:
        file: Restaurant poster image
        restaurant_name: Optional restaurant name
        post_to_facebook: Whether to post to Facebook
        use_ai_generation: Whether to use SDXL generation

    Returns:
        PipelineResult with all outputs
    """
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    # Save uploaded file
    file_data = await file.read()
    saved_path = storage.save_upload(file_data, file.filename)
    logger.info(f"Image uploaded: {saved_path}")

    # Configure pipeline
    pipeline.post_to_facebook = post_to_facebook

    # Run pipeline (original image posted directly)
    result = pipeline.run(str(saved_path), restaurant_name)

    # Prepare response
    response = result.to_dict()

    # Add file URLs
    if result.final_image_path:
        response["final_image_url"] = f"/api/image/{Path(result.final_image_path).name}"

    status_code = 200 if result.status in ("success", "partial") else 500
    return JSONResponse(content=response, status_code=status_code)


@app.get("/api/image/{filename}")
async def get_image(filename: str):
    """Retrieve a processed image."""
    image_path = storage.output_dir / filename
    if not image_path.exists():
        image_path = storage.temp_dir / filename
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(str(image_path), media_type=f"image/{image_path.suffix[1:]}")


@app.get("/api/outputs")
async def list_outputs():
    """List all generated output images."""
    return JSONResponse(content={"outputs": storage.list_outputs()})


@app.get("/api/setup-guide")
async def get_setup_guide(provider: str = ""):
    """Get API key setup instructions for a specific provider."""
    guides = {
        "groq": {
            "name": "Groq API",
            "url": "https://console.groq.com",
            "steps": [
                "1. Visit https://console.groq.com",
                "2. Sign up or log in with Google/GitHub",
                "3. Go to API Keys section",
                "4. Click 'Create API Key'",
                "5. Copy the key and add to .env: GROQ_API_KEY=your_key",
            ],
            "free_tier": "Free tier: 30 requests/min, 500K tokens/day",
        },
        "gemini": {
            "name": "Google Gemini API",
            "url": "https://aistudio.google.com/app/apikey",
            "steps": [
                "1. Visit https://aistudio.google.com/app/apikey",
                "2. Sign in with Google account",
                "3. Click 'Create API Key'",
                "4. Copy the key and add to .env: GEMINI_API_KEY=your_key",
            ],
            "free_tier": "Free tier: 60 requests/min",
        },
        "meta": {
            "name": "Meta Graph API",
            "url": "https://developers.facebook.com/",
            "steps": [
                "1. Visit https://developers.facebook.com/",
                "2. Create or select your App",
                "3. Go to Settings > Basic - copy App ID & Secret",
                "4. Go to Tools > Graph API Explorer",
                "5. Get a Page Access Token with pages_manage_posts scope",
                "6. Add to .env: META_PAGE_ID, META_PAGE_ACCESS_TOKEN",
            ],
            "free_tier": "Free with valid Facebook Page",
        },
    }

    if provider:
        return JSONResponse(guides.get(provider, {"error": "Unknown provider"}))
    return JSONResponse(guides)


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return JSONResponse({
        "status": "healthy",
        "api_version": "1.0.0",
        "facebook_configured": settings.facebook_configured,
        "caption_provider": settings.caption_provider(),
        "missing_keys": settings.get_missing_keys(),
    })


# ── Batch Automation Endpoints ─────────────────────────────────


@app.get("/api/batch/status")
async def batch_status():
    """Get batch scheduler status."""
    return JSONResponse(batch_scheduler.status())


@app.post("/api/batch/start")
async def batch_start(interval: int = 30):
    """Start batch automation with given interval in minutes."""
    result = batch_scheduler.start(interval_minutes=interval)
    return JSONResponse(result)


@app.post("/api/batch/stop")
async def batch_stop():
    """Stop batch automation."""
    result = batch_scheduler.stop()
    return JSONResponse(result)


@app.post("/api/batch/pause")
async def batch_pause():
    """Pause batch automation."""
    result = batch_scheduler.pause()
    return JSONResponse(result)


@app.post("/api/batch/resume")
async def batch_resume():
    """Resume batch automation."""
    result = batch_scheduler.resume()
    return JSONResponse(result)


@app.post("/api/batch/skip")
async def batch_skip():
    """Skip the current pending post."""
    result = batch_scheduler.skip_current()
    return JSONResponse(result)



@app.post("/api/batch/upload-pairs")
async def batch_upload_pairs(
    files: list[UploadFile] = File(...),
    captions: list[str] = Form(...),
):
    """
    Upload multiple images with their captions to the batch folder.
    Images are saved as files, captions as matching .txt files.
    Supports long text, emojis, and any Unicode characters.
    """
    if len(files) != len(captions):
        raise HTTPException(status_code=400, detail="Number of files and captions must match")

    results = []
    for file, caption in zip(files, captions):
        image_data = await file.read()
        result = batch_scheduler.add_pair_with_caption(
            image_data=image_data,
            image_name=file.filename,
            caption=caption,
        )
        results.append(result)

    success_count = sum(1 for r in results if r["success"])
    return JSONResponse({
        "success": True,
        "total": len(results),
        "success_count": success_count,
        "results": results,
    })


@app.post("/api/batch/schedule")
async def batch_schedule(interval: int = 30, scheduled_at: str = Form(...)):
    """Schedule the batch scheduler to start at a specific time."""
    result = batch_scheduler.schedule_start(interval_minutes=interval, scheduled_at_iso=scheduled_at)
    return JSONResponse(result)







INDEX_HTML = '<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="UTF-8">\n<meta name="viewport" content="width=device-width, initial-scale=1.0">\n<title>SocialPost Automation</title>\n<link rel="preconnect" href="https://fonts.googleapis.com">\n<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">\n<style>\n*,*::before,*::after{margin:0;padding:0;box-sizing:border-box}\n:root{\n  --bg:#0b0a0f;\n  --card-bg:rgba(255,255,255,0.04);\n  --card-border:rgba(255,255,255,0.07);\n  --text:#e8e6e3;\n  --text-dim:#8a8886;\n  --text-muted:#6b6866;\n  --accent:#f7971e;\n  --accent2:#ffd200;\n  --gradient:linear-gradient(135deg,#f7971e,#ffd200);\n  --success:#4ade80;\n  --error:#f87171;\n  --info:#60a5fa;\n  --radius:16px;\n  --radius-sm:10px;\n}\nhtml{scroll-behavior:smooth}\nbody{\n  font-family:\'Inter\',-apple-system,sans-serif;\n  background:var(--bg);color:var(--text);\n  min-height:100vh;overflow-x:hidden;\n  line-height:1.5;-webkit-font-smoothing:antialiased;\n}\n/* Particles */\n#particles-canvas{position:fixed;top:0;left:0;width:100%;height:100%;z-index:0;pointer-events:none}\n\n/* BG Glow */\n.bg-glow{\n  position:fixed;border-radius:50%;filter:blur(80px);\n  z-index:0;pointer-events:none;opacity:0.1;\n}\n.bg-glow-1{width:600px;height:600px;top:-200px;right:-100px;background:#f7971e;animation:glowFloat 12s ease-in-out infinite}\n.bg-glow-2{width:500px;height:500px;bottom:-150px;left:-100px;background:#ffd200;animation:glowFloat 15s ease-in-out infinite reverse}\n@keyframes glowFloat{\n  0%,100%{transform:translate(0,0) scale(1)}\n  33%{transform:translate(30px,-30px) scale(1.1)}\n  66%{transform:translate(-20px,20px) scale(0.95)}\n}\n\n/* Container */\n.app-container{position:relative;z-index:1;max-width:1000px;margin:0 auto;padding:20px 20px 40px}\n\n/* Header */\n.header{text-align:center;padding:40px 20px 28px;animation:fadeDown 0.8s ease-out}\n.header .logo-icon{font-size:48px;display:block;margin-bottom:8px;filter:drop-shadow(0 0 20px rgba(247,151,30,0.3));animation:logoPulse 3s ease-in-out infinite}\n@keyframes logoPulse{\n  0%,100%{transform:scale(1);filter:drop-shadow(0 0 20px rgba(247,151,30,0.3))}\n  50%{transform:scale(1.05);filter:drop-shadow(0 0 30px rgba(247,151,30,0.5))}\n}\n.header h1{\n  font-size:32px;font-weight:800;\n  background:var(--gradient);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;\n}\n.header .subtitle{color:var(--text-dim);font-size:14px;margin-top:8px}\n\n/* Tabs */\n.tabs{\n  display:flex;gap:4px;margin-bottom:24px;\n  background:rgba(255,255,255,0.03);border-radius:14px;\n  padding:4px;border:1px solid rgba(255,255,255,0.05);\n  animation:fadeUp 0.4s ease-out 0.1s both;\n}\n.tab{\n  flex:1;padding:12px 20px;border:none;background:transparent;\n  color:var(--text-muted);font-size:14px;font-weight:500;\n  cursor:pointer;border-radius:10px;\n  transition:all 0.3s cubic-bezier(0.4,0,0.2,1);\n  font-family:inherit;\n}\n.tab:hover{color:var(--text-dim);background:rgba(255,255,255,0.04)}\n.tab.active{\n  background:var(--gradient);color:#1a1a1a;font-weight:600;\n  box-shadow:0 4px 15px rgba(247,151,30,0.25);\n}\n.tab-content{display:none;animation:fadeUp 0.4s ease-out}\n.tab-content.active{display:block}\n@keyframes fadeUp{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:translateY(0)}}\n@keyframes fadeDown{from{opacity:0;transform:translateY(-12px)}to{opacity:1;transform:translateY(0)}}\n\n/* Card */\n.card{\n  background:rgba(255,255,255,0.04);\n  backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);\n  border:1px solid rgba(255,255,255,0.07);\n  border-radius:var(--radius);padding:24px;margin-bottom:20px;\n  transition:all 0.3s cubic-bezier(0.4,0,0.2,1);\n  position:relative;overflow:hidden;\n}\n.card::before{\n  content:\'\';position:absolute;top:0;left:0;right:0;height:1px;\n  background:linear-gradient(90deg,transparent,rgba(247,151,30,0.3),transparent);\n  opacity:0;transition:opacity 0.5s;\n}\n.card:hover::before{opacity:1}\n.card:hover{\n  border-color:rgba(247,151,30,0.2);\n  transform:translateY(-1px);\n  box-shadow:0 12px 40px rgba(0,0,0,0.2),0 0 40px rgba(247,151,30,0.03);\n}\n.card-header{\n  display:flex;align-items:center;gap:10px;margin-bottom:20px;\n}\n.card-header .icon{\n  width:36px;height:36px;border-radius:10px;\n  background:var(--gradient);display:flex;align-items:center;justify-content:center;\n  font-size:18px;flex-shrink:0;\n  box-shadow:0 4px 12px rgba(247,151,30,0.2);\n}\n.card-header h2{font-size:17px;font-weight:600}\n.card-header .badge{\n  margin-left:auto;font-size:11px;padding:4px 10px;border-radius:20px;\n  background:rgba(255,255,255,0.06);color:var(--text-dim);\n  border:1px solid rgba(255,255,255,0.06);\n}\n\n/* Stats Grid */\n.stats-grid{\n  display:grid;\n  grid-template-columns:repeat(auto-fit,minmax(135px,1fr));\n  gap:10px;margin-bottom:20px;\n}\n.stat-card{\n  background:rgba(255,255,255,0.03);\n  border:1px solid rgba(255,255,255,0.05);\n  border-radius:12px;padding:16px 12px;text-align:center;\n  transition:all 0.3s;position:relative;overflow:hidden;\n}\n.stat-card:hover{\n  border-color:rgba(247,151,30,0.15);\n  transform:translateY(-2px);\n  box-shadow:0 8px 25px rgba(0,0,0,0.15);\n}\n.stat-card .stat-icon{font-size:20px;margin-bottom:6px;opacity:0.7}\n.stat-card .stat-label{font-size:10px;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.8px;font-weight:600}\n.stat-card .stat-value{font-size:22px;font-weight:700;margin-top:4px;transition:all 0.3s}\n.stat-value.green{color:var(--success)}\n.stat-value.orange{color:#fb923c}\n.stat-value.blue{color:var(--info)}\n.stat-value.purple{color:#a78bfa}\n.stat-value.yellow{color:#facc15}\n.stat-value.pulse{animation:statPulse 1s ease}\n@keyframes statPulse{0%{transform:scale(1)}50%{transform:scale(1.15)}100%{transform:scale(1)}}\n\n/* Status Dot */\n.status-dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px;vertical-align:middle}\n.status-dot.running{background:var(--success);box-shadow:0 0 10px rgba(74,222,128,0.5);animation:blink 1.5s ease-in-out infinite}\n.status-dot.idle{background:var(--text-muted)}\n.status-dot.paused{background:#facc15;box-shadow:0 0 10px rgba(250,204,21,0.5)}\n@keyframes blink{0%,100%{opacity:1}50%{opacity:0.4}}\n\n/* Controls */\n.controls-row{display:flex;gap:10px;flex-wrap:wrap;align-items:center}\n.controls-row label{font-size:13px;color:var(--text-dim);font-weight:500}\n.controls-row select{\n  background:rgba(0,0,0,0.3);border:1px solid rgba(255,255,255,0.1);\n  color:var(--text);padding:9px 14px;border-radius:var(--radius-sm);\n  font-size:13px;font-family:inherit;outline:none;cursor:pointer;\n  appearance:none;-webkit-appearance:none;\n  background-image:url("data:image/svg+xml,%3Csvg xmlns=\'http://www.w3.org/2000/svg\' width=\'12\' height=\'12\' viewBox=\'0 0 24 24\' fill=\'none\' stroke=\'%23888\' stroke-width=\'2\' stroke-linecap=\'round\' stroke-linejoin=\'round\'%3E%3Cpolyline points=\'6 9 12 15 18 9\'%3E%3C/polyline%3E%3C/svg%3E");\n  background-repeat:no-repeat;background-position:right 10px center;\n  padding-right:32px;transition:border-color 0.2s;\n}\n.controls-row select:focus{border-color:var(--accent)}\n.controls-row select:hover{border-color:rgba(255,255,255,0.2)}\n\n/* Buttons */\n.btn{\n  padding:10px 22px;border:none;border-radius:var(--radius-sm);\n  font-size:13px;font-weight:600;cursor:pointer;\n  transition:all 0.25s cubic-bezier(0.4,0,0.2,1);\n  display:inline-flex;align-items:center;gap:6px;\n  font-family:inherit;position:relative;overflow:hidden;white-space:nowrap;\n}\n.btn:disabled{opacity:0.4;cursor:not-allowed}\n.btn::after{\n  content:\'\';position:absolute;inset:0;\n  background:rgba(255,255,255,0.08);\n  transform:translateX(-100%);transition:transform 0.4s;\n}\n.btn:hover:not(:disabled)::after{transform:translateX(0)}\n.btn:active:not(:disabled){transform:scale(0.97)}\n\n.btn-primary{\n  background:var(--gradient);color:#1a1a1a;\n  box-shadow:0 4px 15px rgba(247,151,30,0.25);\n}\n.btn-primary:hover:not(:disabled){\n  transform:translateY(-2px);\n  box-shadow:0 8px 25px rgba(247,151,30,0.35);\n}\n.btn-secondary{\n  background:rgba(255,255,255,0.07);color:var(--text);\n  border:1px solid rgba(255,255,255,0.1);\n}\n.btn-secondary:hover:not(:disabled){background:rgba(255,255,255,0.12);transform:translateY(-1px)}\n.btn-danger{\n  background:rgba(239,68,68,0.12);color:var(--error);\n  border:1px solid rgba(239,68,68,0.2);\n}\n.btn-danger:hover:not(:disabled){background:rgba(239,68,68,0.2);transform:translateY(-1px)}\n.btn-success{\n  background:rgba(74,222,128,0.12);color:var(--success);\n  border:1px solid rgba(74,222,128,0.2);\n}\n.btn-success:hover:not(:disabled){background:rgba(74,222,128,0.2);transform:translateY(-1px)}\n.btn-ghost{background:transparent;color:var(--text-dim);padding:8px 12px}\n.btn-ghost:hover:not(:disabled){color:var(--text);background:rgba(255,255,255,0.05)}\n.btn-sm{padding:8px 16px;font-size:12px;border-radius:8px}\n.btn-xs{padding:5px 10px;font-size:11px;border-radius:6px}\n\n.btn-spinner{\n  width:14px;height:14px;\n  border:2px solid rgba(0,0,0,0.15);border-top-color:#1a1a1a;\n  border-radius:50%;animation:spin 0.6s linear infinite;display:inline-block;\n}\n.btn-spinner.light{border-color:rgba(255,255,255,0.15);border-top-color:#fff}\n@keyframes spin{to{transform:rotate(360deg)}}\n\n/* Dropzone */\n.dropzone{\n  border:2px dashed rgba(255,255,255,0.15);border-radius:14px;\n  padding:48px 24px;text-align:center;cursor:pointer;\n  transition:all 0.3s cubic-bezier(0.4,0,0.2,1);\n  background:rgba(255,255,255,0.02);position:relative;\n}\n.dropzone:hover,.dropzone.dragover{\n  border-color:var(--accent);background:rgba(247,151,30,0.06);\n  box-shadow:inset 0 0 40px rgba(247,151,30,0.04);\n}\n.dropzone.dragover{border-style:solid;transform:scale(1.01)}\n.dropzone .dz-icon{font-size:44px;margin-bottom:10px;display:block;transition:transform 0.3s}\n.dropzone:hover .dz-icon{transform:translateY(-4px)}\n.dropzone .dz-title{font-size:16px;font-weight:600;margin-bottom:4px}\n.dropzone .dz-hint{font-size:13px;color:var(--text-muted)}\n.dropzone .dz-hint strong{color:var(--text-dim)}\n\n/* Image Pairs */\n.pairs-section{margin-top:16px}\n.pairs-count{font-size:12px;color:var(--text-muted);margin-bottom:10px;font-weight:500}\n.pairs-count span{color:var(--accent)}\n\n.image-pair{\n  display:flex;gap:12px;align-items:flex-start;\n  background:rgba(255,255,255,0.03);\n  border:1px solid rgba(255,255,255,0.06);\n  border-radius:12px;padding:12px;margin-bottom:8px;\n  transition:all 0.25s cubic-bezier(0.4,0,0.2,1);\n  animation:slideIn 0.3s ease-out;\n}\n@keyframes slideIn{from{opacity:0;transform:translateX(-10px)}to{opacity:1;transform:translateX(0)}}\n.image-pair:hover{border-color:rgba(255,255,255,0.12);background:rgba(255,255,255,0.05)}\n.image-pair .pair-img{\n  width:56px;height:56px;object-fit:cover;border-radius:8px;\n  flex-shrink:0;border:1px solid rgba(255,255,255,0.06);\n}\n.image-pair .pair-info{flex:1;min-width:0}\n.image-pair .pair-name{font-size:12px;color:var(--text-dim);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-bottom:4px}\n.image-pair .pair-caption{\n  width:100%;background:rgba(0,0,0,0.3);\n  border:1px solid rgba(255,255,255,0.08);border-radius:6px;\n  color:var(--text);padding:7px 10px;font-size:13px;\n  font-family:inherit;resize:vertical;min-height:34px;outline:none;\n  transition:border-color 0.2s;\n}\n.image-pair .pair-caption:focus{border-color:var(--accent)}\n.image-pair .pair-caption::placeholder{color:var(--text-muted)}\n.pair-remove{\n  background:rgba(239,68,68,0.08);border:none;\n  color:var(--error);cursor:pointer;padding:6px 10px;\n  border-radius:6px;font-size:16px;transition:all 0.2s;\n  flex-shrink:0;line-height:1;\n}\n.pair-remove:hover{background:rgba(239,68,68,0.2);transform:scale(1.1)}\n\n/* Upload Options */\n.upload-options{margin-top:16px;display:flex;flex-direction:column;gap:14px}\n.schedule-toggle{display:flex;gap:12px;flex-wrap:wrap;align-items:center}\n.schedule-toggle label{\n  display:flex;align-items:center;gap:7px;font-size:13px;cursor:pointer;\n  padding:8px 16px;background:rgba(255,255,255,0.03);\n  border:1px solid rgba(255,255,255,0.08);border-radius:8px;\n  transition:all 0.2s;font-weight:500;\n}\n.schedule-toggle label:hover{border-color:rgba(247,151,30,0.3)}\n.schedule-toggle input[type="radio"]{accent-color:var(--accent)}\n.schedule-toggle input[type="datetime-local"]{\n  background:rgba(0,0,0,0.3);border:1px solid rgba(255,255,255,0.1);\n  color:var(--text);padding:8px 14px;border-radius:8px;\n  font-size:13px;font-family:inherit;outline:none;\n  transition:border-color 0.2s;\n}\n.schedule-toggle input[type="datetime-local"]:focus{border-color:var(--accent)}\n.upload-actions{display:flex;gap:8px;flex-wrap:wrap}\n\n/* Log Container */\n.log-container{\n  background:rgba(0,0,0,0.35);border:1px solid rgba(255,255,255,0.05);\n  border-radius:12px;padding:14px;max-height:280px;overflow-y:auto;\n  font-family:\'SF Mono\',\'Monaco\',\'Consolas\',monospace;\n  font-size:12px;line-height:1.7;\n}\n.log-container .log-entry{padding:3px 6px;border-radius:4px;transition:background 0.2s;animation:logFade 0.3s ease-out}\n@keyframes logFade{from{opacity:0;transform:translateY(-4px)}to{opacity:1;transform:translateY(0)}}\n.log-container .log-entry:hover{background:rgba(255,255,255,0.03)}\n.log-container .log-entry.success{color:var(--success)}\n.log-container .log-entry.error{color:var(--error)}\n.log-container .log-entry.info{color:var(--info)}\n.log-container .log-entry .ts{color:var(--text-muted);margin-right:8px}\n\n/* Toast */\n.toast-container{\n  position:fixed;top:20px;right:20px;z-index:10000;\n  display:flex;flex-direction:column;gap:8px;max-width:380px;\n}\n.toast{\n  padding:14px 18px;border-radius:12px;\n  backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);\n  font-size:13px;font-weight:500;display:flex;align-items:center;gap:10px;\n  box-shadow:0 10px 40px rgba(0,0,0,0.4);\n  animation:toastIn 0.4s cubic-bezier(0.4,0,0.2,1);\n  cursor:pointer;transition:all 0.3s;\n  border:1px solid rgba(255,255,255,0.08);\n}\n@keyframes toastIn{from{opacity:0;transform:translateX(40px)}to{opacity:1;transform:translateX(0)}}\n@keyframes toastOut{from{opacity:1;transform:translateX(0)}to{opacity:0;transform:translateX(40px)}}\n.toast.success{background:rgba(74,222,128,0.12);border-color:rgba(74,222,128,0.2);color:var(--success)}\n.toast.error{background:rgba(239,68,68,0.12);border-color:rgba(239,68,68,0.2);color:var(--error)}\n.toast.info{background:rgba(96,165,250,0.12);border-color:rgba(96,165,250,0.2);color:var(--info)}\n.toast .toast-icon{font-size:18px}\n\n/* Empty State */\n.empty-state{text-align:center;padding:30px 20px;color:var(--text-muted)}\n.empty-state .empty-icon{font-size:40px;margin-bottom:10px;opacity:0.4}\n.empty-state p{font-size:13px}\n\n/* Scrollbar */\n::-webkit-scrollbar{width:5px}\n::-webkit-scrollbar-track{background:transparent}\n::-webkit-scrollbar-thumb{background:rgba(255,255,255,0.08);border-radius:3px}\n::-webkit-scrollbar-thumb:hover{background:rgba(255,255,255,0.15)}\n\n/* Footer */\n.footer{text-align:center;padding:24px 20px 10px;color:var(--text-muted);font-size:12px;animation:fadeUp 0.5s ease-out 0.5s both}\n.footer span{color:var(--accent);-webkit-text-fill-color:var(--accent)}\n\n/* Responsive */\n@media(max-width:640px){\n  .app-container{padding:12px}\n  .header{padding:24px 12px 20px}\n  .header h1{font-size:24px}\n  .card{padding:16px;border-radius:12px}\n  .stats-grid{grid-template-columns:repeat(3,1fr);gap:6px}\n  .stat-card{padding:12px 8px}\n  .stat-card .stat-value{font-size:18px}\n  .controls-row{gap:6px}\n  .btn{padding:8px 14px;font-size:12px}\n}\n@media(max-width:480px){\n  .stats-grid{grid-template-columns:repeat(2,1fr)}\n  .tabs .tab{font-size:12px;padding:10px 12px}\n  .image-pair{flex-wrap:wrap}\n  .image-pair .pair-img{width:48px;height:48px}\n}\n</style>\n</head>\n<body>\n\n<canvas id="particles-canvas"></canvas>\n<div class="bg-glow bg-glow-1"></div>\n<div class="bg-glow bg-glow-2"></div>\n\n<div class="toast-container" id="toastContainer"></div>\n\n<div class="app-container">\n\n  <header class="header">\n    <span class="logo-icon">&#x1f3ed;</span>\n    <h1>SocialPost Automation</h1>\n    <p class="subtitle">Upload &middot; Schedule &middot; Auto-Post to Facebook</p>\n  </header>\n\n  <div class="tabs">\n    <button class="tab active" onclick="switchTab(\'upload\')" id="tab-upload">&#x1f4e4; Upload &amp; Schedule</button>\n    <button class="tab" onclick="switchTab(\'dashboard\')" id="tab-dashboard">&#x1f4ca; Dashboard &amp; Logs</button>\n  </div>\n\n  <!-- TAB 1: UPLOAD -->\n  <div id="content-upload" class="tab-content active">\n\n    <div class="card">\n      <div class="card-header">\n        <div class="icon">&#x1f5bc;</div>\n        <h2>Upload Images with Captions</h2>\n        <span class="badge" id="pairCountBadge">0 images</span>\n      </div>\n\n      <div class="dropzone" id="multiDropZone" role="button" tabindex="0">\n        <span class="dz-icon">&#x1f4c2;</span>\n        <div class="dz-title">Drop your images here</div>\n        <div class="dz-hint">or <strong>click to browse</strong> &mdash; PNG, JPEG, WEBP</div>\n      </div>\n      <input type="file" id="multiFileInput" accept="image/*" multiple style="display:none">\n\n      <div class="pairs-section" id="imagePairsContainer"></div>\n\n      <div class="upload-options" id="uploadOptions" style="display:none">\n        <div class="controls-row">\n          <label>&#x23f1; Post Interval</label>\n          <select id="uploadInterval">\n            <option value="5">5 minutes</option>\n            <option value="10">10 minutes</option>\n            <option value="15">15 minutes</option>\n            <option value="30" selected>30 minutes</option>\n            <option value="60">1 hour</option>\n            <option value="120">2 hours</option>\n            <option value="360">6 hours</option>\n            <option value="720">12 hours</option>\n            <option value="1440">24 hours</option>\n          </select>\n        </div>\n\n        <div class="schedule-toggle">\n          <label><input type="radio" name="uploadSchedule" value="now" checked onchange="toggleSchedule()"> &#x25b6; Start Now</label>\n          <label><input type="radio" name="uploadSchedule" value="schedule" onchange="toggleSchedule()"> &#x1f4c5; Schedule</label>\n          <input type="datetime-local" id="scheduleDatetime" disabled style="opacity:0.4;pointer-events:none">\n        </div>\n\n        <div class="upload-actions">\n          <button class="btn btn-primary" id="uploadAndStartBtn" onclick="uploadAndStart()">&#x1f680; Upload &amp; Start</button>\n          <button class="btn btn-secondary" id="uploadOnlyBtn" onclick="uploadOnly()">&#x1f4e4; Just Upload</button>\n          <button class="btn btn-ghost btn-xs" onclick="clearAllPairs()" style="margin-left:auto">&#x1f5d1; Clear All</button>\n        </div>\n      </div>\n    </div>\n\n    <div class="card">\n      <div class="card-header">\n        <div class="icon">&#x2139;</div>\n        <h2>Quick Tips</h2>\n      </div>\n      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;font-size:13px;color:var(--text-dim)">\n        <div style="display:flex;gap:8px;align-items:flex-start"><span style="color:var(--accent);font-weight:700">1</span><span>Drag images from WhatsApp or your file manager into the box above</span></div>\n        <div style="display:flex;gap:8px;align-items:flex-start"><span style="color:var(--accent);font-weight:700">2</span><span>Type a caption for each image in the text area below each preview</span></div>\n        <div style="display:flex;gap:8px;align-items:flex-start"><span style="color:var(--accent);font-weight:700">3</span><span>Choose <strong>Start Now</strong> or <strong>Schedule</strong> for later posting</span></div>\n      </div>\n    </div>\n  </div>\n\n  <!-- TAB 2: DASHBOARD -->\n  <div id="content-dashboard" class="tab-content">\n\n    <div class="card">\n      <div class="card-header">\n        <div class="icon">&#x1f4ca;</div>\n        <h2>Batch Status</h2>\n        <span class="badge" id="statusBadge">&#x25cf; Checking...</span>\n      </div>\n\n      <div class="stats-grid">\n        <div class="stat-card"><div class="stat-icon">&#x1f7e2;</div><div class="stat-label">Status</div><div class="stat-value blue" id="statStatus">Idle</div></div>\n        <div class="stat-card"><div class="stat-icon">&#x1f4e6;</div><div class="stat-label">Queued</div><div class="stat-value orange" id="statQueued">0</div></div>\n        <div class="stat-card"><div class="stat-icon">&#x2705;</div><div class="stat-label">Posted</div><div class="stat-value green" id="statPosted">0</div></div>\n        <div class="stat-card"><div class="stat-icon">&#x274c;</div><div class="stat-label">Failed</div><div class="stat-value" id="statFailed" style="color:var(--error)">0</div></div>\n        <div class="stat-card"><div class="stat-icon">&#x23f0;</div><div class="stat-label">Next Run</div><div class="stat-value purple" id="statNextRun" style="font-size:14px">--</div></div>\n        <div class="stat-card"><div class="stat-icon">&#x1f504;</div><div class="stat-label">Interval</div><div class="stat-value yellow" id="statInterval" style="font-size:14px">30 min</div></div>\n        <div class="stat-card"><div class="stat-icon">&#x1f4c5;</div><div class="stat-label">Scheduled</div><div class="stat-value" id="statScheduled" style="font-size:14px;color:var(--text-muted)">None</div></div>\n      </div>\n\n      <div class="controls-row">\n        <label>&#x23f1; Interval</label>\n        <select id="batchInterval" onchange="onIntervalChange()">\n          <option value="5">5 min</option>\n          <option value="15">15 min</option>\n          <option value="30" selected>30 min</option>\n          <option value="60">1 hr</option>\n          <option value="120">2 hr</option>\n          <option value="360">6 hr</option>\n          <option value="720">12 hr</option>\n          <option value="1440">24 hr</option>\n        </select>\n        <button class="btn btn-primary" id="startBtn" onclick="startBatch()">&#x25b6; Start</button>\n        <button class="btn btn-secondary" onclick="pauseBatch()">&#x23f8; Pause</button>\n        <button class="btn btn-danger" onclick="stopBatch()">&#x25a0; Stop</button>\n        <button class="btn btn-secondary btn-xs" onclick="refreshStatus()">&#x1f504;</button>\n      </div>\n    </div>\n\n    <div class="card">\n      <div class="card-header">\n        <div class="icon">&#x1f4dd;</div>\n        <h2>Activity Log</h2>\n        <span class="badge" id="logCount">0 entries</span>\n      </div>\n      <div class="log-container" id="logContainer">\n        <div class="empty-state">\n          <div class="empty-icon">&#x1f4ac;</div>\n          <p>No activity yet. Upload images and start the scheduler!</p>\n        </div>\n      </div>\n    </div>\n  </div>\n\n  <div class="footer">Restaurant Social Automation &mdash; Built with <span>&#x2665;</span></div>\n</div>\n\n<script>\n// PARTICLES\n(function(){\n  const canvas = document.getElementById(\'particles-canvas\');\n  if(!canvas) return;\n  const ctx = canvas.getContext(\'2d\');\n  let particles = [];\n  let mouseX = -1000, mouseY = -1000;\n\n  function resize(){canvas.width = window.innerWidth;canvas.height = window.innerHeight}\n  window.addEventListener(\'resize\', resize);\n  resize();\n\n  document.addEventListener(\'mousemove\', function(e){mouseX = e.clientX;mouseY = e.clientY});\n\n  for(let i = 0; i < 60; i++){\n    particles.push({\n      x: Math.random() * canvas.width,y: Math.random() * canvas.height,\n      vx: (Math.random() - 0.5) * 0.4,vy: (Math.random() - 0.5) * 0.4,\n      r: Math.random() * 2 + 1,alpha: Math.random() * 0.4 + 0.1\n    });\n  }\n\n  function animate(){\n    ctx.clearRect(0, 0, canvas.width, canvas.height);\n    for(let p of particles){\n      p.x += p.vx;p.y += p.vy;\n      if(p.x < 0) p.x = canvas.width;if(p.x > canvas.width) p.x = 0;\n      if(p.y < 0) p.y = canvas.height;if(p.y > canvas.height) p.y = 0;\n      const dx = mouseX - p.x;const dy = mouseY - p.y;\n      if(Math.sqrt(dx*dx + dy*dy) < 150){p.x -= dx * 0.01;p.y -= dy * 0.01}\n      ctx.beginPath();ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);\n      ctx.fillStyle = \'rgba(247, 151, 30, \' + p.alpha + \')\';\n      ctx.fill();\n    }\n    for(let i = 0; i < particles.length; i++){\n      for(let j = i + 1; j < particles.length; j++){\n        const dx = particles[i].x - particles[j].x;\n        const dy = particles[i].y - particles[j].y;\n        const dist = Math.sqrt(dx*dx + dy*dy);\n        if(dist < 120){\n          ctx.beginPath();ctx.moveTo(particles[i].x, particles[i].y);\n          ctx.lineTo(particles[j].x, particles[j].y);\n          ctx.strokeStyle = \'rgba(247, 151, 30, \' + (0.06 * (1 - dist/120)) + \')\';\n          ctx.lineWidth = 0.5;ctx.stroke();\n        }\n      }\n    }\n    requestAnimationFrame(animate);\n  }\n  animate();\n})();\n\n// TAB SWITCHING\nfunction switchTab(tab){\n  document.querySelectorAll(\'.tab\').forEach(t => t.classList.remove(\'active\'));\n  document.querySelectorAll(\'.tab-content\').forEach(t => t.classList.remove(\'active\'));\n  document.getElementById(\'tab-\' + tab).classList.add(\'active\');\n  document.getElementById(\'content-\' + tab).classList.add(\'active\');\n  if(tab === \'dashboard\') refreshStatus();\n}\n\n// TOAST\nfunction showToast(type, msg){\n  const c = document.getElementById(\'toastContainer\');\n  const icons = {success:\'\\u2705\', error:\'\\u274c\', info:\'\\u2139\'};  \n  const t = document.createElement(\'div\');\n  t.className = \'toast \' + type;\n  t.innerHTML = \'<span class="toast-icon">\' + (icons[type]||\'\') + \'</span>\' + msg;\n  c.appendChild(t);\n  setTimeout(() => {t.style.animation = \'toastOut 0.4s ease-in forwards\';setTimeout(() => t.remove(), 400)}, 3500);\n  t.onclick = () => {t.style.animation = \'toastOut 0.3s ease-in forwards\';setTimeout(() => t.remove(), 300)};\n}\n\n// DROPZONE\nconst dz = document.getElementById(\'multiDropZone\');\nconst fi = document.getElementById(\'multiFileInput\');\nconst pc = document.getElementById(\'imagePairsContainer\');\nconst uo = document.getElementById(\'uploadOptions\');\n\ndz.addEventListener(\'click\', () => fi.click());\ndz.addEventListener(\'keydown\', e => { if(e.key===\'Enter\'||e.key===\' \') { e.preventDefault(); fi.click() }});\ndz.addEventListener(\'dragover\', e => {e.preventDefault();dz.classList.add(\'dragover\')});\ndz.addEventListener(\'dragleave\', () => dz.classList.remove(\'dragover\'));\ndz.addEventListener(\'drop\', e => {e.preventDefault();dz.classList.remove(\'dragover\');handleFiles(e.dataTransfer.files)});\nfi.addEventListener(\'change\', () => {handleFiles(fi.files);fi.value = \'\'});\n\nlet fcount = 0;\nfunction handleFiles(files){\n  for(const file of files){\n    if(!file.type.startsWith(\'image/\')) continue;\n    fcount++;\n    const r = new FileReader();\n    r.onload = (e) => {\n      const d = document.createElement(\'div\');\n      d.className = \'image-pair\';d._file = file;\n      d.innerHTML = \'<img class="pair-img" src="\' + e.target.result + \'"><div class="pair-info"><div class="pair-name">\' + file.name + \'</div><textarea class="pair-caption" placeholder="Write caption..." rows="2"></textarea></div><button class="pair-remove" onclick="removePair(this)">&times;</button>\';\n      pc.appendChild(d);updateCount();\n    };\n    r.readAsDataURL(file);\n  }\n}\n\nfunction removePair(btn){\n  const p = btn.closest(\'.image-pair\');\n  p.style.animation = \'slideIn 0.2s ease reverse\';\n  setTimeout(() => {p.remove();updateCount()}, 200);\n}\n\nfunction clearAllPairs(){pc.innerHTML = \'\';updateCount();showToast(\'info\',\'Cleared all\')}\n\nfunction updateCount(){\n  const n = pc.children.length;\n  document.getElementById(\'pairCountBadge\').textContent = n + \' image\' + (n!==1?\'s\':\'\');\n  uo.style.display = n > 0 ? \'flex\' : \'none\';\n}\n\n// SCHEDULE TOGGLE\nfunction toggleSchedule(){\n  const s = document.querySelector("input[name=\'uploadSchedule\']:checked").value === \'schedule\';\n  const d = document.getElementById(\'scheduleDatetime\');\n  d.disabled = !s;d.style.opacity = s?\'1\':\'0.4\';d.style.pointerEvents = s?\'auto\':\'none\';\n  if(s && !d.value){const n=new Date();n.setMinutes(n.getMinutes()+15);d.value=n.toISOString().slice(0,16)}\n}\n\n// UPLOAD & START\nasync function uploadAndStart(){\n  const btn = document.getElementById(\'uploadAndStartBtn\');\n  btn.disabled = true;btn.innerHTML = \'<span class="btn-spinner"></span> Uploading...\';\n  const sched = document.querySelector("input[name=\'uploadSchedule\']:checked").value === \'schedule\';\n  const interval = document.getElementById(\'uploadInterval\').value;\n  const pairs = pc.querySelectorAll(\'.image-pair\');\n  if(pairs.length===0){btn.disabled=false;btn.innerHTML=\'\\u{1f680} Upload & Start\';showToast(\'error\',\'No images\');return}\n  \n  const form = new FormData();\n  for(const p of pairs){\n    const f = p._file;const cap = p.querySelector(\'.pair-caption\').value.trim();\n    if(f){form.append(\'files\',f);form.append(\'captions\',cap||\'\')}\n  }\n  try{\n    const r = await fetch(\'/api/batch/upload-pairs\',{method:\'POST\',body:form});\n    const res = await r.json();\n    if(res.success){\n      showToast(\'success\',\'Uploaded \'+res.count+\' images\');\n      addLog(\'success\',\'Uploaded \'+res.count+\' images\');\n      if(sched){\n        const dt = document.getElementById(\'scheduleDatetime\').value;\n        if(dt){\n          const sr = await fetch(\'/api/batch/schedule\',{method:\'POST\',headers:{\'Content-Type\':\'application/x-www-form-urlencoded\'},body:\'interval=\'+interval+\'&scheduled_at=\'+encodeURIComponent(dt+\':00\')});\n          const sj = await sr.json();\n          if(sj.success){showToast(\'info\',\'Scheduled at \'+dt);addLog(\'info\',\'Scheduled at \'+dt)}else{showToast(\'error\',\'Schedule failed\')}\n        }\n      }else{\n        const sr = await fetch(\'/api/batch/start?interval=\'+interval,{method:\'POST\'});\n        const sj = await sr.json();\n        if(sj.success){showToast(\'success\',\'Batch started!\');addLog(\'success\',\'Started (every \'+interval+\' min)\');switchTab(\'dashboard\')}\n        else{showToast(\'error\',\'Start failed\')}\n      }\n      pc.innerHTML = \'\';updateCount();refreshStatus();\n    }else{showToast(\'error\',\'Upload failed: \'+(res.error||\'Unknown\'))}\n  }catch(err){showToast(\'error\',\'Network error: \'+err.message)}\n  btn.disabled=false;btn.innerHTML=\'\\u{1f680} Upload & Start\';\n}\n\n// UPLOAD ONLY\nasync function uploadOnly(){\n  const btn = document.getElementById(\'uploadOnlyBtn\');\n  btn.disabled = true;btn.innerHTML = \'<span class="btn-spinner light"></span>\';\n  const pairs = pc.querySelectorAll(\'.image-pair\');\n  if(pairs.length===0){btn.disabled=false;btn.innerHTML=\'\\u{1f4e4} Just Upload\';return}\n  const form = new FormData();\n  for(const p of pairs){\n    const f = p._file;const cap = p.querySelector(\'.pair-caption\').value.trim();\n    if(f){form.append(\'files\',f);form.append(\'captions\',cap||\'\')}\n  }\n  try{\n    const r = await fetch(\'/api/batch/upload-pairs\',{method:\'POST\',body:form});\n    const res = await r.json();\n    if(res.success){showToast(\'success\',\'Uploaded \'+res.count+\' images\');addLog(\'success\',\'Uploaded \'+res.count+\' (not started)\');pc.innerHTML=\'\';updateCount();refreshStatus()}\n    else{showToast(\'error\',\'Upload failed\')}\n  }catch(err){showToast(\'error\',\'Network error: \'+err.message)}\n  btn.disabled=false;btn.innerHTML=\'\\u{1f4e4} Just Upload\';\n}\n\n// BATCH CONTROLS\nasync function startBatch(){\n  const i = document.getElementById(\'batchInterval\').value;\n  try{\n    const r = await fetch(\'/api/batch/start?interval=\'+i,{method:\'POST\'});\n    const j = await r.json();\n    if(j.success){showToast(\'success\',\'Started (every \'+i+\' min)\');addLog(\'success\',\'Started (every \'+i+\' min)\')}\n    else{showToast(\'error\',\'Start failed\')}\n    refreshStatus()\n  }catch(err){showToast(\'error\',err.message)}\n}\n\nasync function pauseBatch(){\n  try{\n    const r = await fetch(\'/api/batch/pause\',{method:\'POST\'});\n    const j = await r.json();\n    showToast(j.success?\'info\':\'error\',j.success?\'Paused\':\'Pause failed\');\n    if(j.success) addLog(\'info\',\'Paused\');refreshStatus()\n  }catch(err){showToast(\'error\',err.message)}\n}\n\nasync function stopBatch(){\n  try{\n    const r = await fetch(\'/api/batch/stop\',{method:\'POST\'});\n    const j = await r.json();\n    showToast(j.success?\'info\':\'error\',j.success?\'Stopped\':\'Stop failed\');\n    if(j.success) addLog(\'info\',\'Stopped\');refreshStatus()\n  }catch(err){showToast(\'error\',err.message)}\n}\n\nfunction onIntervalChange(){addLog(\'info\',\'Interval changed to \'+document.getElementById(\'batchInterval\').value+\' min\')}\n\n// STATUS\nasync function refreshStatus(){\n  try{\n    const r = await fetch(\'/api/batch/status\');\n    const d = await r.json();\n    const run = d.running, pause = d.paused;\n    const st = run?\'Running\':pause?\'Paused\':\'Idle\';\n    const sc = run?\'green\':pause?\'yellow\':\'blue\';\n    \n    document.getElementById(\'statStatus\').textContent = st;\n    document.getElementById(\'statStatus\').style.color = run?\'var(--success)\':pause?\'#facc15\':\'var(--info)\';\n    document.getElementById(\'statusBadge\').innerHTML = \'<span class="status-dot \'+(run?\'running\':pause?\'paused\':\'idle\')+\'"></span>\'+st;\n    \n    function up(id,val,cl){const e=document.getElementById(id);const ov=e.textContent;e.textContent=val;if(ov!==String(val)){e.classList.remove(\'pulse\');void e.offsetWidth;e.classList.add(\'pulse\')}if(cl)e.className=\'stat-value \'+cl}\n    up(\'statQueued\',d.queued_pairs||0,\'orange\');\n    up(\'statPosted\',d.posted_count||0,\'green\');\n    up(\'statFailed\',d.failed_count||0,null);\n    document.getElementById(\'statFailed\').style.color = \'var(--error)\';\n    \n    document.getElementById(\'statNextRun\').textContent = d.next_run||\'--\';\n    document.getElementById(\'statNextRun\').className = \'stat-value purple\';\n    const intv = d.interval_minutes||30;\n    document.getElementById(\'statInterval\').textContent = intv+\' min\';\n    document.getElementById(\'statInterval\').className = \'stat-value yellow\';\n    \n    if(d.scheduled_at){document.getElementById(\'statScheduled\').textContent=d.scheduled_at;document.getElementById(\'statScheduled\').style.color=\'var(--info)\'}\n    else{document.getElementById(\'statScheduled\').textContent=\'None\';document.getElementById(\'statScheduled\').style.color=\'var(--text-muted)\'}\n    \n    if(d.interval_minutes) document.getElementById(\'batchInterval\').value = d.interval_minutes;\n    \n    if(d.logs && d.logs.length > 0){\n      const lc = document.getElementById(\'logContainer\');lc.innerHTML = \'\';\n      for(const l of d.logs.slice(-100)){\n        const e = document.createElement(\'div\');\n        let cls = \'log-entry\';\n        if(l.includes(\'Posted\')||l.includes(\'success\')) cls+=\' success\';\n        else if(l.includes(\'Error\')||l.includes(\'Failed\')||l.includes(\'error\')) cls+=\' error\';\n        else if(l.includes(\'Start\')||l.includes(\'added\')||l.includes(\'Schedule\')||l.includes(\'Interval\')) cls+=\' info\';\n        e.className = cls;\n        const n = new Date();\n        e.innerHTML = \'<span class="ts">[\'+n.toLocaleTimeString()+\']</span>\'+l;\n        lc.appendChild(e);\n      }\n      lc.scrollTop = lc.scrollHeight;\n      document.getElementById(\'logCount\').textContent = d.logs.length+\' entries\';\n    }\n  }catch(e){}\n}\n\nfunction addLog(type, msg){\n  const lc = document.getElementById(\'logContainer\');\n  if(lc.children.length===1&&lc.children[0].classList.contains(\'empty-state\')) lc.innerHTML=\'\';\n  const e = document.createElement(\'div\');\n  e.className = \'log-entry \'+type;\n  const n = new Date();\n  e.innerHTML = \'<span class="ts">[\'+n.toLocaleTimeString()+\']</span>\'+msg;\n  lc.appendChild(e);lc.scrollTop = lc.scrollHeight;\n  document.getElementById(\'logCount\').textContent = lc.querySelectorAll(\'.log-entry\').length+\' entries\';\n}\n\nsetInterval(refreshStatus, 5000);\nsetTimeout(refreshStatus, 500);\n</script>\n</body>\n</html>\n'
