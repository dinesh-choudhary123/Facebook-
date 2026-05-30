"""
Background Removal Module - Removes backgrounds from food poster images
using rembg (free, open-source, AI-powered).
"""

from pathlib import Path
from typing import Optional, Tuple
from PIL import Image, ImageFilter
import numpy as np
from utils.logger import get_logger

logger = get_logger(__name__)


class BackgroundRemover:
    """
    Remove backgrounds from restaurant food images.
    Uses rembg with configurable models.
    """

    def __init__(self, model_name: str = "u2net"):
        """
        Initialize background remover.

        Args:
            model_name: rembg model to use.
                Options: u2net, u2netp, isnet-general-use, birefnet-general, silueta
                For food: birefnet-general or isnet-general-use often work best.
        """
        self.model_name = model_name
        self.session = None
        self._lazy_init()

    def _lazy_init(self):
        """Lazily initialize the rembg session (first call is slow)."""
        try:
            from rembg import new_session
            self.session = new_session(self.model_name)
            logger.info(f"rembg session initialized with model: {self.model_name}")
        except ImportError:
            logger.error(
                "rembg not installed. Run: pip install rembg[cpu]"
            )
            raise
        except Exception as e:
            logger.warning(
                f"Could not load model '{self.model_name}': {e}. "
                "Will rely on fallback methods."
            )

    def remove_background(self, image: Image.Image) -> Image.Image:
        """
        Remove background from a food image.

        Args:
            image: PIL Image object

        Returns:
            PIL Image with transparent background (RGBA)
        """
        if self.session is None:
            return self._fallback_remove(image)

        try:
            from rembg import remove

            # Ensure RGBA
            if image.mode != "RGBA":
                image = image.convert("RGBA")

            result = remove(image, session=self.session)
            logger.info("Background removed successfully using rembg")

            # Post-process: smooth edges
            result = self._smooth_edges(result)

            return result

        except Exception as e:
            logger.error(f"rembg failed: {e}. Falling back to OpenCV method.")
            return self._fallback_remove(image)

    def remove_background_from_path(self, image_path: str) -> Image.Image:
        """
        Load image from path and remove background.

        Args:
            image_path: Path to the image file

        Returns:
            PIL Image with transparent background (RGBA)
        """
        image = Image.open(image_path)
        return self.remove_background(image)

    def _smooth_edges(self, image: Image.Image) -> Image.Image:
        """Apply slight blur to alpha channel for smoother edges."""
        if image.mode != "RGBA":
            return image

        r, g, b, a = image.split()
        a = a.filter(ImageFilter.SMOOTH_MORE)
        return Image.merge("RGBA", (r, g, b, a))

    def _fallback_remove(self, image: Image.Image) -> Image.Image:
        """
        Fallback background removal using OpenCV.
        Less accurate but doesn't require rembg models.
        """
        import cv2
        import numpy as np

        logger.info("Using OpenCV fallback for background removal")

        img = np.array(image.convert("RGB"))
        img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

        # Convert to HSV for better color segmentation
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

        # Try to detect and remove background (simple approach)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Use grabcut for foreground detection
        mask = np.zeros(gray.shape[:2], np.uint8)
        bgd_model = np.zeros((1, 65), np.float64)
        fgd_model = np.zeros((1, 65), np.float64)

        # Assume subject is in center
        h, w = gray.shape
        rect = (int(w * 0.05), int(h * 0.05), int(w * 0.9), int(h * 0.9))

        cv2.grabCut(img, mask, rect, bgd_model, fgd_model, 5, cv2.GC_INIT_WITH_RECT)

        mask2 = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 255, 0).astype("uint8")

        # Apply mask to original
        result_rgba = cv2.cvtColor(img, cv2.COLOR_BGR2RGBA)
        result_rgba[:, :, 3] = mask2

        # Smooth edges
        result_rgba[:, :, 3] = cv2.GaussianBlur(result_rgba[:, :, 3], (3, 3), 0)

        return Image.fromarray(result_rgba)

    def get_foreground_mask(self, image: Image.Image) -> np.ndarray:
        """Return just the binary foreground mask as numpy array."""
        result = self.remove_background(image)
        if result.mode == "RGBA":
            return np.array(result)[:, :, 3]
        return np.ones((image.height, image.width), dtype=np.uint8) * 255

    def composite_on_background(
        self,
        foreground: Image.Image,
        background: Image.Image,
        position: Optional[Tuple[int, int]] = None,
    ) -> Image.Image:
        """
        Place the foreground (with transparent bg) onto a new background.

        Args:
            foreground: RGBA image with transparent background
            background: RGB or RGBA background image
            position: (x, y) position to place foreground. Center if None.

        Returns:
            Composited RGBA image
        """
        # Ensure foreground is RGBA
        if foreground.mode != "RGBA":
            foreground = foreground.convert("RGBA")

        # Ensure background is RGBA
        if background.mode != "RGBA":
            background = background.convert("RGBA")

        # Resize foreground to fit background if needed
        bg_w, bg_h = background.size
        fg_w, fg_h = foreground.size

        # Scale foreground to leave margins
        scale = min(bg_w * 0.8 / fg_w, bg_h * 0.8 / fg_h, 1.0)
        if scale < 1.0:
            new_size = (int(fg_w * scale), int(fg_h * scale))
            foreground = foreground.resize(new_size, Image.LANCZOS)

        # Calculate position
        if position is None:
            x = (bg_w - foreground.width) // 2
            y = (bg_h - foreground.height) // 2
        else:
            x, y = position

        # Composite
        background = background.copy()
        background.paste(foreground, (x, y), foreground)

        return background
