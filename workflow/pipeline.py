"""
Workflow Pipeline - Simplified orchestrator for the restaurant social media automation.
Handles: image upload -> OCR -> caption generation -> Facebook posting.
Uploads the original image directly to Facebook with AI-generated captions.
"""

import time
import traceback
from pathlib import Path
from typing import Optional, Dict, Any, Callable
from datetime import datetime
from utils.logger import get_logger
from utils.storage import StorageManager

logger = get_logger(__name__)


class PipelineStep:
    """Represents a single step in the automation pipeline."""

    def __init__(self, name: str, max_retries: int = 3):
        self.name = name
        self.max_retries = max_retries
        self.status = "pending"  # pending, running, success, failed, skipped
        self.error = None
        self.result = None
        self.start_time = None
        self.end_time = None

    def duration(self) -> float:
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return 0.0

    def to_dict(self) -> dict:
        return {
            "step": self.name,
            "status": self.status,
            "error": str(self.error) if self.error else None,
            "duration_seconds": self.duration(),
        }


class PipelineResult:
    """Container for the complete pipeline execution result."""

    def __init__(self):
        self.status = "pending"
        self.steps: list[PipelineStep] = []
        self.final_image_path: Optional[str] = None
        self.captions: Optional[Dict[str, str]] = None
        self.facebook_result: Optional[Dict[str, Any]] = None
        self.extracted_data: Optional[Dict[str, Any]] = None
        self.error: Optional[str] = None
        self.logs: list[str] = []
        self.start_time = datetime.now()
        self.end_time: Optional[datetime] = None

    def add_log(self, message: str):
        self.logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "steps": [s.to_dict() for s in self.steps],
            "final_image_path": self.final_image_path,
            "captions": self.captions,
            "facebook_result": self.facebook_result,
            "extracted_data": self.extracted_data,
            "error": self.error,
            "logs": self.logs,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
        }


