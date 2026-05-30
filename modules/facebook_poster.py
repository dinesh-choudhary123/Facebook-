"""
Facebook Poster Module - Posts content to Facebook Pages using Meta Graph API.
Uses OAuth 2.0 authentication only. No raw password automation.

Posting Strategy:
  Uses POST /{page-id}/photos with published=true — the same endpoint
  that manual Facebook photo uploads use. This creates proper feed posts
  visible to ALL users (not just admins).
"""

import time
from typing import Optional, Dict, Any
from pathlib import Path
from utils.logger import get_logger

logger = get_logger(__name__)


class FacebookPosterError(Exception):
    """Base exception for Facebook posting errors."""
    pass


class TokenExpiredError(FacebookPosterError):
    """The access token has expired or is invalid."""
    pass


class FacebookPoster:
    """
    Post restaurant content to Facebook Pages using Meta Graph API.
    Requires a Page Access Token with pages_manage_posts permission.
    """

    GRAPH_API_BASE = "https://graph.facebook.com"

    def __init__(
        self,
        page_id: str,
        page_access_token: str,
        api_version: str = "v25.0",
        app_id: str = "",
        app_secret: str = "",
    ):
        """
        Initialize Facebook poster.

        Args:
            page_id: Facebook Page ID
            page_access_token: Page Access Token (long-lived)
            api_version: Graph API version
            app_id: Meta App ID (for token refresh)
            app_secret: Meta App Secret (for token refresh)
        """
        self.page_id = page_id
        self.page_access_token = page_access_token
        self.api_version = api_version
        self.app_id = app_id
        self.app_secret = app_secret
        self.base_url = f"{self.GRAPH_API_BASE}/{api_version}"

    def check_token_valid(self) -> bool:
        """Verify the Page Access Token is still valid."""
        try:
            import requests
            url = f"{self.base_url}/me"
            params = {"access_token": self.page_access_token}
            resp = requests.get(url, params=params, timeout=10)

            if resp.status_code == 200:
                logger.info("Page Access Token is valid")
                return True
            else:
                error_data = resp.json().get("error", {})
                error_msg = error_data.get("message", "Unknown error")
                error_code = error_data.get("code", 0)
                logger.warning(f"Token validation failed (code {error_code}): {error_msg}")
                return False

        except Exception as e:
            logger.error(f"Token check error: {e}")
            return False

    def _extract_post_id(self, response: Dict[str, Any]) -> str:
        """
        Extract the feed post ID from a /photos endpoint response.

        The /photos endpoint returns:
          { "id": "photo_id", "post_id": "pageid_postid" }
        where 'post_id' is the actual feed post ID and 'id' is the photo ID.
        Prefer 'post_id' if available, fall back to 'id'.
        """
        return response.get("post_id") or response.get("id", "")

    def _build_post_url(self, post_id: str) -> str:
        """
        Build a proper Facebook post URL.
        """
        if "_" in post_id:
            return f"https://www.facebook.com/{post_id}"
        return f"https://www.facebook.com/photo.php?fbid={post_id}"

    def post_photo(
        self,
        image_path: str,
        caption: str = "",
        published: bool = True,
    ) -> Dict[str, Any]:
        """
        Post a photo to the Facebook Page feed/timeline.

        Uses POST /{page-id}/photos with published=true — the same endpoint
        that manual Facebook photo uploads use. This ensures the photo appears
        as a proper feed post visible to ALL users (not just admins).

        The photo appears in:
        - The Page's main timeline/feed (as a feed post)
        - The Page's Photos section (this is normal Facebook behavior)

        Args:
            image_path: Path to the image file
            caption: Caption text (becomes the post message)
            published: Whether to publish immediately

        Returns:
            Response dict with post_id, post_url, photo_id, verification
        """
        image_path = Path(image_path)
        if not image_path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        import requests

        for attempt in range(3):
            try:
                url = f"{self.base_url}/{self.page_id}/photos"
                with open(image_path, "rb") as img_file:
                    files = {"source": img_file}
                    data = {
                        "access_token": self.page_access_token,
                        "message": caption,
                        "published": "true" if published else "false",
                    }
                    resp = requests.post(url, files=files, data=data, timeout=60)

                if resp.status_code == 200:
                    result = resp.json()
                    post_id = self._extract_post_id(result)
                    photo_id = result.get("id", post_id)
                    post_url = self._build_post_url(post_id)

                    logger.info(f"Photo posted successfully! Post ID: {post_id}")

                    verification = self._verify_post_visibility(post_id)

                    return {
                        "success": True,
                        "post_id": post_id,
                        "post_url": post_url,
                        "photo_id": photo_id,
                        "verification": verification,
                    }

                error_data = resp.json().get("error", {})
                error_msg = error_data.get("message", "Unknown error")
                error_code = error_data.get("code", 0)

                logger.warning(f"Post attempt {attempt + 1}/3 failed: Code {error_code} - {error_msg}")

                if error_code in (190, 102, 200) or "access token" in error_msg.lower():
                    raise TokenExpiredError(f"Token expired/invalid: {error_msg}")

                if attempt < 2:
                    time.sleep(2 ** attempt)

            except (TokenExpiredError, FileNotFoundError):
                raise
            except Exception as e:
                logger.error(f"Post attempt {attempt + 1}/3 error: {e}")
                if attempt < 2:
                    time.sleep(2 ** attempt)
                if attempt >= 2:
                    raise FacebookPosterError(f"Failed to post photo after 3 attempts: {e}")

        raise FacebookPosterError("Failed to post photo after 3 attempts")

    def post_with_photo_url(
        self,
        photo_url: str,
        caption: str = "",
        published: bool = True,
    ) -> Dict[str, Any]:
        """
        Post a photo to the Facebook Page feed using a publicly accessible image URL.

        Uses POST /{page-id}/photos with published=true and the url parameter
        instead of a file upload.

        Args:
            photo_url: Public URL of the image
            caption: Caption text (becomes the post message)
            published: Whether to publish immediately

        Returns:
            Response dict with post_id, post_url, photo_id, verification

        Raises:
            TokenExpiredError: If the access token is expired
            FacebookPosterError: On other failures
        """
        import requests

        for attempt in range(3):
            try:
                url = f"{self.base_url}/{self.page_id}/photos"
                data = {
                    "access_token": self.page_access_token,
                    "url": photo_url,
                    "message": caption,
                    "published": "true" if published else "false",
                }
                resp = requests.post(url, data=data, timeout=60)

                if resp.status_code == 200:
                    result = resp.json()
                    post_id = self._extract_post_id(result)
                    photo_id = result.get("id", post_id)
                    post_url = self._build_post_url(post_id)

                    logger.info(f"Photo posted via URL successfully! Post ID: {post_id}")

                    verification = self._verify_post_visibility(post_id)

                    return {
                        "success": True,
                        "post_id": post_id,
                        "post_url": post_url,
                        "photo_id": photo_id,
                        "verification": verification,
                    }

                error_data = resp.json().get("error", {})
                error_msg = error_data.get("message", "Unknown error")
                error_code = error_data.get("code", 0)

                logger.warning(
                    f"URL post attempt {attempt + 1}/3 failed: "
                    f"Code {error_code} - {error_msg}"
                )

                if error_code in (190, 102, 200) or "access token" in error_msg.lower():
                    raise TokenExpiredError(
                        f"Your Facebook access token has expired or is invalid. "
                        f"Error: {error_msg}\n\n"
                        f"Generate a new token and update .env"
                    )

                if attempt < 2:
                    time.sleep(2 ** attempt)

            except TokenExpiredError:
                raise
            except Exception as e:
                logger.error(f"URL post attempt {attempt + 1}/3 error: {e}")
                if attempt < 2:
                    time.sleep(2 ** attempt)
                if attempt >= 2:
                    raise FacebookPosterError(f"Failed to post via URL after 3 attempts: {e}")

        raise FacebookPosterError(f"Failed to post photo via URL after 3 attempts")

    # ── Verification ────────────────────────────────────

    def _verify_post_visibility(self, post_id: str) -> Dict[str, Any]:
        """
        Verify that a published post is publicly visible in the Page feed.

        Uses GET /{post-id} with fields to check:
        - id, message, created_time: The post exists
        - is_published: The post is not a draft
        - permalink_url: The public URL is accessible

        Args:
            post_id: The post ID to verify

        Returns:
            Dict with verification results
        """
        result = {
            "verified": False,
            "post_exists": False,
            "is_published": False,
            "permalink_url": "",
            "errors": [],
        }

        try:
            import requests

            url = f"{self.base_url}/{post_id}"
            params = {
                "access_token": self.page_access_token,
                "fields": "id,message,created_time,permalink_url,is_published,privacy,scheduled_publish_time",
            }
            resp = requests.get(url, params=params, timeout=10)

            if resp.status_code == 200:
                data = resp.json()
                result["post_exists"] = True
                result["permalink_url"] = data.get("permalink_url", "")
                result["post_id"] = data.get("id", "")
                result["created_time"] = data.get("created_time", "")

                scheduled_publish_time = data.get("scheduled_publish_time", None)
                if scheduled_publish_time is not None:
                    result["errors"].append(
                        f"Post is scheduled for future time: {scheduled_publish_time}"
                    )

                is_published = data.get("is_published", False)
                if is_published is False:
                    result["is_published"] = False
                    result["errors"].append("Post is in draft/unpublished state")
                else:
                    result["is_published"] = True

                privacy = data.get("privacy", {})
                privacy_value = privacy.get("value", "")
                if privacy_value and privacy_value != "EVERYONE":
                    result["errors"].append(
                        f"Post privacy is '{privacy_value}', not PUBLIC"
                    )

                feed_check = self._check_post_in_feed(post_id)
                result["in_feed"] = feed_check

                if (
                    result["post_exists"]
                    and result["is_published"]
                    and len(result["errors"]) == 0
                ):
                    result["verified"] = True
                    logger.info(f"Post {post_id} verified: public feed post \u2713")
                else:
                    logger.warning(
                        f"Post {post_id} verification issues: {result['errors']}"
                    )

            else:
                error_data = resp.json().get("error", {})
                error_msg = error_data.get("message", "Unknown error")
                result["errors"].append(f"API error verifying post: {error_msg}")
                logger.warning(f"Verification API error for {post_id}: {error_msg}")

        except Exception as e:
            result["errors"].append(f"Verification exception: {e}")
            logger.error(f"Verification error for {post_id}: {e}")

        return result

    def _check_post_in_feed(self, post_id: str) -> Dict[str, Any]:
        """
        Check if the post appears in the Page's published feed.
        """
        result = {"found": False, "in_feed": False}
        try:
            import requests

            url = f"{self.base_url}/{self.page_id}/feed"
            params = {
                "access_token": self.page_access_token,
                "limit": 20,
                "fields": "id,message,created_time,permalink_url",
            }
            resp = requests.get(url, params=params, timeout=10)

            if resp.status_code == 200:
                feed_data = resp.json().get("data", [])
                result["found"] = True
                for post in feed_data:
                    if post.get("id") == post_id:
                        result["in_feed"] = True
                        result["feed_position"] = feed_data.index(post)
                        break

                if result["in_feed"]:
                    logger.info(f"Post {post_id} confirmed in Page feed \u2713")
                else:
                    logger.warning(f"Post {post_id} not found in recent Page feed")
            else:
                logger.warning(f"Could not fetch feed to verify post {post_id}")

        except Exception as e:
            logger.error(f"Feed check error: {e}")

        return result

    def get_page_info(self) -> Optional[Dict[str, Any]]:
        """Get basic information about the connected Page."""
        try:
            import requests
            url = f"{self.base_url}/{self.page_id}"
            params = {
                "access_token": self.page_access_token,
                "fields": "id,name,about,fan_count,link",
            }
            resp = requests.get(url, params=params, timeout=10)

            if resp.status_code == 200:
                return resp.json()
            else:
                logger.warning(f"Failed to get page info: {resp.text[:200]}")
                return None

        except Exception as e:
            logger.error(f"Error getting page info: {e}")
            return None

    def get_recent_posts(self, limit: int = 10) -> list:
        """Get recent posts from the Page."""
        try:
            import requests
            url = f"{self.base_url}/{self.page_id}/posts"
            params = {
                "access_token": self.page_access_token,
                "limit": limit,
                "fields": "id,message,created_time,permalink_url",
            }
            resp = requests.get(url, params=params, timeout=10)

            if resp.status_code == 200:
                return resp.json().get("data", [])
            return []

        except Exception as e:
            logger.error(f"Error getting recent posts: {e}")
            return []

    @staticmethod
    def get_token_setup_instructions() -> str:
        """Return instructions for obtaining a Page Access Token."""
        return """
=== How to Get Facebook Page Access Token ===

1. Go to https://developers.facebook.com/
2. Create or open your App
3. Go to App Settings > Basic and note your App ID & App Secret
4. Go to Tools > Graph API Explorer
5. Select your App and get a User Token with these permissions:
   - pages_manage_posts
   - pages_read_engagement
6. Click "Add a Page" and select your restaurant page
7. Click "Generate Access Token"
8. Exchange for a long-lived Page Access Token:
   GET /oauth/access_token?
     grant_type=fb_exchange_token&
     client_id={app_id}&
     client_secret={app_secret}&
     fb_exchange_token={short_lived_token}

9. Save the following to your .env file:
   META_PAGE_ID=<your-page-id>
   META_PAGE_ACCESS_TOKEN=<your-long-lived-token>
   META_APP_ID=<your-app-id>
   META_APP_SECRET=<your-app-secret>
        """.strip()

    @staticmethod
    def debug_token(access_token: str, app_id: str, app_secret: str) -> Optional[Dict]:
        """Debug a token to check validity and permissions."""
        try:
            import requests
            url = "https://graph.facebook.com/debug_token"
            params = {
                "input_token": access_token,
                "access_token": f"{app_id}|{app_secret}",
            }
            resp = requests.get(url, params=params, timeout=10)

            if resp.status_code == 200:
                return resp.json().get("data", {})
            return None

        except Exception as e:
            logger.error(f"Debug token error: {e}")
            return None
