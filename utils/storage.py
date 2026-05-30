"""
Local file storage utilities for managing temporary and output files.
"""

import os
import shutil
import uuid
from pathlib import Path
from typing import Optional


class StorageManager:
    """Manages temporary and output file storage for the automation pipeline."""

    def __init__(self, temp_dir: str, output_dir: str):
        self.temp_dir = Path(temp_dir)
        self.output_dir = Path(output_dir)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def save_upload(self, file_data: bytes, filename: str) -> Path:
        """Save an uploaded file to the temp directory with a unique name."""
        ext = Path(filename).suffix or ".jpg"
        unique_name = f"{uuid.uuid4().hex}{ext}"
        dest = self.temp_dir / unique_name
        dest.write_bytes(file_data)
        return dest

    def save_output(self, file_data: bytes, prefix: str = "", ext: str = ".png") -> Path:
        """Save an output file to the output directory."""
        unique_name = f"{prefix}{uuid.uuid4().hex}{ext}"
        dest = self.output_dir / unique_name
        dest.write_bytes(file_data)
        return dest

    def get_temp_path(self, filename: str) -> Path:
        """Get a path in the temp directory."""
        return self.temp_dir / filename

    def get_output_path(self, filename: str) -> Path:
        """Get a path in the output directory."""
        return self.output_dir / filename

    def cleanup_temp(self, max_age_hours: int = 24):
        """Remove temporary files older than max_age_hours."""
        import time
        now = time.time()
        cutoff = now - (max_age_hours * 3600)
        for f in self.temp_dir.iterdir():
            if f.is_file() and f.stat().st_mtime < cutoff:
                f.unlink()

    def list_outputs(self) -> list:
        """List all output files with metadata."""
        results = []
        for f in sorted(self.output_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if f.is_file():
                results.append({
                    "name": f.name,
                    "path": str(f),
                    "size_kb": round(f.stat().st_size / 1024, 2),
                    "created": f.stat().st_mtime,
                })
        return results