class RestaurantPipeline:
    """
    Simplified restaurant social media automation pipeline.

    Steps:
    1. OCR Extraction (get food info for caption)
    2. Caption Generation (via Groq/Gemini)
    3. Facebook Posting (original image + AI caption)
    """

    def __init__(
        self,
        ocr_extractor=None,
        caption_generator=None,
        facebook_poster=None,
        storage: Optional[StorageManager] = None,
    ):
        self.ocr = ocr_extractor
        self.caption_gen = caption_generator
        self.fb_poster = facebook_poster
        self.storage = storage
        self.post_to_facebook = True

    def _run_step(
        self,
        step: PipelineStep,
        action: Callable,
        *args,
        **kwargs,
    ) -> Any:
        """Run a pipeline step with retry logic."""
        step.status = "running"
        step.start_time = time.time()

        last_error = None
        for attempt in range(1, step.max_retries + 1):
            try:
                logger.info(f"Step '{step.name}' - Attempt {attempt}/{step.max_retries}")
                result = action(*args, **kwargs)

                # Check if result is a dict with success=False (failure response)
                if isinstance(result, dict) and not result.get("success", True):
                    error_msg = result.get("error", "Step returned failure response")
                    last_error = error_msg
                    logger.warning(f"Step '{step.name}' returned failure: {error_msg}")
                    if attempt < step.max_retries:
                        wait = min(2 ** attempt, 30)
                        logger.info(f"Retrying in {wait}s...")
                        time.sleep(wait)
                    continue

                if result is not None and result is not False:
                    step.status = "success"
                    step.result = result
                    step.end_time = time.time()
                    logger.info(f"Step '{step.name}' completed in {step.duration():.1f}s")
                    return result

                last_error = f"Step returned no result"
                logger.warning(f"Step '{step.name}' returned empty result")

            except Exception as e:
                last_error = e
                logger.error(f"Step '{step.name}' attempt {attempt} failed: {e}")
                if attempt < step.max_retries:
                    wait = min(2 ** attempt, 30)
                    logger.info(f"Retrying in {wait}s...")
                    time.sleep(wait)

        step.status = "failed"
        step.error = str(last_error)
        step.end_time = time.time()
        raise Exception(f"Step '{step.name}' failed after {step.max_retries} retries: {last_error}")

    def run(self, image_path: str, restaurant_name: str = "") -> PipelineResult:
        """
        Execute the simplified automation pipeline.

        Args:
            image_path: Path to the uploaded restaurant poster image
            restaurant_name: Optional restaurant name

        Returns:
            PipelineResult with all outputs
        """
        result = PipelineResult()
        # The original uploaded image is posted directly — no processing
        result.final_image_path = image_path
        result.add_log(f"Starting pipeline for image: {Path(image_path).name}")

        try:
            # === STEP 1: OCR Extraction (for caption context) ===
            step1 = PipelineStep("OCR Text Extraction", max_retries=2)
            result.steps.append(step1)

            if self.ocr:
                extracted = self._run_step(step1, self.ocr.extract_structured, image_path)
                result.extracted_data = extracted
                result.add_log(
                    f"OCR complete: '{extracted.get('food_title', 'Unknown')}' - "
                    f"{extracted.get('offer_text', 'No offer')}"
                )
            else:
                step1.status = "skipped"
                result.extracted_data = {"food_title": "", "all_text": ""}
                result.add_log("OCR module not available, skipped")

            # === STEP 2: Caption Generation ===
            step2 = PipelineStep("Caption Generation", max_retries=2)
            result.steps.append(step2)
            captions = None

            if self.caption_gen:
                food_data = {}
                if result.extracted_data:
                    food_data = {
                        "food_title": result.extracted_data.get("food_title", ""),
                        "offer_text": result.extracted_data.get("offer_text", ""),
                        "pricing": result.extracted_data.get("pricing", [""])[0] if result.extracted_data.get("pricing") else "",
                        "restaurant_name": restaurant_name,
                    }

                captions = self._run_step(step2, self.caption_gen.generate_captions, food_data)
                result.captions = captions
                result.add_log("Captions generated successfully via Groq/Gemini")
            else:
                step2.status = "skipped"
                result.add_log("Caption generator not available")

            # === STEP 3: Facebook Posting (original image directly) ===
            step3 = PipelineStep("Facebook Posting", max_retries=3)
            result.steps.append(step3)

            if self.fb_poster and self.post_to_facebook and result.final_image_path:
                # Build caption from generated captions
                post_caption = ""
                if captions:
                    post_caption = (
                        f"{captions.get('long_caption', '')}\n\n"
                        f"{captions.get('cta', '')}\n\n"
                        f"{captions.get('hashtags', '')}"
                    )

                fb_result = self._run_step(
                    step3,
                    self.fb_poster.post_photo,
                    result.final_image_path,
                    caption=post_caption,
                )

                result.facebook_result = fb_result
                if fb_result and fb_result.get("success"):
                    result.add_log(
                        f"Posted to Facebook! "
                        f"URL: {fb_result.get('post_url', 'N/A')}"
                    )
                else:
                    result.add_log(f"Facebook posting issue: {fb_result}")
            else:
                step3.status = "skipped"
                result.add_log(
                    "Facebook posting skipped "
                    f"(poster: {'yes' if self.fb_poster else 'no'}, "
                    f"enabled: {self.post_to_facebook})"
                )

            # === Final Status ===
            successful = sum(1 for s in result.steps if s.status == "success")
            skipped = sum(1 for s in result.steps if s.status == "skipped")
            total = len(result.steps)

            if successful == total - skipped:
                result.status = "success"
            elif successful > 0:
                result.status = "partial"
            else:
                result.status = "failed"
                result.error = "All steps failed"

            result.add_log(
                f"Pipeline finished: {result.status.upper()} "
                f"({successful} success, {total - successful - skipped} failed, {skipped} skipped)"
            )

        except Exception as e:
            result.status = "failed"
            result.error = str(e)
            traceback.print_exc()
            result.add_log(f"Pipeline failed with error: {e}")

        result.end_time = datetime.now()
        return result
