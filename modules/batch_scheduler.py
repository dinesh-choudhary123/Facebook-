"""
Batch Scheduler Module - Automatically posts images from a folder to Facebook.
Scans the batch/ directory for image files (.jpg, .png, .jpeg, .webp, .gif).
The image filename (without extension) OR an accompanying .txt file is used as the Facebook post caption.
Posts them sequentially with a 30-minute interval, deleting each image after successful post.
"""

import os
import time
import threading
from pathlib import Path
from typing import Optional, Dict, Any, Callable
from datetime import datetime, timedelta
from utils.logger import get_logger

logger = get_logger(__name__)

# Supported image extensions
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


class BatchScheduler:
    """
    Automated batch posting scheduler.

    Folder convention:
        batch/
            My delicious pizza.jpg   (caption comes from filename: "My delicious pizza")
            Best burger in town.png   (caption comes from filename: "Best burger in town")
            ...

    The scheduler picks the first image alphabetically, posts to Facebook using
    its filename stem or a matching .txt file as the caption, then schedules the
    next run after 30 minutes. No .txt caption files are needed.
    """

    def __init__(self, batch_dir: str, fb_poster=None):
        self.batch_dir = Path(batch_dir)
        self.fb_poster = fb_poster
        self.batch_dir.mkdir(parents=True, exist_ok=True)

        # State
        self._running = False
        self._paused = False
        self._timer: Optional[threading.Timer] = None
        self._current_job: Optional[Dict[str, Any]] = None
        self._history: list[Dict[str, Any]] = []
        self._lock = threading.Lock()
        self._log: list[str] = []
        self.interval_minutes = 30
        self._scheduled_start_timer: Optional[threading.Timer] = None
        self._scheduled_at: Optional[str] = None

    # ── Public API ──────────────────────────────────────────

    def start(self, interval_minutes: int = 30) -> Dict[str, Any]:
        """Start the batch scheduler."""
        with self._lock:
            if self._running:
                return {"success": False, "message": "Scheduler is already running"}

            self.interval_minutes = interval_minutes
            self._running = True
            self._paused = False
            self._log = []
            self._history = []

        self._add_log(f"🚀 Batch scheduler started (every {interval_minutes} min)")
        logger.info(f"Batch scheduler started with {interval_minutes} min interval")

        # Start processing immediately
        self._process_next()
        return {"success": True, "message": f"Batch scheduler started (every {interval_minutes} min)"}

    def stop(self) -> Dict[str, Any]:
        """Stop the batch scheduler."""
        with self._lock:
            self._running = False
            self._paused = False
            self._cancel_timer()
            self.cancel_scheduled_start()

        self._add_log("🛑 Batch scheduler stopped")
        logger.info("Batch scheduler stopped")
        return {"success": True, "message": "Batch scheduler stopped"}

    def pause(self) -> Dict[str, Any]:
        """Pause the scheduler (current timer continues, but pauses after)."""
        with self._lock:
            if not self._running:
                return {"success": False, "message": "Scheduler is not running"}
            self._paused = True

        self._add_log("⏸️  Batch scheduler paused")
        logger.info("Batch scheduler paused")
        return {"success": True, "message": "Batch scheduler paused"}

    def resume(self) -> Dict[str, Any]:
        """Resume a paused scheduler."""
        with self._lock:
            if not self._running:
                return {"success": False, "message": "Scheduler is not running"}
            if not self._paused:
                return {"success": False, "message": "Scheduler is not paused"}
            self._paused = False

        self._add_log("▶️  Batch scheduler resumed")
        logger.info("Batch scheduler resumed")
        # Immediately try to process next
        self._process_next()
        return {"success": True, "message": "Batch scheduler resumed"}

    def status(self) -> Dict[str, Any]:
        """Get current scheduler status."""
        with self._lock:
            next_run = None
            if self._timer and self._running and not self._paused:
                # Estimate next run based on when timer was created
                next_run = (datetime.now() + timedelta(seconds=self.interval_minutes * 60)).isoformat()

            queued = self._count_queued()

            return {
                "running": self._running,
                "paused": self._paused,
                "interval_minutes": self.interval_minutes,
                "next_run": next_run,
                "queued_pairs": queued,
                "posted_count": len([h for h in self._history if h.get("status") == "success"]),
                "failed_count": len([h for h in self._history if h.get("status") == "failed"]),
                "current_job": self._current_job,
                "history": self._history[-10:],  # Last 10 entries
                "scheduled_at": self._scheduled_at,
                "batch_dir": str(self.batch_dir),
                "logs": self._log[-50:],  # Last 50 log entries
            }

    def skip_current(self) -> Dict[str, Any]:
        """Skip the current pending pair (mark as failed and move on)."""
        with self._lock:
            if not self._current_job:
                return {"success": False, "message": "No current job to skip"}

            job = self._current_job
            job["status"] = "skipped"
            job["ended_at"] = datetime.now().isoformat()
            self._history.append(job)
            self._current_job = None

        # Delete the skipped image so we don't get stuck on it
        image_name = job.get('image_name', '')
        skipped_image = self.batch_dir / image_name if image_name else None
        if skipped_image:
            self._delete_pair(skipped_image)

        self._add_log(f"⏭️  Skipped & deleted: {image_name}")
        logger.info(f"Skipped batch item: {image_name}")

        # Schedule next
        self._schedule_next()
        return {"success": True, "message": "Skipped current job"}

    def add_pair(self, image_path: str) -> Dict[str, Any]:
        """Add an image to the batch folder. The filename (without extension) becomes the caption."""
        img = Path(image_path)
        if not img.exists():
            return {"success": False, "message": f"Image not found: {image_path}"}

        # Copy the image to batch folder
        dest_img = self.batch_dir / img.name
        import shutil
        shutil.copy2(str(img), str(dest_img))

        self._add_log(f"➕ Added image: {img.name} (caption from filename)")
        return {"success": True, "message": f"Added {img.name} to batch — filename will be used as caption"}

    def add_pair_with_caption(self, image_data: bytes, image_name: str, caption: str) -> Dict[str, Any]:
        """Add an image with its caption (as .txt file) to the batch folder."""
        try:
            # Add timestamp prefix to avoid filename collisions
            from datetime import datetime
            import uuid
            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            safe_name = f"{ts}_{uuid.uuid4().hex[:6]}_{image_name}"
            dest_img = self.batch_dir / safe_name
            dest_img.write_bytes(image_data)

            # Save caption as .txt file (supports long text, emojis, any characters)
            if caption and caption.strip():
                txt_file = dest_img.with_suffix('.txt')
                txt_file.write_text(caption.strip(), encoding='utf-8')

            self._add_log(f"➕ Added: {image_name} with caption ({len(caption)} chars)")
            return {"success": True, "message": f"Added {image_name} with caption"}
        except Exception as e:
            logger.error(f"Failed to add pair {image_name}: {e}")
            return {"success": False, "message": str(e)}

    def schedule_start(self, interval_minutes: int, scheduled_at_iso: str) -> Dict[str, Any]:
        """Schedule the batch scheduler to auto-start at a specific time."""
        try:
            scheduled_dt = datetime.fromisoformat(scheduled_at_iso)
            delay = (scheduled_dt - datetime.now()).total_seconds()
            
            # Save interval immediately for correct status display
            self.interval_minutes = interval_minutes
            
            if delay < 0:
                self._scheduled_at = None
                self.start(interval_minutes)
                return {"success": True, "message": f"Scheduled time already passed. Starting now with {interval_minutes} min interval."}

            # Cancel any existing timer first, THEN set new schedule
            self.cancel_scheduled_start()
            self._scheduled_at = scheduled_at_iso
            self._scheduled_start_timer = threading.Timer(delay, self.start, args=[interval_minutes])
            self._scheduled_start_timer.daemon = True
            self._scheduled_start_timer.start()

            time_str = scheduled_dt.strftime("%Y-%m-%d %H:%M")
            self._add_log(f"📅 Scheduled to start at {time_str} (every {interval_minutes} min)")
            logger.info(f"Batch scheduled to start at {time_str}")
            return {"success": True, "message": f"Scheduled to start at {time_str}"}
        except Exception as e:
            logger.error(f"Failed to schedule start: {e}")
            return {"success": False, "message": str(e)}
            return {"success": False, "message": str(e)}

    def cancel_scheduled_start(self):
        '''Cancel a previously scheduled start.'''
        if self._scheduled_start_timer:
            self._scheduled_start_timer.cancel()
            self._scheduled_start_timer = None
        self._scheduled_at = None

    # ── Internal Logic ──────────────────────────────────────

    def _process_next(self):
        """Find the next image and post it with its filename as the caption."""
        if not self._running or self._paused:
            return

        pair = self._find_next_pair()
        if not pair:
            self._add_log("📭 No more images in batch folder. Scheduler stopping.")
            logger.info("No more batch images — stopping scheduler")
            with self._lock:
                self._running = False
            return

        image_path = pair
        image_name = image_path.name
        # Try to read caption from .txt file first, fallback to filename
        caption_file = image_path.with_suffix('.txt')
        caption_text = image_path.stem
        if caption_file.exists():
            try:
                caption_text = caption_file.read_text(encoding='utf-8').strip()
            except Exception as e:
                logger.warning(f"Could not read caption file {caption_file.name}: {e}")

        job = {
            "image_name": image_name,
            "caption": caption_text[:80] + ("..." if len(caption_text) > 80 else ""),
            "started_at": datetime.now().isoformat(),
            "status": "posting",
        }
        with self._lock:
            self._current_job = job

        self._add_log(f'📤 Posting: {image_name} — caption: "{caption_text[:50]}"')
        logger.info(f"Batch posting: {image_name}")

        # Post to Facebook
        if self.fb_poster:
            try:
                result = self.fb_poster.post_photo(
                    image_path=str(image_path),
                    caption=caption_text,
                )

                success = result and result.get("success")

                if success:
                    job["status"] = "success"
                    job["post_id"] = result.get("post_id", "")
                    job["post_url"] = result.get("post_url", "")
                    job["ended_at"] = datetime.now().isoformat()
                    self._add_log(f"✅ Posted: {image_name}")
                    logger.info(f"Batch post success: {image_name} -> {result.get('post_id', '')}")
                else:
                    error = result.get("error", "Unknown error") if result else "No result"
                    job["status"] = "failed"
                    job["error"] = error
                    job["ended_at"] = datetime.now().isoformat()
                    self._add_log(f"❌ Failed: {image_name} - {error}")
                    logger.error(f"Batch post failed: {image_name} - {error}")

                # Always delete the image — move on regardless of success/failure
                self._delete_pair(image_path)
                self._add_log(f"🗑️  Deleted: {image_name}")

            except Exception as e:
                job["status"] = "failed"
                job["error"] = str(e)
                job["ended_at"] = datetime.now().isoformat()
                self._add_log(f"❌ Error: {image_name} - {e}")
                logger.error(f"Batch post error: {image_name} - {e}")
                # Delete image to avoid getting stuck on bad files
                self._delete_pair(image_path)
        else:
            job["status"] = "failed"
            job["error"] = "Facebook poster not configured"
            job["ended_at"] = datetime.now().isoformat()
            self._add_log("❌ Facebook poster not configured")
            logger.error("Facebook poster not available for batch")

        with self._lock:
            self._history.append(job)
            self._current_job = None

        # Schedule next run
        self._schedule_next()

    def _schedule_next(self):
        """Schedule the next batch run after the interval."""
        with self._lock:
            self._cancel_timer()

            if not self._running or self._paused:
                return

            remaining = self._count_queued()
            if remaining == 0:
                self._add_log("📭 All queued pairs posted. Scheduler stopping.")
                logger.info("All batch pairs posted — stopping scheduler")
                self._running = False
                return

            self._timer = threading.Timer(
                self.interval_minutes * 60,
                self._process_next,
            )
            self._timer.daemon = True
            self._timer.start()

            next_time = datetime.now() + timedelta(minutes=self.interval_minutes)
            self._add_log(f"⏰ Next post in {self.interval_minutes}m ({next_time.strftime('%H:%M')}) — {remaining} images remaining")
            logger.info(f"Next batch post in {self.interval_minutes}min ({remaining} images left)")

    def _find_next_pair(self) -> Optional[Path]:
        """Find the next image file to post (sorted alphabetically)."""
        images = sorted([
            f for f in self.batch_dir.iterdir()
            if f.suffix.lower() in IMAGE_EXTS and not f.name.startswith(".")
        ])

        if images:
            return images[0]

        return None

    def _delete_pair(self, image_path: Path):
        """Delete the image and its .txt caption file after posting."""
        try:
            if image_path.exists():
                image_path.unlink()
            # Also delete accompanying .txt caption file
            txt_file = image_path.with_suffix('.txt')
            if txt_file.exists():
                txt_file.unlink()
        except Exception as e:
            logger.warning(f"Failed to delete {image_path.name}: {e}")

    def _count_queued(self) -> int:
        """Count how many images are remaining in the batch folder."""
        images = [f for f in self.batch_dir.iterdir() if f.suffix.lower() in IMAGE_EXTS and not f.name.startswith(".")]
        return len(images)

    def _cancel_timer(self):
        """Cancel the current timer if active."""
        if self._timer:
            self._timer.cancel()
            self._timer = None

    def _add_log(self, message: str):
        """Add a timestamped log entry."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = f"[{timestamp}] {message}"
        self._log.append(entry)
        if len(self._log) > 500:
            self._log = self._log[-500:]
