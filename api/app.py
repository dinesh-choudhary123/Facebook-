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


# --- Web Interface HTML (single-page app) ---

INDEX_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Restaurant Social Media Automation</title>
    <style>
        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: #0f0f11;
            color: #e0e0e0;
            min-height: 100vh;
            line-height: 1.6;
        }
        .container {
            max-width: 900px;
            margin: 0 auto;
            padding: 2rem;
        }
        header {
            text-align: center;
            margin-bottom: 2.5rem;
            padding: 2rem 0;
            border-bottom: 1px solid #2a2a2e;
        }
        h1 {
            font-size: 2rem;
            font-weight: 700;
            background: linear-gradient(135deg, #f7971e, #ffd200);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.5rem;
        }
        .subtitle {
            color: #888;
            font-size: 0.95rem;
        }
        .card {
            background: #1a1a1e;
            border-radius: 12px;
            padding: 1.5rem;
            margin-bottom: 1.5rem;
            border: 1px solid #2a2a2e;
        }
        .card h2 {
            font-size: 1.1rem;
            margin-bottom: 1rem;
            color: #ffd200;
        }
        .upload-zone {
            border: 2px dashed #3a3a3e;
            border-radius: 12px;
            padding: 3rem 2rem;
            text-align: center;
            cursor: pointer;
            transition: all 0.3s;
        }
        .upload-zone:hover, .upload-zone.dragover {
            border-color: #ffd200;
            background: rgba(255, 210, 0, 0.05);
        }
        .upload-zone.has-image {
            border-color: #4caf50;
            background: rgba(76, 175, 80, 0.05);
        }
        .upload-icon {
            font-size: 3rem;
            margin-bottom: 1rem;
        }
        .upload-text {
            color: #888;
        }
        .upload-text strong {
            color: #ffd200;
        }
        .preview-container {
            display: none;
            margin-top: 1rem;
        }
        .preview-container img {
            max-width: 100%;
            max-height: 300px;
            border-radius: 8px;
            margin: 0 auto;
            display: block;
        }
        .preview-container.visible {
            display: block;
        }
        .form-group {
            margin-bottom: 1rem;
        }
        .form-group label {
            display: block;
            margin-bottom: 0.5rem;
            color: #aaa;
            font-size: 0.9rem;
        }
        .form-group input[type="text"] {
            width: 100%;
            padding: 0.75rem 1rem;
            border-radius: 8px;
            border: 1px solid #3a3a3e;
            background: #252529;
            color: #e0e0e0;
            font-size: 1rem;
        }
        .form-group input[type="text"]:focus {
            outline: none;
            border-color: #ffd200;
        }
        .checkbox-group {
            display: flex;
            gap: 2rem;
            flex-wrap: wrap;
        }
        .checkbox-group label {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            cursor: pointer;
            color: #ccc;
        }
        .checkbox-group input[type="checkbox"] {
            accent-color: #ffd200;
            width: 18px;
            height: 18px;
        }
        button {
            width: 100%;
            padding: 1rem;
            background: linear-gradient(135deg, #f7971e, #ffd200);
            color: #000;
            border: none;
            border-radius: 10px;
            font-size: 1.1rem;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s, opacity 0.2s;
        }
        button:hover {
            transform: translateY(-1px);
            opacity: 0.95;
        }
        button:disabled {
            opacity: 0.5;
            cursor: not-allowed;
            transform: none;
        }
        .status-section {
            display: none;
        }
        .status-section.visible {
            display: block;
        }
        .progress-bar-container {
            background: #2a2a2e;
            border-radius: 20px;
            height: 8px;
            margin: 1rem 0;
            overflow: hidden;
        }
        .progress-bar {
            height: 100%;
            background: linear-gradient(135deg, #f7971e, #ffd200);
            width: 0%;
            border-radius: 20px;
            transition: width 0.5s;
        }
        .log-container {
            background: #0a0a0c;
            border-radius: 8px;
            padding: 1rem;
            max-height: 200px;
            overflow-y: auto;
            font-family: 'SF Mono', 'Fira Code', monospace;
            font-size: 0.85rem;
            color: #888;
        }
        .log-container .log-entry {
            padding: 2px 0;
            border-bottom: 1px solid #1a1a1e;
        }
        .log-container .log-entry:last-child {
            border-bottom: none;
        }
        .result-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1rem;
        }
        .result-item {
            background: #252529;
            border-radius: 8px;
            padding: 1rem;
        }
        .result-item h3 {
            font-size: 0.85rem;
            color: #888;
            margin-bottom: 0.5rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }
        .result-item .value {
            font-size: 0.95rem;
            color: #e0e0e0;
            word-break: break-word;
        }
        .result-image {
            width: 100%;
            border-radius: 8px;
            margin-top: 1rem;
        }
        .step-list {
            margin: 1rem 0;
        }
        .step-item {
            display: flex;
            align-items: center;
            gap: 0.75rem;
            padding: 0.5rem 0;
            border-bottom: 1px solid #2a2a2e;
        }
        .step-status {
            width: 24px;
            height: 24px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 0.8rem;
        }
        .step-status.success { background: #4caf50; color: white; }
        .step-status.failed { background: #f44336; color: white; }
        .step-status.skipped { background: #757575; color: white; }
        .step-status.running { background: #ff9800; color: white; animation: pulse 1s infinite; }
        .step-name { color: #ccc; }
        .step-duration { color: #666; font-size: 0.85rem; margin-left: auto; }
        .badge {
            display: inline-block;
            padding: 0.25rem 0.75rem;
            border-radius: 20px;
            font-size: 0.85rem;
            font-weight: 500;
        }
        .badge.success { background: rgba(76, 175, 80, 0.2); color: #4caf50; }
        .badge.partial { background: rgba(255, 152, 0, 0.2); color: #ff9800; }
        .badge.failed { background: rgba(244, 67, 54, 0.2); color: #f44336; }
        .api-status {
            display: flex;
            gap: 1rem;
            flex-wrap: wrap;
            margin-bottom: 1rem;
        }
        .api-chip {
            padding: 0.3rem 0.75rem;
            border-radius: 20px;
            font-size: 0.8rem;
            border: 1px solid #3a3a3e;
        }
        .api-chip.configured { border-color: #4caf50; color: #4caf50; }
        .api-chip.missing { border-color: #f44336; color: #f44336; }
        .api-chip a { color: inherit; text-decoration: none; }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
        @media (max-width: 600px) {
            .container { padding: 1rem; }
            .result-grid { grid-template-columns: 1fr; }
            .checkbox-group { flex-direction: column; gap: 0.5rem; }
        }
            .image-pairs-container {
            display: flex;
            flex-direction: column;
            gap: 0.75rem;
            margin-top: 1rem;
        }
        .image-pair {
            display: flex;
            gap: 1rem;
            background: #252529;
            border-radius: 10px;
            padding: 0.75rem;
            align-items: flex-start;
            border: 1px solid #3a3a3e;
            transition: border-color 0.2s;
        }
        .image-pair:hover {
            border-color: #ffd200;
        }
        .pair-image {
            flex-shrink: 0;
            width: 120px;
            height: 90px;
            border-radius: 8px;
            overflow: hidden;
            background: #1a1a1e;
            display: flex;
            align-items: center;
            justify-content: center;
            border: 1px solid #3a3a3e;
        }
        .pair-image img {
            width: 100%;
            height: 100%;
            object-fit: cover;
        }
        .pair-image .no-image {
            color: #555;
            font-size: 0.75rem;
            text-align: center;
            padding: 0.5rem;
        }
        .pair-caption {
            flex: 1;
            min-width: 0;
        }
        .pair-caption .pair-filename {
            font-size: 0.8rem;
            color: #888;
            margin-bottom: 0.3rem;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .pair-caption textarea {
            width: 100%;
            padding: 0.6rem 0.8rem;
            border-radius: 8px;
            border: 1px solid #3a3a3e;
            background: #1a1a1e;
            color: #e0e0e0;
            font-size: 0.9rem;
            font-family: inherit;
            resize: vertical;
            min-height: 60px;
            box-sizing: border-box;
            transition: border-color 0.2s;
        }
        .pair-caption textarea:focus {
            outline: none;
            border-color: #ffd200;
        }
        .pair-caption textarea::placeholder {
            color: #555;
        }
        .pair-remove {
            flex-shrink: 0;
            width: 28px;
            height: 28px;
            border-radius: 50%;
            border: 1px solid #5a3a3a;
            background: transparent;
            color: #f44336;
            cursor: pointer;
            font-size: 0.9rem;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.2s;
            padding: 0;
        }
        .pair-remove:hover {
            background: rgba(244, 67, 54, 0.15);
            border-color: #f44336;
        }
        .upload-counter {
            text-align: center;
            color: #888;
            font-size: 0.85rem;
            margin-top: 0.5rem;
        }
        @media (max-width: 600px) {
            .image-pair {
                flex-direction: column;
            }
            .pair-image {
                width: 100%;
                height: 150px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🍽️ Restaurant Social Automation</h1>
            <p class="subtitle">Upload a poster → AI captions (Groq) → Post directly to Facebook</p>
        </header>

        <div class="card">
            <h2>🔌 API Status</h2>
            <div class="api-status" id="apiStatus">
                <span class="api-chip" id="groqStatus">Loading...</span>
                <span class="api-chip" id="geminiStatus">Loading...</span>
                <span class="api-chip" id="fbStatus">Loading...</span>

            </div>
        </div>

        <div class="card">
            <h2>📤 Upload Poster Image</h2>
            <form id="uploadForm">
                <div class="upload-zone" id="dropZone">
                    <div class="upload-icon">📸</div>
                    <div class="upload-text">
                        <strong>Click to upload</strong> or drag and drop<br>
                        <span id="fileInfo">Supports: JPG, PNG, WebP (up to 20MB)</span>
                    </div>
                    <input type="file" id="fileInput" accept="image/*" style="display:none">
                </div>
                <div class="preview-container" id="previewContainer">
                    <img id="previewImage" src="" alt="Preview">
                </div>

                <div class="form-group" style="margin-top:1rem">
                    <label for="restaurantName">Restaurant Name (optional)</label>
                    <input type="text" id="restaurantName" placeholder="e.g., Pizza Paradise">
                </div>

                <div class="form-group">
                    <label>Options</label>
                    <div class="checkbox-group">
                        <label>
                            <input type="checkbox" id="postToFacebook" checked>
                            Post to Facebook
                        </label>
        
                    </div>
                </div>

                <button type="submit" id="processBtn">🚀 Run Automation Pipeline</button>
            </form>
        </div>

        <div class="card status-section" id="statusSection">
            <h2>📊 Pipeline Status</h2>
            <div class="progress-bar-container">
                <div class="progress-bar" id="progressBar"></div>
            </div>
            <div class="step-list" id="stepList"></div>
            <div class="log-container" id="logContainer"></div>
        </div>

        <!-- ── Batch Automation Section ── -->
        <div class="card">
            <h2>🤖 Batch Automation</h2>
            <p style="color:#888;font-size:0.9rem;margin-bottom:1rem">
                Drop images + .txt caption files in the <code style="background:#252529;padding:2px 6px;border-radius:4px">batch/</code> folder.
                The system posts them one by one every 30 minutes, then deletes used files.
            </p>

            <div class="batch-info" style="display:flex;gap:1rem;flex-wrap:wrap;margin-bottom:1rem">
                <div class="result-item" style="flex:1;min-width:120px">
                    <h3>Status</h3>
                    <div class="value" id="batchStatus" style="font-weight:600">⏹️ Stopped</div>
                </div>
                <div class="result-item" style="flex:1;min-width:120px">
                    <h3>Queued</h3>
                    <div class="value" id="batchQueued">0 pairs</div>
                </div>
                <div class="result-item" style="flex:1;min-width:120px">
                    <h3>Posted</h3>
                    <div class="value" id="batchPosted">0</div>
                </div>
                <div class="result-item" style="flex:1;min-width:120px">
                    <h3>Next Run</h3>
                    <div class="value" id="batchNextRun">—</div>
                </div>
            </div>

            <div class="checkbox-group" style="margin-bottom:1rem">
                <label>
                    Interval:
                    <select id="batchInterval" style="background:#252529;color:#e0e0e0;border:1px solid #3a3a3e;padding:0.4rem 0.8rem;border-radius:8px;font-size:0.9rem">
                        <option value="15">15 min</option>
                        <option value="30" selected>30 min</option>
                        <option value="60">1 hour</option>
                        <option value="120">2 hours</option>
                        <option value="360">6 hours</option>
                        <option value="720">12 hours</option>
                        <option value="1440">24 hours</option>
                    </select>
                </label>
            </div>

            <div class="checkbox-group" style="margin-bottom:1rem">
                <button id="batchStartBtn" class="btn-success" style="flex:1;background:linear-gradient(135deg,#4caf50,#2e7d32);color:white">▶️ Start Batch</button>
                <button id="batchPauseBtn" style="flex:1;background:linear-gradient(135deg,#ff9800,#e65100);color:white">⏸️ Pause</button>
                <button id="batchSkipBtn" style="flex:1;background:linear-gradient(135deg,#9e9e9e,#616161);color:white">⏭️ Skip Current</button>
                <button id="batchStopBtn" style="flex:1;background:linear-gradient(135deg,#f44336,#b71c1c);color:white">⏹️ Stop</button>
            </div>

            <div class="batch-logs" id="batchLogSection" style="display:none">
                <h3 style="color:#aaa;font-size:0.9rem;margin-bottom:0.5rem">📋 Activity Log</h3>
                <div class="log-container" id="batchLogs" style="max-height:150px"></div>
            </div>
            <div class="batch-history" id="batchHistorySection" style="display:none;margin-top:1rem">
                <h3 style="color:#aaa;font-size:0.9rem;margin-bottom:0.5rem">📜 Post History</h3>
                <div id="batchHistory"></div>
            </div>
        <!-- ── Multi-Image Upload Section ── -->
        <div class="card">
            <h2>📤 Multi-Image Batch Upload</h2>
            <p style="color:#888;font-size:0.9rem;margin-bottom:1rem">
                Upload images and paste their WhatsApp captions. They'll be saved to the batch folder
                and posted one by one at your chosen interval. <strong>No manual .txt files needed!</strong>
            </p>

            <div class="upload-zone" id="multiDropZone" style="margin-bottom:1rem">
                <div class="upload-icon">🖼️</div>
                <div class="upload-text">
                    <strong>Click to select images</strong> or drag & drop from WhatsApp<br>
                    <span>Multiple images supported — add captions below</span>
                </div>
                <input type="file" id="multiFileInput" accept="image/*" multiple style="display:none">
            </div>

            <div id="imagePairsContainer" class="image-pairs-container"></div>

            <div class="upload-counter" id="uploadCounter">No images added yet</div>

            <div style="display:flex;gap:1rem;align-items:center;margin-top:1rem;flex-wrap:wrap">
                <label style="color:#aaa;font-size:0.9rem">
                    Post Interval:
                    <select id="uploadInterval" style="background:#252529;color:#e0e0e0;border:1px solid #3a3a3e;padding:0.4rem 0.8rem;border-radius:8px;font-size:0.9rem;margin-left:0.5rem">
                        <option value="15">15 min</option>
                        <option value="30" selected>30 min</option>
                        <option value="45">45 min</option>
                        <option value="60">1 hour</option>
                        <option value="120">2 hours</option>
                    </select>
                </label>
                <button id="uploadAndStartBtn" style="flex:1;background:linear-gradient(135deg,#4caf50,#2e7d32);color:white;min-width:200px">
                    🚀 Upload & Start Scheduled Posting
                </button>
            </div>
            <div id="uploadStatus" style="margin-top:1rem;color:#888;font-size:0.9rem;display:none"></div>
        </div>

        <div class="card status-section" id="resultSection">
            <h2>✅ Results</h2>
            <div id="resultContent"></div>
        </div>
    </div>

    <script>
        // Load API status
        fetch('/api/config')
            .then(r => r.json())
            .then(data => {
                const gc = data.config || {};
                document.getElementById('groqStatus').innerHTML = gc.groq_available
                    ? '✅ Groq API' : '<a href="https://console.groq.com" target="_blank">❌ Groq API</a>';
                document.getElementById('geminiStatus').innerHTML = gc.gemini_available
                    ? '✅ Gemini API' : '<a href="https://aistudio.google.com/app/apikey" target="_blank">❌ Gemini API</a>';
                document.getElementById('fbStatus').innerHTML = gc.facebook_configured
                    ? '✅ Facebook' : '<a href="https://developers.facebook.com/" target="_blank">❌ Facebook</a>';

            });

        // Drag & drop upload
        const dropZone = document.getElementById('dropZone');
        const fileInput = document.getElementById('fileInput');
        const previewContainer = document.getElementById('previewContainer');
        const previewImage = document.getElementById('previewImage');
        const fileInfo = document.getElementById('fileInfo');

        dropZone.addEventListener('click', () => fileInput.click());
        dropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropZone.classList.add('dragover');
        });
        dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
        dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropZone.classList.remove('dragover');
            if (e.dataTransfer.files.length) {
                fileInput.files = e.dataTransfer.files;
                handleFileSelect(e.dataTransfer.files[0]);
            }
        });
        fileInput.addEventListener('change', () => {
            if (fileInput.files.length) handleFileSelect(fileInput.files[0]);
        });

        function handleFileSelect(file) {
            if (!file.type.startsWith('image/')) return;
            fileInfo.textContent = `📄 ${file.name} (${(file.size / 1024).toFixed(1)} KB)`;
            dropZone.classList.add('has-image');
            previewContainer.classList.add('visible');
            const reader = new FileReader();
            reader.onload = (e) => { previewImage.src = e.target.result; };
            reader.readAsDataURL(file);
        }

        // Form submission
        document.getElementById('uploadForm').addEventListener('submit', async (e) => {
            e.preventDefault();

            const file = fileInput.files[0];
            if (!file) { alert('Please select an image first!'); return; }

            const form = new FormData();
            form.append('file', file);
            form.append('restaurant_name', document.getElementById('restaurantName').value);
            form.append('post_to_facebook', document.getElementById('postToFacebook').checked);


            // Show status section
            const statusSection = document.getElementById('statusSection');
            const resultSection = document.getElementById('resultSection');
            statusSection.classList.add('visible');
            resultSection.classList.remove('visible');
            document.getElementById('processBtn').disabled = true;
            document.getElementById('processBtn').textContent = '⏳ Processing...';
            document.getElementById('progressBar').style.width = '0%';

            const stepList = document.getElementById('stepList');
            const logContainer = document.getElementById('logContainer');
            stepList.innerHTML = '';
            logContainer.innerHTML = '';

            // Simplified steps
            const steps = ['OCR Extraction', 'Caption Generation', 'Facebook Post'];
            steps.forEach((name, i) => {
                const div = document.createElement('div');
                div.className = 'step-item';
                div.id = 'step-' + i;
                div.innerHTML = `
                    <div class="step-status" id="status-${i}">⏳</div>
                    <span class="step-name">${name}</span>
                    <span class="step-duration" id="duration-${i}"></span>
                `;
                stepList.appendChild(div);
            });

            try {
                const resp = await fetch('/api/process', { method: 'POST', body: form });
                const result = await resp.json();

                // Show progress
                document.getElementById('progressBar').style.width = '100%';

                // Update step statuses
                if (result.steps) {
                    result.steps.forEach((step, i) => {
                        if (i < steps.length) {
                            const statusEl = document.getElementById('status-' + i);
                            statusEl.className = 'step-status ' + step.status;
                            statusEl.textContent = step.status === 'success' ? '✓' :
                                                     step.status === 'failed' ? '✗' :
                                                     step.status === 'skipped' ? '–' : '…';
                            document.getElementById('duration-' + i).textContent =
                                step.duration_seconds ? step.duration_seconds.toFixed(1) + 's' : '';
                        }
                    });
                }

                // Show logs
                if (result.logs) {
                    result.logs.forEach(log => {
                        const div = document.createElement('div');
                        div.className = 'log-entry';
                        div.textContent = log;
                        logContainer.appendChild(div);
                    });
                    logContainer.scrollTop = logContainer.scrollHeight;
                }

                // Show result
                const content = document.getElementById('resultContent');
                const statusBadge = result.status === 'success' ? 'success' :
                                    result.status === 'partial' ? 'partial' : 'failed';

                let html = `<p><span class="badge ${statusBadge}">${result.status.toUpperCase()}</span></p>`;

                if (result.final_image_url) {
                    html += `<img src="${result.final_image_url}" class="result-image" alt="Final poster">`;
                }

                if (result.captions) {
                    html += `
                        <div class="result-grid" style="margin-top:1rem">
                            <div class="result-item">
                                <h3>Short Caption</h3>
                                <div class="value">${result.captions.short_caption || '-'}</div>
                            </div>
                            <div class="result-item">
                                <h3>Long Caption</h3>
                                <div class="value">${result.captions.long_caption || '-'}</div>
                            </div>
                            <div class="result-item">
                                <h3>Hashtags</h3>
                                <div class="value">${result.captions.hashtags || '-'}</div>
                            </div>
                            <div class="result-item">
                                <h3>Call to Action</h3>
                                <div class="value">${result.captions.cta || '-'}</div>
                            </div>
                        </div>
                    `;
                }

                if (result.facebook_result) {
                    const fb = result.facebook_result;
                    html += `
                        <div class="result-item" style="margin-top:1rem">
                            <h3>Facebook Post</h3>
                            <div class="value">
                                ${fb.success
                                    ? `<a href="${fb.post_url}" target="_blank">✅ Posted! View on Facebook →</a>`
                                    : `❌ Failed: ${fb.error || 'Unknown error'}`
                                }
                            </div>
                        </div>
                        <p style="margin-top:1rem;font-size:0.85rem;color:#888">
                            Post ID: ${fb.post_id || 'N/A'}
                        </p>
                    `;
                }

                if (result.extracted_data) {
                    html += `
                        <div class="result-item" style="margin-top:1rem">
                            <h3>Extracted Text</h3>
                            <div class="value">
                                <strong>Food:</strong> ${result.extracted_data.food_title || 'N/A'}<br>
                                <strong>Offer:</strong> ${result.extracted_data.offer_text || 'N/A'}<br>
                                <strong>Prices:</strong> ${(result.extracted_data.pricing || []).join(', ') || 'N/A'}
                            </div>
                        </div>
                    `;
                }

                if (result.error) {
                    html += `<p style="color:#f44336;margin-top:1rem">Error: ${result.error}</p>`;
                }

                content.innerHTML = html;
                resultSection.classList.add('visible');

            } catch (err) {
                logContainer.innerHTML += `<div class="log-entry" style="color:#f44336">Error: ${err.message}</div>`;
            }

            document.getElementById('processBtn').disabled = false;
            document.getElementById('processBtn').textContent = '🚀 Run Automation Pipeline';
        });

        // ── Batch Automation Controls ──
        let batchRefreshInterval = null;

        function updateBatchStatus() {
            fetch('/api/batch/status')
                .then(r => r.json())
                .then(data => {
                    const statusEl = document.getElementById('batchStatus');
                    const isRunning = data.running && !data.paused;
                    const isPaused = data.running && data.paused;

                    if (isRunning) statusEl.innerHTML = '▶️ Running';
                    else if (isPaused) statusEl.innerHTML = '⏸️ Paused';
                    else statusEl.innerHTML = '⏹️ Stopped';

                    document.getElementById('batchQueued').textContent = data.queued_pairs + ' pairs';
                    document.getElementById('batchPosted').textContent = data.posted_count;
                    document.getElementById('batchNextRun').textContent =
                        data.next_run ? new Date(data.next_run).toLocaleTimeString() : '—';

                    // Toggle buttons
                    document.getElementById('batchStartBtn').disabled = data.running;
                    document.getElementById('batchPauseBtn').disabled = !data.running || data.paused;
                    document.getElementById('batchSkipBtn').disabled = !data.running;
                    document.getElementById('batchStopBtn').disabled = !data.running;

                    // Show current job
                    if (data.current_job) {
                        statusEl.innerHTML = '📤 Posting: ' + data.current_job.image_name;
                    }

                    // Show logs
                    const logSection = document.getElementById('batchLogSection');
                    const logContainer = document.getElementById('batchLogs');
                    if (data.logs && data.logs.length > 0) {
                        logSection.style.display = 'block';
                        logContainer.innerHTML = data.logs.map(log =>
                            `<div class="log-entry">${log}</div>`
                        ).join('');
                        logContainer.scrollTop = logContainer.scrollHeight;
                    }

                    // Show history
                    const historySection = document.getElementById('batchHistorySection');
                    const historyContainer = document.getElementById('batchHistory');
                    if (data.history && data.history.length > 0) {
                        historySection.style.display = 'block';
                        historyContainer.innerHTML = data.history.map(h => {
                            const icon = h.status === 'success' ? '✅' : h.status === 'failed' ? '❌' : '⏭️';
                            const time = h.ended_at ? new Date(h.ended_at).toLocaleTimeString() : '';
                            return `<div class="step-item">
                                <span>${icon}</span>
                                <span class="step-name">${h.image_name}</span>
                                <span class="step-duration">${time}</span>
                            </div>`;
                        }).join('');
                    }
                });
        }

        document.getElementById('batchStartBtn').addEventListener('click', () => {
            const interval = parseInt(document.getElementById('batchInterval').value);
            fetch('/api/batch/start', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({interval: interval})
            }).then(r => r.json()).then(data => {
                if (data.success) updateBatchStatus();
                else alert('Error: ' + data.message);
            });
        });

        document.getElementById('batchPauseBtn').addEventListener('click', () => {
            fetch('/api/batch/pause', {method: 'POST'})
                .then(r => r.json())
                .then(data => { if (data.success) updateBatchStatus(); });
        });

        document.getElementById('batchSkipBtn').addEventListener('click', () => {
            fetch('/api/batch/skip', {method: 'POST'})
                .then(r => r.json())
                .then(data => { if (data.success) updateBatchStatus(); });
        });

        document.getElementById('batchStopBtn').addEventListener('click', () => {
            fetch('/api/batch/stop', {method: 'POST'})
                .then(r => r.json())
                .then(data => {
                    if (data.success) {
                        if (batchRefreshInterval) clearInterval(batchRefreshInterval);
                        batchRefreshInterval = null;
                        updateBatchStatus();
                    }
                });
        });

        // Poll batch status every 5 seconds if running
        setInterval(() => {
            fetch('/api/batch/status')
                .then(r => r.json())
                .then(data => {
                    if (data.running) updateBatchStatus();
                });
        }, 5000);

        // Initial load
        updateBatchStatus();
    
        // ── Multi-Image Upload ──
        const multiDropZone = document.getElementById('multiDropZone');
        const multiFileInput = document.getElementById('multiFileInput');
        const pairsContainer = document.getElementById('imagePairsContainer');
        const uploadCounter = document.getElementById('uploadCounter');
        const uploadStatus = document.getElementById('uploadStatus');
        multiDropZone.addEventListener('click', () => multiFileInput.click());
        multiDropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            multiDropZone.classList.add('dragover');
        });
        multiDropZone.addEventListener('dragleave', () => multiDropZone.classList.remove('dragover'));
        multiDropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            multiDropZone.classList.remove('dragover');
            if (e.dataTransfer.files.length) {
                handleSelectedFiles(e.dataTransfer.files);
            }
        });
        multiFileInput.addEventListener('change', () => {
            if (multiFileInput.files.length) {
                handleSelectedFiles(multiFileInput.files);
                multiFileInput.value = '';
            }
        });

        function handleSelectedFiles(files) {
            Array.from(files).forEach(file => {
                if (!file.type.startsWith('image/')) return;
                addImagePair(file);
            });
            updateUploadCounter();
        }

        function addImagePair(file) {
            const url = URL.createObjectURL(file);
            const div = document.createElement('div');
            div.className = 'image-pair';
            div._file = file;  // Store file reference directly on element
            div.innerHTML = `
                <div class="pair-image">
                    <img src="${url}" alt="${file.name.replace(/["<>]/g, '')}">
                </div>
                <div class="pair-caption">
                    <div class="pair-filename">${file.name.replace(/["<>]/g, '')}</div>
                    <textarea placeholder="Paste WhatsApp caption here... (63,206 chars, emojis supported)" rows="3"></textarea>
                </div>
                <button class="pair-remove" onclick="this.closest('.image-pair').remove(); updateUploadCounter();" title="Remove">✕</button>
            `;
            pairsContainer.appendChild(div);
        }



        function updateUploadCounter() {
            const count = document.querySelectorAll('.image-pair').length;
            uploadCounter.textContent = count === 0
                ? 'No images added yet'
                : count + ' image' + (count > 1 ? 's' : '') + ' ready to post';
        }

        document.getElementById('uploadAndStartBtn').addEventListener('click', async () => {
            const pairs = document.querySelectorAll('.image-pair');
            if (pairs.length === 0) {
                alert('Please add at least one image first!');
                return;
            }

            const form = new FormData();
            let validCount = 0;

            pairs.forEach(pair => {
                const file = pair._file;
                if (!file) return;
                const caption = pair.querySelector('textarea').value.trim();
                form.append('files', file);
                form.append('captions', caption || '');
                validCount++;
            });

            if (validCount === 0) {
                alert('No valid images to upload!');
                return;
            }

            const btn = document.getElementById('uploadAndStartBtn');
            btn.disabled = true;
            btn.textContent = '⏳ Uploading ' + validCount + ' images...';
            uploadStatus.style.display = 'block';
            uploadStatus.textContent = '📤 Uploading ' + validCount + ' image' + (validCount > 1 ? 's' : '') + '...';
            uploadStatus.style.color = '#ffd200';

            try {
                const resp = await fetch('/api/batch/upload-pairs', { method: 'POST', body: form });
                const data = await resp.json();

                if (data.success && data.success_count > 0) {
                    uploadStatus.textContent = '✅ ' + data.success_count + ' of ' + data.total + ' uploaded! Starting batch posting...';
                    uploadStatus.style.color = '#4caf50';

                    // Now start the batch scheduler
                    const interval = parseInt(document.getElementById('uploadInterval').value);
                    const startResp = await fetch('/api/batch/start', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({interval: interval})
                    });
                    const startData = await startResp.json();

                    if (startData.success) {
                        uploadStatus.textContent = '🚀 Batch started! ' + data.success_count + ' images will post every ' + interval + ' minutes.';
                    } else {
                        uploadStatus.textContent = '✅ Uploaded but could not start batch: ' + startData.message;
                    }

                    // Clear the form
                    pairsContainer.innerHTML = '';
                    updateUploadCounter();

                    // Refresh batch status display
                    if (typeof updateBatchStatus === 'function') updateBatchStatus();
                } else {
                    uploadStatus.textContent = '❌ Upload failed. Please try again.';
                    uploadStatus.style.color = '#f44336';
                }
            } catch (err) {
                uploadStatus.textContent = '❌ Error: ' + err.message;
                uploadStatus.style.color = '#f44336';
            }

            btn.disabled = false;
            btn.textContent = '🚀 Upload & Start Scheduled Posting';
        });
    </script>
</body>
</html>
"""
