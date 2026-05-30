# Optimization Recommendations

## Performance Optimization

### 1. Image Pipeline

**Current: Sequential processing → Optimized: Parallel processing where possible**

```python
# Before (sequential)
ocr_result = ocr.extract_text(image)
bg_result = bg_remover.remove(image)
# Both steps are independent!

# After (parallel - use threading)
from concurrent.futures import ThreadPoolExecutor
with ThreadPoolExecutor(max_workers=2) as executor:
    ocr_future = executor.submit(ocr.extract_text, image)
    bg_future = executor.submit(bg_remover.remove, image)
    ocr_result = ocr_future.result()
    bg_result = bg_future.result()
```

### 2. OCR Speed

| Optimization | Speedup | Quality Impact |
|-------------|---------|----------------|
| Reduce PSM modes | 2x | Minimal |
| Limit language to `eng` | 1.5x | None |
| Skip preprocessing | 3x | Reduced accuracy |
| Cache results | 100x (cached) | None |

**Recommended:** Preprocess + OCR with PSM 6 (uniform text block)

### 3. Background Removal

| Model | Speed (CPU) | Quality | VRAM |
|-------|-------------|---------|------|
| u2net | 5-8s | Good | 500MB |
| u2netp | 2-3s | Acceptable | 200MB |
| silueta | 1-2s | Baseline | 100MB |
| birefnet-general | 8-12s | Excellent | 1GB |

**Recommended:** Use `u2netp` for speed, `birefnet-general` for quality.

**Key optimization:** Reuse session object - don't recreate it per image!

```python
# GOOD - reuse session
session = new_session("u2net")
for img in images:
    result = remove(img, session=session)

# BAD - creates new session each time
for img in images:
    result = remove(img)  # Creates new session!
```

### 4. Caption Generation

**Response time by provider:**
- Groq API: 0.5-2 seconds (recommended)
- Gemini API: 1-3 seconds
- Ollama (local): 5-30 seconds (depends on model)

**Cache strategy:**
```python
# Simple LRU cache for repeated captions
from functools import lru_cache

@lru_cache(maxsize=100)
def get_cached_captions(food_title: str, offer: str) -> dict:
    return caption_gen.generate_captions({"food_title": food_title, "offer_text": offer})
```

### 5. ComfyUI SDXL

**Generation time factors:**
| Steps | Sampler | Time (RTX 4090) | Quality |
|-------|---------|----------------|---------|
| 20 | DPM++ 2M Karras | 5s | Good |
| 30 | DPM++ 2M Karras | 7s | Excellent |
| 40 | DPM++ 2M Karras | 10s | Marginal gain |
| 4 | SDXL Turbo | 2s | Good (different model) |

**Recommended:** 25-30 steps with DPM++ 2M Karras for best quality/speed.

---

## Quality Optimization

### 1. OCR Accuracy

```python
# Enhanced preprocessing for better OCR
def advanced_preprocess(image):
    # 1. Increase DPI
    image = image.resize((image.width * 2, image.height * 2), Image.LANCZOS)

    # 2. Smart sharpening
    img_array = np.array(image)
    kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
    sharpened = cv2.filter2D(img_array, -1, kernel)

    # 3. Better thresholding
    gray = cv2.cvtColor(sharpened, cv2.COLOR_RGB2GRAY)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    return binary
```

### 2. Background Removal Fine-Tuning

```python
# Better food image background removal
remover = BackgroundRemover(model_name="birefnet-general")

# Post-processing for food images
def refine_food_mask(image, mask):
    # Remove small specks
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5,5)))
    # Smooth edges
    mask = cv2.GaussianBlur(mask, (3,3), 0)
    return mask
```

### 3. Image Enhancement

```python
# Professional food photo enhancement
def enhance_food_photo(image):
    # 1. Color balance
    img = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2LAB)
    l, a, b = cv2.split(img)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
    l = clahe.apply(l)
    img = cv2.merge([l, a, b])
    img = cv2.cvtColor(img, cv2.COLOR_LAB2RGB)

    # 2. Warm tone boost (for food)
    img = img.astype(float)
    img[:,:,0] *= 1.05  # Boost red
    img[:,:,1] *= 1.02  # Boost green
    img[:,:,2] *= 0.95  # Slightly reduce blue (warm)
    img = np.clip(img, 0, 255).astype(np.uint8)

    return Image.fromarray(img)
```

### 4. SDXL Prompt Engineering

```python
# Effective restaurant prompts
def build_restaurant_prompt(food_title, style="premium"):
    base = f"Professional food photography of {food_title}, "

    if style == "premium":
        prompt = base + (
            "cinematic lighting, mouth-watering presentation, "
            "Michelin star quality, premium restaurant aesthetic, "
            "clean composition, vibrant natural colors, "
            "soft shadows, depth of field, 8K quality"
        )
    elif style == "street_food":
        prompt = base + (
            "street food style, rustic presentation, "
            "authentic atmosphere, natural lighting, "
            "urban setting, casual dining vibe"
        )

    return prompt
```

---

## Cost Optimization

### Free Tier Limits Management

| Service | Limit | Mitigation |
|---------|-------|------------|
| Groq API | 30 req/min | Cache captions, batch requests |
| Gemini API | 60 req/min | Use as backup only |
| Hugging Face | CPU only | Skip AI generation |
| Google Colab | 15hrs/week | Use SDXL Turbo, save models |

### Reduce API Calls

```python
# 1. Cache similar captions
caption_cache = {}

def get_caption(food_data):
    key = f"{food_data.get('food_title')}_{food_data.get('offer_text')}"
    if key in caption_cache:
        return caption_cache[key]

    captions = caption_gen.generate_captions(food_data)
    caption_cache[key] = captions
    return captions
```

### Batch Processing

```python
# Process multiple posters in one session
def batch_process(poster_paths):
    results = []
    # Reuse session objects
    bg_session = new_session("u2netp")

    for path in poster_paths:
        result = pipeline.run(path)
        results.append(result)

    return results
```

---

## Monitoring & Profiling

### Add timing decorators

```python
import time
from functools import wraps

def timed(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        duration = time.time() - start
        logger.info(f"{func.__name__}: {duration:.2f}s")
        return result
    return wrapper

# Apply to pipeline steps
@timed
def run_pipeline(self, image_path):
    # ...
```

### System Resource Monitoring

```bash
# Watch GPU usage
watch -n 1 nvidia-smi

# Watch CPU/Memory
htop

# Monitor disk usage
du -sh static/outputs/
du -sh static/uploads/
```

---

## Recommended Configuration

For **best quality** (with GPU):
```yaml
# config/settings.py overrides
COMFYUI_WORKFLOW: "restaurant_poster.json"
SDXL_STEPS: 30
SDXL_CFG: 7.5
BG_MODEL: "birefnet-general"
OCR_PSM: 3
CAPTION_MODEL: "llama-3.3-70b-versatile"
```

For **fastest speed** (CPU only):
```yaml
USE_AI_GENERATION: false
BG_MODEL: "u2netp"
OCR_PSM: 6
SKIP_OCR_PREPROCESS: true
CAPTION_PROVIDER: "template"  # Skip API calls
```

For **balanced**:
```yaml
USE_AI_GENERATION: false
BG_MODEL: "u2net"
OCR_PSM: 6
CAPTION_PROVIDER: "groq"
```
