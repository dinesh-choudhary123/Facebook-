"""
Caption Generation Module - Generates social media captions for restaurant posters.
Supports multiple providers in priority order: Groq -> Gemini -> Ollama (local).
"""

import re
import json
from typing import Optional, Dict, List
from utils.logger import get_logger

logger = get_logger(__name__)


class CaptionGenerator:
    """
    Generate professional Facebook captions for restaurant food posters.
    Falls back through providers: Groq -> Gemini -> Ollama.
    """

    def __init__(
        self,
        groq_api_key: str = "",
        gemini_api_key: str = "",
        ollama_host: str = "http://127.0.0.1",
        ollama_port: int = 11434,
        ollama_model: str = "llama3.2",
    ):
        self.groq_api_key = groq_api_key
        self.gemini_api_key = gemini_api_key
        self.ollama_host = ollama_host.rstrip("/")
        self.ollama_port = ollama_port
        self.ollama_model = ollama_model

    def generate_captions(self, food_data: Dict[str, str]) -> Dict[str, str]:
        """
        Generate all caption components for a restaurant post.

        Args:
            food_data: Dict with keys:
                - food_title: Name of the food item
                - offer_text: Promotion/discount text
                - pricing: Price information
                - restaurant_name: (optional) Restaurant name

        Returns:
            Dict with keys: short_caption, long_caption, hashtags, cta
        """
        prompt = self._build_prompt(food_data)

        result = self._try_groq(prompt)
        if not result:
            result = self._try_gemini(prompt)
        if not result:
            result = self._try_ollama(prompt)
        if not result:
            result = self._fallback_captions(food_data)

        return result

    def generate_short_caption(self, food_data: Dict[str, str]) -> str:
        """Generate a short, punchy caption (1-2 lines)."""
        captions = self.generate_captions(food_data)
        return captions.get("short_caption", "")

    def generate_long_caption(self, food_data: Dict[str, str]) -> str:
        """Generate a detailed, engaging caption."""
        captions = self.generate_captions(food_data)
        return captions.get("long_caption", "")

    def _build_prompt(self, food_data: Dict[str, str]) -> str:
        """Build the prompt for caption generation."""
        title = food_data.get("food_title", "Delicious Food")
        offer = food_data.get("offer_text", "")
        pricing = food_data.get("pricing", "")
        restaurant = food_data.get("restaurant_name", "Our Restaurant")

        return f"""You are a professional social media manager for a restaurant. Generate Facebook captions for this food poster.

FOOD TITLE: {title}
OFFER: {offer}
PRICING: {pricing}
RESTAURANT: {restaurant}

Generate the following in JSON format:
1. "short_caption": A short, punchy 1-2 line caption with emojis (max 150 chars)
2. "long_caption": A detailed 3-5 line engaging caption with emojis (max 500 chars)
3. "hashtags": 8-12 relevant hashtags as a comma-separated string
4. "cta": A call to action (max 60 chars)

Respond ONLY with valid JSON, no other text."""

    def _try_groq(self, prompt: str) -> Optional[Dict[str, str]]:
        """Try Groq API first."""
        if not self.groq_api_key:
            logger.info("Groq API key not configured, skipping")
            return None

        try:
            import requests
            headers = {
                "Authorization": f"Bearer {self.groq_api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": "llama-3.3-70b-versatile",
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a restaurant social media expert. Return ONLY valid JSON."
                    },
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.7,
                "max_tokens": 500,
            }

            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=30,
            )

            if resp.status_code == 200:
                content = resp.json()["choices"][0]["message"]["content"]
                result = self._parse_json_response(content)
                if result:
                    logger.info("Captions generated via Groq API")
                    return result

            logger.warning(f"Groq API returned {resp.status_code}: {resp.text[:200]}")
            return None

        except ImportError:
            logger.warning("requests library not installed")
            return None
        except Exception as e:
            logger.error(f"Groq API error: {e}")
            return None

    def _try_gemini(self, prompt: str) -> Optional[Dict[str, str]]:
        """Try Gemini API as fallback."""
        if not self.gemini_api_key:
            logger.info("Gemini API key not configured, skipping")
            return None

        try:
            import requests

            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={self.gemini_api_key}"

            payload = {
                "contents": [{
                    "parts": [{"text": f"You are a restaurant social media expert. Return ONLY valid JSON.\n\n{prompt}"}]
                }],
                "generationConfig": {
                    "temperature": 0.7,
                    "maxOutputTokens": 500,
                }
            }

            resp = requests.post(url, json=payload, timeout=30)

            if resp.status_code == 200:
                content = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                result = self._parse_json_response(content)
                if result:
                    logger.info("Captions generated via Gemini API")
                    return result

            logger.warning(f"Gemini API returned {resp.status_code}")
            return None

        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            return None

    def _try_ollama(self, prompt: str) -> Optional[Dict[str, str]]:
        """Try local Ollama as final fallback."""
        try:
            import requests

            url = f"{self.ollama_host}:{self.ollama_port}/api/generate"
            full_prompt = f"You are a restaurant social media expert. Return ONLY valid JSON.\n\n{prompt}"

            payload = {
                "model": self.ollama_model,
                "prompt": full_prompt,
                "stream": False,
                "temperature": 0.7,
            }

            resp = requests.post(url, json=payload, timeout=60)

            if resp.status_code == 200:
                content = resp.json()["response"]
                result = self._parse_json_response(content)
                if result:
                    logger.info(f"Captions generated via Ollama ({self.ollama_model})")
                    return result

            logger.warning(f"Ollama returned {resp.status_code}")
            return None

        except requests.ConnectionError:
            logger.warning(
                f"Ollama not running at {self.ollama_host}:{self.ollama_port}. "
                "Start with: ollama serve"
            )
            return None
        except Exception as e:
            logger.error(f"Ollama error: {e}")
            return None

    def _parse_json_response(self, text: str) -> Optional[Dict[str, str]]:
        """Parse JSON from LLM response, handling markdown code blocks."""
        # Try to find JSON in code blocks
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
        if json_match:
            text = json_match.group(1)

        # Clean and parse
        text = text.strip()
        try:
            result = json.loads(text)
            # Validate required fields
            if isinstance(result, dict):
                required = ["short_caption", "long_caption", "hashtags", "cta"]
                if all(k in result for k in required):
                    return {
                        "short_caption": str(result.get("short_caption", "")),
                        "long_caption": str(result.get("long_caption", "")),
                        "hashtags": str(result.get("hashtags", "")),
                        "cta": str(result.get("cta", "")),
                    }
            return None
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON response: {e}")
            return None

    def _fallback_captions(self, food_data: Dict[str, str]) -> Dict[str, str]:
        """Generate template-based captions when no AI provider is available."""
        title = food_data.get("food_title", "Delicious Food")
        offer = food_data.get("offer_text", "")
        pricing = food_data.get("pricing", "")

        price_str = pricing[0] if isinstance(pricing, list) and pricing else str(pricing)

        return {
            "short_caption": f"🍽️ {title} - {offer or 'Available Now!'} {price_str}",
            "long_caption": (
                f"🌟 **{title}** 🌟\n\n"
                f"{offer + ' ' if offer else ''}"
                f"Starting at {price_str}! "
                f"Made with fresh ingredients and served with love.\n\n"
                f"📸 Captured fresh from our kitchen to your table.\n"
                f"👉 Order now or visit us today!"
            ),
            "hashtags": "#Restaurant #FoodLover #Delicious #Foodie #FreshFood "
                        "#FoodPhotography #Tasty #Yummy #LocalEats #FoodGram",
            "cta": "Order Now - Link in Bio! 📲",
        }


def generate_simple_caption(
    food_title: str,
    offer: str = "",
    pricing: str = "",
    restaurant: str = "",
    groq_key: str = "",
    gemini_key: str = "",
) -> Dict[str, str]:
    """
    Convenience function for quick caption generation.
    """
    generator = CaptionGenerator(
        groq_api_key=groq_key,
        gemini_api_key=gemini_key,
    )
    return generator.generate_captions({
        "food_title": food_title,
        "offer_text": offer,
        "pricing": pricing,
        "restaurant_name": restaurant,
    })
