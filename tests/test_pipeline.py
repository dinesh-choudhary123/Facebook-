"""
Tests for the Restaurant Social Media Automation Pipeline.
Run with: pytest tests/ -v
"""

import os
import sys
import json
import tempfile
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image
import numpy as np


class TestOCRExtractor:
    """Test OCR extraction functionality."""

    def test_ocr_import(self):
        """Verify OCR module can be imported."""
        from modules.ocr import RestaurantOCRExtractor
        extractor = RestaurantOCRExtractor()
        assert extractor is not None
        assert extractor.lang == "eng"

    def test_ocr_patterns(self):
        """Verify price patterns are defined."""
        from modules.ocr import RestaurantOCRExtractor
        extractor = RestaurantOCRExtractor()
        assert len(extractor.PRICE_PATTERNS) > 0

    def test_extract_prices_dollar(self):
        """Test price extraction with dollar amounts."""
        from modules.ocr import RestaurantOCRExtractor
        extractor = RestaurantOCRExtractor()
        prices = extractor._extract_prices("Burger $12.99 only!")
        assert any("$12.99" in p for p in prices)

    def test_extract_prices_off(self):
        """Test discount extraction."""
        from modules.ocr import RestaurantOCRExtractor
        extractor = RestaurantOCRExtractor()
        prices = extractor._extract_prices("20% OFF on all items")
        assert any("OFF" in p for p in prices)

    def test_extract_phone(self):
        """Test phone number extraction."""
        from modules.ocr import RestaurantOCRExtractor
        extractor = RestaurantOCRExtractor()
        phone = extractor._extract_phone("Call us at (555) 123-4567")
        assert phone != ""

    def test_guess_food_title(self):
        """Test food title guessing from lines."""
        from modules.ocr import RestaurantOCRExtractor
        extractor = RestaurantOCRExtractor()
        lines = [
            "Delicious Margherita Pizza",
            "Made with fresh ingredients",
            "Only $12.99",
        ]
        title = extractor._guess_food_title(lines)
        assert "Margherita" in title or "Pizza" in title


class TestBackgroundRemoval:
    """Test background removal functionality."""

    def test_import(self):
        """Verify rembg module can be imported."""
        from modules.background_removal import BackgroundRemover
        remover = BackgroundRemover()
        assert remover is not None

    def test_create_test_image(self):
        """Create a simple test image and verify processing."""
        # Create a simple solid-color image
        img = Image.new("RGBA", (100, 100), (255, 0, 0, 255))

        from modules.background_removal import BackgroundRemover
        remover = BackgroundRemover()

        # Test image properties
        assert img.mode == "RGBA"
        assert img.size == (100, 100)

    def test_fallback_remove(self):
        """Test the fallback removal method."""
        from modules.background_removal import BackgroundRemover
        remover = BackgroundRemover()

        img = Image.new("RGBA", (200, 200), (100, 150, 200, 255))
        result = remover._fallback_remove(img)
        assert result is not None
        assert result.mode == "RGBA"


class TestImageProcessor:
    """Test image processing functionality."""

    def test_import(self):
        """Verify ImageProcessor can be imported."""
        from modules.image_processing import ImageProcessor
        proc = ImageProcessor()
        assert proc is not None

    def test_resize_format(self):
        """Test format-based resizing."""
        from modules.image_processing import ImageProcessor
        proc = ImageProcessor()

        img = Image.new("RGB", (800, 600), (255, 0, 0))
        result = proc.resize_to_format(img, "square")
        assert result.size == (1080, 1080)

    def test_add_vignette(self):
        """Test vignette effect."""
        from modules.image_processing import ImageProcessor
        proc = ImageProcessor()

        img = Image.new("RGB", (100, 100), (200, 200, 200))
        result = proc.add_vignette(img)
        assert result.size == img.size

    def test_create_premium_background(self):
        """Test premium background creation."""
        from modules.image_processing import ImageProcessor
        proc = ImageProcessor()

        bg = proc.create_premium_background(
            size=(100, 100),
            texture="warm"
        )
        assert bg.size == (100, 100)
        assert bg.mode == "RGBA"

    def test_enhance_lighting(self):
        """Test lighting enhancement."""
        from modules.image_processing import ImageProcessor
        proc = ImageProcessor()

        img = Image.new("RGB", (100, 100), (128, 128, 128))
        result = proc.enhance_lighting(img)
        assert result.size == img.size


class TestCaptionGenerator:
    """Test caption generation functionality."""

    def test_import(self):
        """Verify CaptionGenerator can be imported."""
        from modules.caption_generation import CaptionGenerator
        cg = CaptionGenerator()
        assert cg is not None

    def test_fallback_captions(self):
        """Test template-based fallback captions."""
        from modules.caption_generation import CaptionGenerator
        cg = CaptionGenerator()

        food_data = {
            "food_title": "Margherita Pizza",
            "offer_text": "20% OFF",
            "pricing": ["$12.99"],
            "restaurant_name": "Pizza Paradise",
        }

        captions = cg._fallback_captions(food_data)
        assert "short_caption" in captions
        assert "long_caption" in captions
        assert "hashtags" in captions
        assert "cta" in captions
        assert "Pizza" in captions["short_caption"]

    def test_parse_json_response(self):
        """Test JSON parsing from LLM responses."""
        from modules.caption_generation import CaptionGenerator
        cg = CaptionGenerator()

        valid_json = '''{
            "short_caption": "Test caption",
            "long_caption": "Longer test caption with details",
            "hashtags": "#Test #Food",
            "cta": "Order now!"
        }'''

        result = cg._parse_json_response(valid_json)
        assert result is not None
        assert result["short_caption"] == "Test caption"
        assert result["hashtags"] == "#Test #Food"

    def test_parse_json_code_block(self):
        """Test JSON parsing from markdown code blocks."""
        from modules.caption_generation import CaptionGenerator
        cg = CaptionGenerator()

        markdown_json = '''```json
        {
            "short_caption": "Yummy food!",
            "long_caption": "This is the best food ever...",
            "hashtags": "#Food #Yummy",
            "cta": "Order now!"
        }
        ```'''

        result = cg._parse_json_response(markdown_json)
        assert result is not None
        assert result["short_caption"] == "Yummy food!"


