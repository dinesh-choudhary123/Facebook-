# GPU Recommendations & Optimization Guide

## Why GPU Matters

| Task | CPU | GPU | Speedup |
|------|-----|-----|---------|
| SDXL Image Generation | 2-5 minutes | 10-30 seconds | 10-15x |
| Background Removal (rembg) | 5-15 seconds | 1-3 seconds | 3-5x |
| ComfyUI Workflow | Unusable without GPU | Real-time | Essential |

## Recommended GPUs

### Minimum (SDXL Base)
- **NVIDIA RTX 3060 12GB** ($250-300 used)
  - SDXL: ~30s per image
  - 1080x1080 generation
  - Can run SDXL + ControlNet

### Recommended
- **NVIDIA RTX 4070 12GB** ($500-550)
  - SDXL: ~15s per image
  - SDXL + ControlNet + IP-Adapter simultaneously
  - Supports FP16 inference

### Best Value
- **NVIDIA RTX 3090 24GB** ($700-900 used)
  - SDXL: ~8-10s per image
  - Can run SDXL Turbo for real-time generation
  - Plenty of VRAM for complex workflows

### Professional
- **NVIDIA RTX 4090 24GB** ($1600-1800)
  - SDXL: ~5-7s per image
  - Can run SDXL + multiple ControlNets + IP-Adapter
  - Best for batch processing

### Cloud GPU Options (Free Tier)

| Provider | Free Tier | GPU Type | Limitations |
|----------|-----------|----------|-------------|
| Google Colab | 15hrs/week | T4 16GB | Session timeout |
| Kaggle | 30hrs/week | P100/T4 | 9hr session limit |
| Hugging Face Spaces | Free CPU | N/A | No GPU free tier |
| GitHub Codespaces | 60hrs/month | N/A | CPU only |

## Memory Optimization

### Reduce VRAM Usage
```bash
# In ComfyUI, use these arguments:
python main.py --listen --force-fp16 --lowvram

# Or for very low VRAM (4-6GB):
python main.py --listen --force-fp16 --novram
```

### Use SDXL Turbo (faster, less VRAM)
SDXL Turbo can generate in 1-4 steps instead of 30:
- 4GB VRAM minimum
- 1-2 seconds per image
- Slightly lower quality than full SDXL

### Model Quantization
```bash
# Use FP16 models (half precision)
# SDXL base: 6.9GB -> 3.5GB in FP16

# Use GGUF quantized models
# Further reduces to 2-4GB with minimal quality loss
```

## Performance Tuning

### ComfyUI Settings
| Setting | Value | Effect |
|---------|-------|--------|
| Batch Size | 1 | Lower for stability |
| Steps | 20-30 | Lower = faster, less quality |
| CFG Scale | 7.0-8.0 | Lower = faster, less adherence |
| Sampler | DPM++ 2M Karras | Good quality/speed balance |
| Scheduler | Karras | Standard choice |

### Add batch processing
```python
# Process multiple images efficiently
images = ["poster1.jpg", "poster2.jpg", "poster3.jpg"]
for img in images:
    # Pipeline skips slow steps where possible
    result = pipeline.run(img)
```

## macOS (Apple Silicon)

M1/M2/M3 Macs can run SDXL using:
- **Draw Things** app (native, fast)
- **ComfyUI** with MPS backend
- **Diffusers** library with MPS

```bash
# For MPS acceleration in ComfyUI
python main.py --listen --force-fp16 --use-mps
```

Performance:
- M1 Pro: ~45s per SDXL image
- M2 Max: ~25s per SDXL image
- M3 Max: ~15s per SDXL image
- M4 Pro: ~10s per SDXL image

## No GPU? No Problem

The system works without GPU:
1. **Image Processing**: Uses OpenCV/Pillow (CPU) - still fast
2. **Background Removal**: rembg (CPU) - slower but works
3. **Caption Generation**: Uses API (no GPU needed)
4. **Facebook Posting**: API call (no GPU needed)
5. **AI Generation**: Falls back to enhanced image processing

When `use_ai_generation=false`, the system:
- Creates premium gradient backgrounds
- Enhances lighting and contrast
- Adds professional overlays
- Uses template-based text placement
- Generates social-media optimized layouts

This produces professional-looking results without any GPU hardware.
