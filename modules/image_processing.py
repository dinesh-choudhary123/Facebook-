"""
Image Processing Module - Handles all image manipulation using OpenCV and Pillow.
Provides: resizing, compositing, text overlay, lighting effects, and design enhancements.
"""

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
from pathlib import Path
from typing import Optional, Tuple, List
from utils.logger import get_logger

logger = get_logger(__name__)


class ImageProcessor:
    """
    Professional image processing for restaurant posters.
    Handles composition, lighting, text overlay, and design enhancements.
    """

    # Standard social media sizes
    FORMATS = {
        "square": (1080, 1080),      # Instagram/Facebook square
        "portrait": (1080, 1350),    # Instagram portrait
        "story": (1080, 1920),       # Instagram/Facebook story
        "landscape": (1200, 630),    # Facebook link share
    }

    def __init__(self):
        self.font_paths = self._find_fonts()

    def _find_fonts(self) -> dict:
        """Find available fonts on the system for text rendering."""
        import os
        possible_paths = [
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "/System/Library/Fonts/Supplemental/SFPro.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/TTF/DejaVuSans.ttf",
        ]
        fonts = {}
        for path in possible_paths:
            if os.path.exists(path):
                if "Bold" in path or "bold" in path:
                    fonts["bold"] = path
                elif "Regular" in path or "regular" in path:
                    fonts["regular"] = path
                else:
                    fonts.setdefault("regular", path)
        return fonts

    def load_image(self, path: str) -> Image.Image:
        """Load an image from path."""
        return Image.open(path).convert("RGBA")

    def resize_to_format(
        self,
        image: Image.Image,
        format_name: str = "square",
        fit_mode: str = "cover"
    ) -> Image.Image:
        """
        Resize image to a standard social media format.

        Args:
            image: PIL Image
            format_name: 'square', 'portrait', 'story', or 'landscape'
            fit_mode: 'cover' (crop to fill), 'contain' (fit within)

        Returns:
            Resized PIL Image
        """
        target_size = self.FORMATS.get(format_name, self.FORMATS["square"])
        return self.resize(image, target_size, fit_mode)

    def resize(
        self,
        image: Image.Image,
        target_size: Tuple[int, int],
        fit_mode: str = "cover"
    ) -> Image.Image:
        """
        Resize image to target dimensions.

        Args:
            image: PIL Image
            target_size: (width, height) tuple
            fit_mode: 'cover' or 'contain'

        Returns:
            Resized PIL Image
        """
        if fit_mode == "cover":
            return self._resize_cover(image, target_size)
        else:
            return self._resize_contain(image, target_size)

    def _resize_cover(self, image: Image.Image, target_size: Tuple[int, int]) -> Image.Image:
        """Resize and crop to fill target dimensions."""
        target_w, target_h = target_size
        img_w, img_h = image.size

        # Calculate scale to cover target
        scale = max(target_w / img_w, target_h / img_h)
        new_w = int(img_w * scale)
        new_h = int(img_h * scale)

        image = image.resize((new_w, new_h), Image.LANCZOS)

        # Center crop
        left = (new_w - target_w) // 2
        top = (new_h - target_h) // 2
        return image.crop((left, top, left + target_w, top + target_h))

    def _resize_contain(self, image: Image.Image, target_size: Tuple[int, int]) -> Image.Image:
        """Resize to fit within target dimensions (pillarbox/letterbox)."""
        image.thumbnail(target_size, Image.LANCZOS)
        canvas = Image.new("RGBA", target_size, (0, 0, 0, 0))
        x = (target_size[0] - image.width) // 2
        y = (target_size[1] - image.height) // 2
        canvas.paste(image, (x, y))
        return canvas

    def add_gradient_overlay(
        self,
        image: Image.Image,
        colors: Optional[List[Tuple[int, int, int, int]]] = None,
        direction: str = "bottom"
    ) -> Image.Image:
        """
        Add a professional gradient overlay to the image.

        Args:
            image: PIL Image
            colors: List of RGBA tuples for gradient stops
            direction: 'bottom', 'top', 'left', 'right', 'radial'

        Returns:
            Image with gradient overlay
        """
        if colors is None:
            colors = [
                (0, 0, 0, 0),        # transparent
                (0, 0, 0, 180),       # semi-transparent black
            ]

        img = image.copy()
        overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        w, h = image.size

        if direction == "bottom":
            for y in range(h):
                ratio = y / h
                idx = min(int(ratio * len(colors)), len(colors) - 2)
                local_ratio = (ratio * len(colors)) - idx
                if idx + 1 < len(colors):
                    c1, c2 = colors[idx], colors[idx + 1]
                    r = int(c1[0] + (c2[0] - c1[0]) * local_ratio)
                    g = int(c1[1] + (c2[1] - c1[1]) * local_ratio)
                    b = int(c1[2] + (c2[2] - c1[2]) * local_ratio)
                    a = int(c1[3] + (c2[3] - c1[3]) * local_ratio)
                    draw.line([(0, y), (w, y)], fill=(r, g, b, a))

        elif direction == "radial":
            center = (w // 2, h // 2)
            max_radius = int((w**2 + h**2) ** 0.5 / 2)
            for r in range(max_radius, 0, -1):
                ratio = 1 - (r / max_radius)
                idx = min(int(ratio * len(colors)), len(colors) - 2)
                local_ratio = (ratio * len(colors)) - idx
                if idx + 1 < len(colors):
                    c1, c2 = colors[idx], colors[idx + 1]
                    ra = int(c1[0] + (c2[0] - c1[0]) * local_ratio)
                    g = int(c1[1] + (c2[1] - c1[1]) * local_ratio)
                    b = int(c1[2] + (c2[2] - c1[2]) * local_ratio)
                    a = int(c1[3] + (c2[3] - c1[3]) * local_ratio)
                    draw.ellipse(
                        [(center[0] - r, center[1] - r),
                         (center[0] + r, center[1] + r)],
                        outline=(ra, g, b, a),
                        width=3
                    )

        return Image.alpha_composite(img, overlay)

    def enhance_lighting(self, image: Image.Image, factor: float = 1.2) -> Image.Image:
        """Enhance image lighting and contrast."""
        enhancer = ImageEnhance.Brightness(image)
        image = enhancer.enhance(factor)
        enhancer = ImageEnhance.Contrast(image)
        image = enhancer.enhance(1.1)
        enhancer = ImageEnhance.Sharpness(image)
        image = enhancer.enhance(1.15)
        return image

    def add_shadow(
        self,
        image: Image.Image,
        offset: Tuple[int, int] = (0, 5),
        blur_radius: int = 15,
        opacity: int = 100
    ) -> Image.Image:
        """
        Add a drop shadow to an image element.

        Args:
            image: PIL Image (RGBA)
            offset: (x, y) shadow offset
            blur_radius: Gaussian blur radius
            opacity: Shadow opacity (0-255)

        Returns:
            Image with shadow (size increased to accommodate shadow)
        """
        shadow = Image.new("RGBA", image.size, (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow)

        # Create shadow mask
        if image.mode == "RGBA":
            mask = image.split()[3]
        else:
            mask = Image.new("L", image.size, 255)

        # Offset and blur shadow
        shadow_mask = Image.new("L", image.size, 0)
        shadow_draw = ImageDraw.Draw(shadow_mask)
        shadow_draw.bitmap(offset, mask)

        shadow_mask = shadow_mask.filter(ImageFilter.GaussianBlur(blur_radius))

        # Apply shadow
        result = Image.new("RGBA",
                          (image.width + abs(offset[0]) + blur_radius,
                           image.height + abs(offset[1]) + blur_radius),
                          (0, 0, 0, 0))

        shadow_layer = Image.new("RGBA", result.size, (0, 0, 0, 0))
        shadow_layer_np = np.array(shadow_layer)
        shadow_layer_np[:, :, 3] = np.array(shadow_mask.resize(result.size)) * opacity // 255
        shadow_layer = Image.fromarray(shadow_layer_np)

        result = Image.alpha_composite(result, shadow_layer)
        result.paste(image, (blur_radius // 2, blur_radius // 2), image)

        return result

    def add_text_overlay(
        self,
        image: Image.Image,
        text: str,
        position: Tuple[int, int],
        font_size: int = 48,
        color: Tuple[int, int, int] = (255, 255, 255),
        font_path: Optional[str] = None,
        align: str = "center",
        stroke_width: int = 0,
        stroke_color: Tuple[int, int, int] = (0, 0, 0),
    ) -> Image.Image:
        """
        Add text overlay to image with professional styling.

        Args:
            image: PIL Image
            text: Text to render
            position: (x, y) center position
            font_size: Font size in pixels
            color: RGB text color
            font_path: Path to font file (uses system font if None)
            align: 'left', 'center', 'right'
            stroke_width: Outline width
            stroke_color: Outline color

        Returns:
            Image with text overlay
        """
        img = image.copy()
        draw = ImageDraw.Draw(img)

        # Use specified font or fall back to default
        try:
            if font_path:
                font = ImageFont.truetype(font_path, font_size)
            else:
                font_path = self.font_paths.get("bold") or self.font_paths.get("regular")
                if font_path:
                    font = ImageFont.truetype(font_path, font_size)
                else:
                    font = ImageFont.load_default()
        except (IOError, OSError):
            font = ImageFont.load_default()

        # Get text bounding box
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]

        # Adjust position based on alignment
        x, y = position
        if align == "center":
            x -= text_w // 2
        elif align == "right":
            x -= text_w

        # Draw stroke/outline
        if stroke_width > 0:
            for dx in range(-stroke_width, stroke_width + 1):
                for dy in range(-stroke_width, stroke_width + 1):
                    if dx != 0 or dy != 0:
                        draw.text(
                            (x + dx, y + dy),
                            text,
                            font=font,
                            fill=stroke_color + (255,)
                        )

        # Draw main text
        draw.text((x, y), text, font=font, fill=color + (255,))

        return img

    def create_premium_background(
        self,
        size: Tuple[int, int] = (1080, 1080),
        primary_color: Tuple[int, int, int] = (30, 30, 35),
        accent_color: Tuple[int, int, int] = (200, 160, 80),
        texture: str = "subtle"
    ) -> Image.Image:
        """
        Create a premium restaurant-style background.

        Args:
            size: (width, height)
            primary_color: Base color
            accent_color: Accent color for effects
            texture: Type of texture ('subtle', 'warm', 'dark')

        Returns:
            Premium background PIL Image
        """
        img = Image.new("RGBA", size, primary_color + (255,))
        draw = ImageDraw.Draw(img)

        w, h = size

        if texture == "warm":
            # Warm gradient overlay
            for y in range(h):
                ratio = y / h
                r = int(primary_color[0] * (1 - ratio) + accent_color[0] * ratio)
                g = int(primary_color[1] * (1 - ratio) + accent_color[1] * ratio)
                b = int(primary_color[2] * (1 - ratio) + accent_color[2] * ratio)
                draw.line([(0, y), (w, y)], fill=(r, g, b, 30))

        elif texture == "dark":
            # Dark vignette
            center = (w // 2, h // 2)
            for x in range(w):
                for y in range(h):
                    dist = ((x - center[0])**2 + (y - center[1])**2) ** 0.5
                    max_dist = ((w//2)**2 + (h//2)**2) ** 0.5
                    ratio = min(dist / max_dist, 1.0)
                    darkness = int(ratio * 60)
                    pixel = img.getpixel((x, y))
                    img.putpixel((x, y), (
                        max(pixel[0] - darkness, 0),
                        max(pixel[1] - darkness, 0),
                        max(pixel[2] - darkness, 0),
                        255
                    ))

        # Add subtle noise for texture
        if texture != "none":
            noise = np.random.randint(0, 15, (h, w, 4), dtype=np.uint8)
            noise[:, :, 3] = 15
            noise_img = Image.fromarray(noise)
            img = Image.alpha_composite(img, noise_img)

        return img

    def add_vignette(self, image: Image.Image, strength: float = 0.3) -> Image.Image:
        """Add a vignette effect (darkening at edges)."""
        img = np.array(image)
        h, w = img.shape[:2]

        # Create vignette mask
        X, Y = np.meshgrid(np.linspace(-1, 1, w), np.linspace(-1, 1, h))
        mask = 1 - np.sqrt(X**2 + Y**2) * strength
        mask = np.clip(mask, 0, 1)

        # Apply to each channel
        for c in range(3):
            if c < img.shape[2]:
                img[:, :, c] = (img[:, :, c] * mask).astype(np.uint8)

        return Image.fromarray(img)

    def detect_logo_region(
        self,
        image: Image.Image,
    ) -> Optional[Tuple[int, int, int, int]]:
        """
        Detect likely logo region in a restaurant poster.
        Uses edge detection and clustering.

        Returns:
            (x, y, width, height) of detected logo region, or None
        """
        img = np.array(image.convert("RGB"))
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)

        # Edge detection
        edges = cv2.Canny(gray, 50, 150)

        # Find contours
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # Filter for likely logo regions (small, in corners or top)
        candidates = []
        h, w = gray.shape
        for contour in contours:
            x, y, cw, ch = cv2.boundingRect(contour)
            area = cw * ch
            aspect_ratio = cw / ch if ch > 0 else 1

            # Logo criteria: small, near 1:1 aspect, in upper region
            if (50 < area < w * h * 0.15 and
                    0.5 < aspect_ratio < 2.0 and
                    y < h * 0.5):
                candidates.append((x, y, cw, ch, area))

        if not candidates:
            return None

        # Return the largest candidate
        best = max(candidates, key=lambda c: c[4])
        return (best[0], best[1], best[2], best[3])

    def composite_images(
        self,
        background: Image.Image,
        foreground: Image.Image,
        position: Optional[Tuple[int, int]] = None,
        scale: Optional[float] = None,
    ) -> Image.Image:
        """
        Composite foreground onto background with optional scaling.

        Args:
            background: Background PIL Image
            foreground: Foreground PIL Image (RGBA)
            position: (x, y) top-left position
            scale: Scale factor for foreground

        Returns:
            Composited image
        """
        bg = background.copy()
        fg = foreground.copy()

        if fg.mode != "RGBA":
            fg = fg.convert("RGBA")

        if scale:
            new_size = (int(fg.width * scale), int(fg.height * scale))
            fg = fg.resize(new_size, Image.LANCZOS)

        if position:
            x, y = position
        else:
            x = (bg.width - fg.width) // 2
            y = (bg.height - fg.height) // 2

        bg.paste(fg, (x, y), fg)
        return bg
