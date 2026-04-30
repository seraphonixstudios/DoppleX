from __future__ import annotations

import base64
import json
import os
import requests
from pathlib import Path
from typing import Dict, Optional

from config.settings import load_settings
from utils.logger import get_logger

logger = get_logger("you2.image_gen")
settings = load_settings()


class ImageGenerator:
    def __init__(self, sd_url: str | None = None):
        self.sd_url = (sd_url or os.environ.get("YOU2_SD_URL", "http://localhost:7860")).rstrip("/")
        self.output_dir = settings.data_dir / "generated_images"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def is_available(self) -> bool:
        try:
            r = requests.get(f"{self.sd_url}/sdapi/v1/samplers", timeout=3)
            return r.status_code == 200
        except Exception:
            return False

    def generate(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 1024,
        height: int = 1024,
        steps: int = 20,
        cfg_scale: float = 7.0,
        seed: int = -1,
        sampler: str = "DPM++ 2M Karras",
    ) -> Optional[Path]:
        """Generate an image via Stable Diffusion WebUI API and return the saved path."""
        if not self.is_available():
            logger.error("Stable Diffusion WebUI not available at %s", self.sd_url)
            return None

        payload = {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "width": width,
            "height": height,
            "steps": steps,
            "cfg_scale": cfg_scale,
            "seed": seed,
            "sampler_name": sampler,
            "batch_size": 1,
            "n_iter": 1,
            "save_images": False,
            "send_images": True,
        }

        try:
            logger.info("Generating image with prompt: %s", prompt[:80])
            r = requests.post(f"{self.sd_url}/sdapi/v1/txt2img", json=payload, timeout=120)
            if r.status_code != 200:
                logger.error("SD API error: %s", r.text)
                return None

            data = r.json()
            images = data.get("images", [])
            if not images:
                logger.error("No images returned from SD")
                return None

            # Save image
            import time
            timestamp = int(time.time())
            image_path = self.output_dir / f"generated_{timestamp}.png"
            img_data = base64.b64decode(images[0])
            image_path.write_bytes(img_data)

            logger.info("Image saved to %s", image_path)
            return image_path

        except Exception as e:
            logger.exception("Image generation failed")
            return None

    def list_recent(self, limit: int = 20) -> list[Path]:
        files = sorted(self.output_dir.glob("generated_*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
        return files[:limit]
