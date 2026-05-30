"""
OCR Module - Extracts text from restaurant poster images using Tesseract.
Detects: food titles, offer text, pricing, and menu items.
"""

import re
import cv2
import numpy as np
from PIL import Image
from typing import Optional
import pytesseract
from utils.logger import get_logger

logger = get_logger(__name__)


class RestaurantOCRExtractor:
    """Extract structured text data from restaurant food poster images."""

    # Common price patterns
    PRICE_PATTERNS = [
        r'\$\s*\d+\.?\d*',        # $9.99
        r'\₹\s*\d+\.?\d*',        # ₹99
        r'\€\s*\d+\.?\d*',        # €9.99
        r'\£\s*\d+\.?\d*',        # £9.99
        r'\d+\.?\d*\s*\$',        # 9.99$
        r'\d+%\s*OFF',            # 20% OFF
        r'OFF\s*\d+%',            # OFF 20%
        r'FREE',                   # FREE
        r'Only\s*\d+\.?\d*',      # Only 9.99
        r'Just\s*\d+\.?\d*',      # Just 9.99
    ]

    def __init__(self, lang: str = "eng", psm: int = 6):
        """
        Initialize OCR extractor.

        Args:
            lang: Tesseract language (default: eng)
            psm: Page segmentation mode (6 = uniform text block)
        """
        self.lang = lang
        self.psm = psm
        self._check_tesseract()

    def _check_tesseract(self):
        """Verify Tesseract is installed and accessible."""
        try:
            pytesseract.get_tesseract_version()
            logger.info("Tesseract OCR detected and ready")
        except Exception as e:
            logger.warning(
                f"Tesseract not found: {e}. "
                "Install with: brew install tesseract (macOS) or "
                "apt-get install tesseract-ocr (Linux)"
            )

    def preprocess_image(self, image: np.ndarray) -> np.ndarray:
        """
        Preprocess image for better OCR accuracy.

        Steps:
        - Convert to grayscale
        - Denoise
        - Apply adaptive thresholding
        - Deskew
        """
        # Convert to grayscale if needed
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image

        # Denoise
        denoised = cv2.fastNlMeansDenoising(gray, h=10)

        # Increase contrast with CLAHE
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(denoised)

        # Adaptive thresholding
        binary = cv2.adaptiveThreshold(
            enhanced, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            blockSize=31,
            C=2
        )

        # Deskew
        coords = np.column_stack(np.where(binary > 0))
        if len(coords) > 0:
            angle = cv2.minAreaRect(coords)[-1]
            if angle < -45:
                angle = 90 + angle
            if abs(angle) > 0.5:
                h, w = binary.shape
                center = (w // 2, h // 2)
                matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
                binary = cv2.warpAffine(binary, matrix, (w, h),
                                        flags=cv2.INTER_CUBIC,
                                        borderMode=cv2.BORDER_REPLICATE)

        return binary

    def extract_text(self, image_path: str) -> str:
        """
        Extract all text from a restaurant poster image.

        Args:
            image_path: Path to the image file

        Returns:
            Extracted text as a single string
        """
        # Read image
        image = cv2.imread(image_path)
        if image is None:
            raise FileNotFoundError(f"Could not read image: {image_path}")

        # Preprocess
        processed = self.preprocess_image(image)

        # OCR configuration
        custom_config = f"--psm {self.psm} --oem 3 -c tessedit_char_whitelist='abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789$₹€£%.,/-!@#&() '"

        # Extract text
        text = pytesseract.image_to_string(
            processed,
            lang=self.lang,
            config=custom_config
        )

        logger.info(f"OCR extracted {len(text)} characters from {image_path}")
        return text.strip()

    def extract_structured(self, image_path: str) -> dict:
        """
        Extract structured restaurant data from a poster image.

        Returns:
            dict with keys: food_title, offer_text, pricing, all_text, sections
        """
        raw_text = self.extract_text(image_path)
        lines = [l.strip() for l in raw_text.split('\n') if l.strip()]

        # Detect pricing
        prices = self._extract_prices(raw_text)

        # Find likely food title (first large/emphasized text)
        food_title = self._guess_food_title(lines)

        # Find offer text
        offer_text = self._extract_offer_text(lines)

        # Find phone/social info
        phone = self._extract_phone(raw_text)

        return {
            "food_title": food_title,
            "offer_text": offer_text,
            "pricing": prices,
            "phone": phone,
            "all_text": raw_text,
            "lines": lines,
        }

    def _extract_prices(self, text: str) -> list:
        """Extract price information from text."""
        prices = []
        for pattern in self.PRICE_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            prices.extend(matches)
        return list(set(prices))

    def _guess_food_title(self, lines: list) -> str:
        """Guess the food title (typically the first substantive line)."""
        skip_words = {"www", "http", "phone", "call", "order", "delivery",
                      "open", "hours", "address", "free", "offer", "save"}
        for line in lines[:6]:
            words = line.split()
            if len(words) >= 2 and len(line) < 60:
                if not any(s in line.lower() for s in skip_words):
                    return line
        return lines[0] if lines else ""

    def _extract_offer_text(self, lines: list) -> str:
        """Extract offer/promotion text."""
        offer_keywords = ["offer", "save", "free", "off", "deal", "combo",
                          "special", "discount", "limited", "today only",
                          "buy", "get", "%"]
        for line in lines:
            if any(kw in line.lower() for kw in offer_keywords):
                return line
        return ""

    def _extract_phone(self, text: str) -> str:
        """Extract phone number from text."""
        phone_patterns = [
            r'\+\d{1,3}[\s.-]?\d{3}[\s.-]?\d{3}[\s.-]?\d{4}',
            r'\d{3}[\s.-]?\d{3}[\s.-]?\d{4}',
            r'\d{5}[\s.-]?\d{5}',
        ]
        for pattern in phone_patterns:
            match = re.search(pattern, text)
            if match:
                return match.group()
        return ""
