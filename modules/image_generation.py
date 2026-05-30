"""
Image Generation Module - Generates restaurant posters using ComfyUI + SDXL.
Communicates with local ComfyUI instance via HTTP and WebSocket APIs.
"""

import json
import time
import uuid
import requests
import websocket
from pathlib import Path
from typing import Optional, Dict, Any
from PIL import Image
from io import BytesIO
from utils.logger import get_logger

logger = get_logger(__name__)


class ComfyUIGenerator:
    """
    Client for ComfyUI API to generate images using SDXL + ControlNet + IP-Adapter.
    Assumes ComfyUI is running locally with SDXL and ControlNet nodes installed.
    """

    def __init__(self, base_url: str = "http://127.0.0.1:8188"):
        """
        Initialize ComfyUI client.

        Args:
            base_url: ComfyUI server URL (default: http://127.0.0.1:8188)
        """
        self.base_url = base_url.rstrip("/")
        self.client_id = str(uuid.uuid4())
        self.ws_url = f"ws://{self.base_url.split('://')[1]}/ws?clientId={self.client_id}"
        self.upload_url = f"{self.base_url}/upload/image"
        self.prompt_url = f"{self.base_url}/prompt"
        self.history_url = f"{self.base_url}/history"

    def check_health(self) -> bool:
        """Check if ComfyUI server is reachable."""
        try:
            resp = requests.get(f"{self.base_url}/system_stats", timeout=5)
            return resp.status_code == 200
        except requests.RequestException:
            return False

    def upload_image(self, image_path: str) -> Optional[Dict[str, Any]]:
        """
        Upload an image to ComfyUI's input directory.

        Args:
            image_path: Path to image file

        Returns:
            Response dict with filename and subfolder, or None on failure
        """
        try:
            with open(image_path, "rb") as f:
                files = {"image": f}
                resp = requests.post(self.upload_url, files=files, timeout=30)
            if resp.status_code == 200:
                result = resp.json()
                logger.info(f"Image uploaded to ComfyUI: {result.get('name', image_path)}")
                return result
            else:
                logger.error(f"Upload failed: {resp.status_code} {resp.text}")
                return None
        except Exception as e:
            logger.error(f"Upload error: {e}")
            return None

    def load_workflow(self, workflow_path: str) -> dict:
        """
        Load a workflow JSON file (exported in API format from ComfyUI).

        Args:
            workflow_path: Path to the workflow JSON file

        Returns:
            Workflow dict
        """
        with open(workflow_path, "r") as f:
            workflow = json.load(f)
        logger.info(f"Loaded workflow from {workflow_path}")
        return workflow

    def update_workflow(
        self,
        workflow: dict,
        params: Dict[str, Any]
    ) -> dict:
        """
        Update workflow parameters for restaurant poster generation.

        Args:
            workflow: Base workflow dict
            params: Parameters to update:
                - positive_prompt: Main prompt
                - negative_prompt: Negative prompt
                - image_name: Input image filename (for ControlNet/IP-Adapter)
                - seed: Random seed
                - steps: Sampling steps
                - cfg: CFG scale
                - width: Output width
                - height: Output height

        Returns:
            Updated workflow dict
        """
        # Deep copy
        workflow = json.loads(json.dumps(workflow))

        for node_id, node in list(workflow.items()):
            # Skip non-dict values (e.g. description, notes, or other metadata)
            if not isinstance(node, dict):
                continue

            class_type = node.get("class_type", "")
            if not class_type:
                continue

            # CLIPTextEncode nodes — update positive/negative prompts by position
            if class_type == "CLIPTextEncode":
                if "inputs" in node and "text" in node["inputs"]:
                    # Determine if this is the positive or negative prompt node
                    # by checking for "negative" in default text
                    is_negative = "blurry" in node["inputs"].get("text", "").lower() or "negative" in node["inputs"].get("text", "").lower()
                    if is_negative:
                        node["inputs"]["text"] = params.get(
                            "negative_prompt",
                            "blurry, low quality, distorted, watermark, text, signature"
                        )
                    else:
                        node["inputs"]["text"] = params.get(
                            "positive_prompt",
                            "a professional restaurant food poster, cinematic lighting, premium quality"
                        )

            # KSampler / SamplerCustom
            elif class_type in ("KSampler", "SamplerCustom", "KSamplerAdvanced"):
                inputs = node.get("inputs", {})
                if "seed" in inputs:
                    inputs["seed"] = params.get("seed", int(time.time()))
                if "steps" in inputs:
                    inputs["steps"] = params.get("steps", 30)
                if "cfg" in inputs:
                    inputs["cfg"] = params.get("cfg", 7.5)

            # EmptyLatentImage
            elif class_type == "EmptyLatentImage":
                inputs = node.get("inputs", {})
                if "width" in inputs:
                    inputs["width"] = params.get("width", 1080)
                if "height" in inputs:
                    inputs["height"] = params.get("height", 1080)

            # LoadImage (input image for ControlNet/IP-Adapter)
            elif class_type == "LoadImage":
                inputs = node.get("inputs", {})
                if "image" in inputs:
                    image_name = params.get("image_name")
                    if image_name:
                        inputs["image"] = image_name

        return workflow

    def queue_prompt(self, workflow: dict) -> Optional[str]:
        """
        Queue a prompt/workflow to ComfyUI.

        Args:
            workflow: Workflow dict to execute

        Returns:
            Prompt ID if successful, None otherwise
        """
        payload = {
            "client_id": self.client_id,
            "prompt": workflow,
        }
        try:
            resp = requests.post(self.prompt_url, json=payload, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                # ComfyUI returns {'prompt_id': '...'} on success
                if isinstance(data, dict):
                    prompt_id = data.get("prompt_id")
                    if prompt_id:
                        logger.info(f"Prompt queued: {prompt_id}")
                        return prompt_id
                    # Check for error field
                    error = data.get("error", data.get("node_errors", {}))
                    if error:
                        logger.error(f"ComfyUI queue error: {error}")
                        return None
                logger.error(f"Unexpected ComfyUI response: {data}")
                return None
            else:
                logger.error(f"Queue failed: {resp.status_code} {resp.text[:500]}")
                return None
        except Exception as e:
            logger.error(f"Queue error: {e}")
            return None

    def wait_for_completion(self, prompt_id: str, timeout: int = 300) -> bool:
        """
        Wait for a queued prompt to complete via WebSocket.

        Args:
            prompt_id: Prompt ID to wait for
            timeout: Maximum wait time in seconds

        Returns:
            True if completed successfully, False otherwise
        """
        try:
            ws = websocket.create_connection(self.ws_url, timeout=timeout)
            start_time = time.time()

            while time.time() - start_time < timeout:
                try:
                    msg = json.loads(ws.recv())
                    msg_type = msg.get("type", "")

                    if msg_type == "execution_start":
                        logger.info("Execution started")

                    elif msg_type == "execution_cached":
                        logger.info("Execution cached")

                    elif msg_type == "progress":
                        node = msg.get("data", {}).get("node", "?")
                        step = msg.get("data", {}).get("value", 0)
                        max_step = msg.get("data", {}).get("max", 1)
                        pct = (step / max_step) * 100
                        logger.debug(f"Progress [{node}]: {step}/{max_step} ({pct:.0f}%)")

                    elif msg_type == "executing":
                        node = msg.get("data", {}).get("node")
                        if node is None:
                            logger.info("Execution complete")
                            ws.close()
                            return True

                    elif msg_type == "execution_error":
                        error = msg.get("data", {})
                        logger.error(f"Execution error: {error.get('exception_message', 'Unknown')}")
                        ws.close()
                        return False

                except websocket.WebSocketTimeoutException:
                    logger.debug("WebSocket timeout (no message)")
                    continue

            logger.warning(f"Timeout waiting for prompt {prompt_id}")
            ws.close()
            return False

        except Exception as e:
            logger.error(f"WebSocket error: {e}")
            # Fallback: poll history
            return self._poll_history(prompt_id, timeout)

    def _poll_history(self, prompt_id: str, timeout: int = 300) -> bool:
        """Fallback: poll history endpoint for completion."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                resp = requests.get(f"{self.history_url}/{prompt_id}", timeout=10)
                if resp.status_code == 200 and resp.json():
                    logger.info(f"Prompt {prompt_id} found in history")
                    return True
            except requests.RequestException:
                pass
            time.sleep(2)
        return False

    def get_output_images(self, prompt_id: str) -> list:
        """
        Get generated images from a completed prompt.

        Args:
            prompt_id: Prompt ID

        Returns:
            List of PIL Image objects
        """
        try:
            # Wait a moment for ComfyUI to finish writing the image
            time.sleep(1)

            resp = requests.get(f"{self.history_url}/{prompt_id}", timeout=15)
            if resp.status_code != 200:
                logger.error(f"Failed to get history: {resp.status_code}")
                return []

            history = resp.json()
            # history is {prompt_id: {...}} on success
            if not isinstance(history, dict):
                logger.error(f"Unexpected history format: {type(history).__name__}")
                return []

            prompt_data = history.get(prompt_id, {})
            if not isinstance(prompt_data, dict):
                logger.error(f"Prompt data not found in history")
                return []

            outputs = prompt_data.get("outputs", {})
            if not isinstance(outputs, dict):
                logger.info("No outputs in history")
                return []

            images = []
            for node_id, node_output in outputs.items():
                if not isinstance(node_output, dict):
                    continue
                for output_type, files in node_output.items():
                    if output_type == "images":
                        if not isinstance(files, list):
                            continue
                        for file_info in files:
                            if not isinstance(file_info, dict):
                                continue
                            filename = file_info.get("filename", "")
                            subfolder = file_info.get("subfolder", "")
                            if not filename:
                                continue

                            img_url = f"{self.base_url}/view?filename={filename}&subfolder={subfolder}&type=output"
                            img_resp = requests.get(img_url, timeout=30)
                            if img_resp.status_code == 200:
                                img = Image.open(BytesIO(img_resp.content))
                                images.append(img)
                                logger.info(f"Retrieved output image: {filename}")

            return images

        except Exception as e:
            logger.error(f"Error getting output images: {e}")
            return []

    def generate_restaurant_poster(
        self,
        workflow_path: str,
        input_image_path: Optional[str] = None,
        positive_prompt: str = "",
        negative_prompt: str = "",
        seed: Optional[int] = None,
        width: int = 1080,
        height: int = 1080,
        steps: int = 30,
        cfg: float = 7.5,
    ) -> Optional[Image.Image]:
        """
        Full pipeline: Upload image, queue workflow, wait, retrieve result.

        Args:
            workflow_path: Path to API-format workflow JSON
            input_image_path: Path to input image (for ControlNet/IP-Adapter)
            positive_prompt: Positive prompt for generation
            negative_prompt: Negative prompt
            seed: Random seed (auto if None)
            width: Output width
            height: Output height
            steps: Sampling steps
            cfg: CFG scale

        Returns:
            Generated PIL Image, or None on failure
        """
        if not self.check_health():
            logger.error(
                "ComfyUI is not running. Start it first:\n"
                "cd ComfyUI && python main.py --listen"
            )
            return None

        # Load workflow
        try:
            workflow = self.load_workflow(workflow_path)
        except FileNotFoundError:
            logger.error(f"Workflow file not found: {workflow_path}")
            logger.info(
                "To create a workflow:\n"
                "1. Open ComfyUI in browser\n"
                "2. Create your SDXL workflow with ControlNet\n"
                "3. Click Settings > Enable Dev Mode\n"
                "4. Save (API Format) to comfyui/workflows/\n"
                "5. Or the system will use a default pipeline"
            )
            return None

        # Upload input image if provided
        image_name = None
        if input_image_path and Path(input_image_path).exists():
            upload_result = self.upload_image(input_image_path)
            if upload_result:
                image_name = upload_result.get("name")

        # Prepare parameters
        if seed is None:
            seed = int(time.time() * 1000) % (2**32)

        params = {
            "positive_prompt": positive_prompt,
            "negative_prompt": negative_prompt or "blurry, low quality, distorted, watermark, text, signature, poorly drawn",
            "image_name": image_name,
            "seed": seed,
            "steps": steps,
            "cfg": cfg,
            "width": width,
            "height": height,
        }

        # Update workflow
        workflow = self.update_workflow(workflow, params)

        # Queue prompt
        prompt_id = self.queue_prompt(workflow)
        if not prompt_id:
            return None

        # Wait for completion
        success = self.wait_for_completion(prompt_id)
        if not success:
            return None

        # Get output images
        images = self.get_output_images(prompt_id)
        if images:
            logger.info(f"Generated {len(images)} image(s)")
            return images[0]

        return None

    def generate_with_default_pipeline(
        self,
        positive_prompt: str,
        negative_prompt: str = "",
        width: int = 1080,
        height: int = 1080,
        seed: Optional[int] = None,
    ) -> Optional[Image.Image]:
        """
        Generate image without a workflow file by creating a minimal prompt.

        Note: This requires the server-side workflow to be set up properly.
        For full ControlNet/IP-Adapter support, use generate_restaurant_poster
        with a proper workflow file.

        Falls back to a simple SDXL text-to-image if no workflow file is available.
        """
        if seed is None:
            seed = int(time.time() * 1000) % (2**32)

        # Minimal workflow for basic SDXL generation
        workflow = {
            "3": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": seed,
                    "steps": 30,
                    "cfg": 7.5,
                    "sampler_name": "euler",
                    "scheduler": "normal",
                    "denoise": 1.0,
                    "model": ["4", 0],
                    "positive": ["6", 0],
                    "negative": ["7", 0],
                    "latent_image": ["5", 0],
                }
            },
            "4": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": "sd_xl_base_1.0.safetensors"}
            },
            "5": {
                "class_type": "EmptyLatentImage",
                "inputs": {"width": width, "height": height, "batch_size": 1}
            },
            "6": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": positive_prompt,
                    "clip": ["4", 1]
                }
            },
            "7": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": negative_prompt or "blurry, low quality",
                    "clip": ["4", 1]
                }
            },
            "8": {
                "class_type": "VAEDecode",
                "inputs": {
                    "samples": ["3", 0],
                    "vae": ["4", 2]
                }
            },
            "9": {
                "class_type": "SaveImage",
                "inputs": {
                    "filename_prefix": "restaurant_poster",
                    "images": ["8", 0]
                }
            }
        }

        prompt_id = self.queue_prompt(workflow)
        if not prompt_id:
            return None

        success = self.wait_for_completion(prompt_id)
        if not success:
            return None

        images = self.get_output_images(prompt_id)
        return images[0] if images else None
