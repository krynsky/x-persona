"""
Abstract base for X API providers and factory to select the active one.
"""
from abc import ABC, abstractmethod
import os


class XAPIProvider(ABC):
    """Interface for fetching X user data."""

    @abstractmethod
    async def get_user_info(self, username: str) -> dict | None:
        """Resolve an X username to a dict with id, display_name, profile_image_url."""
        ...

    @abstractmethod
    async def get_memberships(self, user_id: str, username: str) -> list[dict]:
        """Fetch all list memberships for a user. Returns [{name, owner, id}, ...]."""
        ...


def get_provider() -> XAPIProvider:
    """Factory: returns the configured API provider based on X_API_PROVIDER env var."""
    provider = os.getenv("X_API_PROVIDER", "twikit").lower()
    if provider == "official":
        from app.api.x_api_v2 import OfficialAPIProvider
        return OfficialAPIProvider()
    else:
        from app.api.twikit_client import TwikitProvider
        return TwikitProvider()
