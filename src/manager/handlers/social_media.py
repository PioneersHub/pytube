"""
Multi-provider social media posting service.

This module provides a unified interface for posting to multiple social media platforms:
- LinkedIn
- Twitter/X
- Mastodon
- Bluesky

Configuration in config.yaml/config_local.yaml:

    twitter:
        api_key: "your-key"
        api_secret: "your-secret"
        access_token: "your-token"
        access_token_secret: "your-secret"
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from manager import conf, logger
from manager.utils.common import SafeConfig


class SocialMediaProvider(ABC):
    """Abstract base class for social media providers."""

    @abstractmethod
    def post(self, text: str, image_path: Path | None = None) -> dict[str, Any]:
        """Post content to social media."""
        pass

    @abstractmethod
    def validate_config(self) -> bool:
        """Validate provider configuration."""
        pass


class TwitterProvider(SocialMediaProvider):
    """Twitter/X posting provider."""

    def __init__(self):
        safe_conf = SafeConfig(conf)
        self.safe_conf = safe_conf
        self.api_key = self.safe_conf.get("twitter.api_key")
        self.api_secret = self.safe_conf.get("twitter.api_secret")
        self.access_token = self.safe_conf.get("twitter.access_token")
        self.access_token_secret = self.safe_conf.get("twitter.access_token_secret")

    def validate_config(self) -> bool:
        """Validate Twitter configuration."""
        required = [self.api_key, self.api_secret, self.access_token, self.access_token_secret]
        if not all(required):
            logger.error("Twitter configuration incomplete")
            return False
        return True

    def post(self, text: str, image_path: Path | None = None) -> dict[str, Any]:
        """Post to Twitter/X."""
        if not self.validate_config():
            raise ValueError("Twitter configuration invalid")

        try:
            import tweepy
        except ImportError:
            raise ImportError("Please install tweepy: pip install tweepy")

        # Authenticate with Twitter
        auth = tweepy.OAuthHandler(self.api_key, self.api_secret)
        auth.set_access_token(self.access_token, self.access_token_secret)
        api = tweepy.API(auth)

        try:
            if image_path and image_path.exists():
                # Upload image and post
                media = api.media_upload(str(image_path))
                tweet = api.update_status(status=text, media_ids=[media.media_id])
            else:
                # Text-only post
                tweet = api.update_status(status=text)

            return {
                "id": tweet.id_str,
                "url": f"https://twitter.com/user/status/{tweet.id_str}",
                "created_at": tweet.created_at.isoformat(),
            }
        except Exception as e:
            logger.error(f"Failed to post to Twitter: {e}")
            raise


class MastodonProvider(SocialMediaProvider):
    """Mastodon posting provider."""

    def __init__(self):
        safe_conf = SafeConfig(conf)
        self.safe_conf = safe_conf
        self.instance_url = self.safe_conf.get("mastodon.instance_url", "https://mastodon.social")
        self.access_token = self.safe_conf.get("mastodon.access_token")
        self.visibility = self.safe_conf.get("mastodon.visibility", "public")

    def validate_config(self) -> bool:
        """Validate Mastodon configuration."""
        if not self.access_token:
            logger.error("Mastodon access_token not configured")
            return False
        return True

    def post(self, text: str, image_path: Path | None = None) -> dict[str, Any]:
        """Post to Mastodon."""
        if not self.validate_config():
            raise ValueError("Mastodon configuration invalid")

        try:
            from mastodon import Mastodon
        except ImportError:
            raise ImportError("Please install Mastodon.py: pip install Mastodon.py")

        # Create Mastodon instance
        mastodon = Mastodon(access_token=self.access_token, api_base_url=self.instance_url)

        try:
            media_ids = []
            if image_path and image_path.exists():
                # Upload media first
                media = mastodon.media_post(str(image_path))
                media_ids = [media["id"]]

            # Post the toot
            toot = mastodon.status_post(text, media_ids=media_ids, visibility=self.visibility)

            return {"id": toot["id"], "url": toot["url"], "created_at": toot["created_at"].isoformat()}
        except Exception as e:
            logger.error(f"Failed to post to Mastodon: {e}")
            raise


class BlueskyProvider(SocialMediaProvider):
    """Bluesky posting provider."""

    def __init__(self):
        safe_conf = SafeConfig(conf)
        self.safe_conf = safe_conf
        self.handle = self.safe_conf.get("bluesky.handle")
        self.app_password = self.safe_conf.get("bluesky.app_password")

    def validate_config(self) -> bool:
        """Validate Bluesky configuration."""
        if not self.handle or not self.app_password:
            logger.error("Bluesky handle and app_password required")
            return False
        return True

    def post(self, text: str, image_path: Path | None = None) -> dict[str, Any]:
        """Post to Bluesky."""
        if not self.validate_config():
            raise ValueError("Bluesky configuration invalid")

        try:
            from atproto import Client
        except ImportError:
            raise ImportError("Please install atproto: pip install atproto")

        # Create client and login
        client = Client()
        client.login(self.handle, self.app_password)

        try:
            # Post to Bluesky
            if image_path and image_path.exists():
                # Upload image first
                with open(image_path, "rb") as f:
                    img_data = f.read()
                upload = client.upload_blob(img_data)

                # Create post with image
                post = client.send_post(
                    text=text,
                    embed={
                        "$type": "app.bsky.embed.images",
                        "images": [{"alt": "Conference talk image", "image": upload.blob}],
                    },
                )
            else:
                # Text-only post
                post = client.send_post(text=text)

            return {"uri": post.uri, "cid": post.cid, "created_at": post.created_at}
        except Exception as e:
            logger.error(f"Failed to post to Bluesky: {e}")
            raise


# Factory function to get the appropriate provider
def get_social_media_provider() -> SocialMediaProvider:
    """Get the configured social media provider."""
    safe_conf = SafeConfig(conf)
    service = safe_conf.get("social_media_service", "linkedin").lower()

    providers = {
        "twitter": TwitterProvider,
        "x": TwitterProvider,  # Alias
        "mastodon": MastodonProvider,
        "bluesky": BlueskyProvider,
    }

    if service not in providers:
        raise ValueError(f"Unknown social media service: {service}. Options: {list(providers.keys())}")

    try:
        provider = providers[service]()
        if not provider.validate_config():
            raise ValueError(f"{service} configuration is incomplete")
        return provider
    except Exception as e:
        logger.error(f"Failed to initialize {service} provider: {e}")
        raise


def post_to_social_media(text: str, image_path: Path | str | None = None) -> dict[str, Any]:
    """Post content to the configured social media platform."""
    provider = get_social_media_provider()

    # Convert string path to Path object
    if isinstance(image_path, str):
        image_path = Path(image_path)

    safe_conf = SafeConfig(conf)
    logger.info(f"Posting to {safe_conf.get('social_media_service', 'linkedin')}")

    try:
        result = provider.post(text, image_path)
        logger.info(f"Successfully posted to social media: {result}")
        return result
    except Exception as e:
        logger.error(f"Failed to post to social media: {e}")
        raise
