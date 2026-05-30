# ============================================
# Restaurant Social Media Automation
# Dockerfile - Multi-stage build
# ============================================

# ---- Base Image ----
FROM python:3.11-slim AS base

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-hin \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---- Development Image ----
FROM base AS development

RUN pip install --no-cache-dir "rembg[cpu]"

# Copy source code
COPY . .

EXPOSE 8000

CMD ["uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ---- Production Image ----
FROM base AS production

RUN pip install --no-cache-dir "rembg[cpu]"

COPY . .

EXPOSE 8000

CMD ["uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8000"]

# ---- Full Image (with ComfyUI support) ----
FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04 AS full

# Install Python and system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3-pip \
    tesseract-ocr \
    tesseract-ocr-eng \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    git \
    curl \
    wget \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt
RUN pip3 install --no-cache-dir "rembg[gpu]"

# Copy app
COPY . .

# Clone ComfyUI (optional, can be mounted as volume)
RUN git clone https://github.com/comfyanonymous/ComfyUI /comfyui || true

EXPOSE 8000 8188

# Start both ComfyUI and the automation API
CMD ["sh", "-c", "cd /comfyui && python main.py --listen 0.0.0.0 --port 8188 & uvicorn api.app:app --host 0.0.0.0 --port 8000"]