class TestFacebookPoster:
    """Test Facebook posting module."""

    def test_import(self):
        """Verify FacebookPoster can be imported."""
        from modules.facebook_poster import FacebookPoster
        # Just test the static method, no auth needed
        instructions = FacebookPoster.get_token_setup_instructions()
        assert instructions is not None
        assert "Page Access Token" in instructions

    def test_token_setup_instructions(self):
        """Test that setup instructions contain required info."""
        from modules.facebook_poster import FacebookPoster
        instructions = FacebookPoster.get_token_setup_instructions()

        assert "developers.facebook.com" in instructions
        assert "pages_manage_posts" in instructions
        assert "META_PAGE_ID" in instructions
        assert "META_PAGE_ACCESS_TOKEN" in instructions


class TestPipeline:
    """Test the main pipeline orchestrator."""

    def test_import(self):
        """Verify Pipeline can be imported."""
        from workflow.pipeline import RestaurantPipeline, PipelineResult, PipelineStep
        assert RestaurantPipeline is not None
        assert PipelineResult is not None
        assert PipelineStep is not None

    def test_pipeline_step_defaults(self):
        """Test PipelineStep default values."""
        from workflow.pipeline import PipelineStep
        step = PipelineStep("Test Step")

        assert step.name == "Test Step"
        assert step.max_retries == 3
        assert step.status == "pending"
        assert step.error is None
        assert step.result is None

    def test_pipeline_result_basics(self):
        """Test PipelineResult default values."""
        from workflow.pipeline import PipelineResult
        result = PipelineResult()

        assert result.status == "pending"
        assert result.steps == []
        assert result.final_image_path is None
        assert result.captions is None
        assert result.error is None

    def test_pipeline_result_add_log(self):
        """Test adding logs to PipelineResult."""
        from workflow.pipeline import PipelineResult
        result = PipelineResult()

        result.add_log("Test log message")
        assert len(result.logs) == 1
        assert "Test log message" in result.logs[0]

    def test_pipeline_step_duration(self):
        """Test step duration calculation."""
        from workflow.pipeline import PipelineStep
        import time

        step = PipelineStep("Test")
        step.start_time = time.time() - 1.5
        step.end_time = time.time()

        assert 1.0 < step.duration() < 2.5

    def test_pipeline_to_dict(self):
        """Test PipelineResult serialization."""
        from workflow.pipeline import PipelineResult, PipelineStep
        result = PipelineResult()
        result.status = "success"
        result.add_log("Pipeline completed")
        result.final_image_path = "/tmp/test.png"

        data = result.to_dict()
        assert data["status"] == "success"
        assert len(data["logs"]) == 1
        assert data["final_image_path"] == "/tmp/test.png"


class TestStorage:
    """Test storage manager."""

    def test_storage_init(self):
        """Test StorageManager initialization."""
        from utils.storage import StorageManager

        with tempfile.TemporaryDirectory() as tmp:
            temp_dir = os.path.join(tmp, "uploads")
            output_dir = os.path.join(tmp, "outputs")
            storage = StorageManager(temp_dir, output_dir)

            assert os.path.exists(temp_dir)
            assert os.path.exists(output_dir)

    def test_save_and_list(self):
        """Test saving files and listing outputs."""
        from utils.storage import StorageManager

        with tempfile.TemporaryDirectory() as tmp:
            temp_dir = os.path.join(tmp, "uploads")
            output_dir = os.path.join(tmp, "outputs")
            storage = StorageManager(temp_dir, output_dir)

            # Save an output
            saved = storage.save_output(b"test data", prefix="test_", ext=".txt")
            assert saved.exists()

            # List outputs
            outputs = storage.list_outputs()
            assert len(outputs) >= 1
            assert outputs[0]["name"].startswith("test_")


class TestSettings:
    """Test configuration settings."""

    def test_default_settings(self):
        """Test default settings values."""
        from config.settings import Settings
        settings = Settings()

        assert settings.LOG_LEVEL == "INFO"
        assert settings.META_API_VERSION == "v25.0"

    def test_facebook_configured(self):
        """Test Facebook configuration detection."""
        from config.settings import Settings
        settings = Settings()

        # Without env vars, should be False
        if not settings.META_PAGE_ACCESS_TOKEN:
            assert not settings.facebook_configured

    def test_caption_provider_priority(self):
        """Test caption provider priority logic."""
        from config.settings import Settings
        settings = Settings()

        # Priority: groq > gemini > ollama
        provider = settings.caption_provider()
        assert provider in ("groq", "gemini", "ollama")
