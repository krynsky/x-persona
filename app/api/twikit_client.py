"""
Twikit-based X API client for local development and testing.
Uses browser cookies for authentication — NOT suitable for production.
"""
import os
from pathlib import Path
from app.api import twikit_patch  # noqa: F401 — monkey-patches twikit
from twikit import Client
from app.api.provider import XAPIProvider


BASE_DIR = Path(__file__).resolve().parent.parent.parent


class TwikitProvider(XAPIProvider):
    """Dev/test provider using twikit with cookie-based auth."""

    def __init__(self):
        self.client = Client('en-US')
        self.cookies_path = Path(os.getenv("COOKIES_PATH", os.getenv("TWIKIT_COOKIES_PATH", str(BASE_DIR / "browser_session" / "cookies.json"))))
        self._logged_in = False

    async def _ensure_login(self):
        """Load cookies if not already loaded."""
        if not self._logged_in:
            if not self.cookies_path.exists():
                raise FileNotFoundError(
                    f"Twikit cookies not found at {self.cookies_path}. "
                    "Copy your cookies.json from x-list-summarizer/browser_session/ "
                    "or switch to X_API_PROVIDER=official."
                )
            self.client.load_cookies(str(self.cookies_path))
            self._logged_in = True

    async def get_user_info(self, username: str) -> dict | None:
        """Resolve username to user info dict via twikit."""
        try:
            await self._ensure_login()
            user = await self.client.get_user_by_screen_name(username)
            # Upgrade thumbnail URL to full-size by removing _normal suffix
            image_url = getattr(user, 'profile_image_url', None) or getattr(user, 'profile_image_url_https', None)
            if image_url:
                image_url = image_url.replace('_normal.', '_400x400.')
            return {
                'id': user.id,
                'display_name': getattr(user, 'name', None),
                'profile_image_url': image_url,
                'bio': getattr(user, 'description', None),
            }
        except Exception as e:
            print(f"[ERR] Twikit error resolving @{username}: {e}")
            return None

    async def get_memberships(self, user_id: str, username: str) -> list[dict]:
        """Fetch list memberships via twikit's v1.1 API call."""
        try:
            await self._ensure_login()
            memberships = []
            cursor = '-1'

            while True:
                url = f'https://api.twitter.com/1.1/lists/memberships.json?user_id={user_id}&count=50'
                if cursor and cursor != '-1':
                    url += f'&cursor={cursor}'

                response, _ = await self.client.get(url, headers=self.client._base_headers)

                if not response or 'lists' not in response:
                    break

                for lst in response['lists']:
                    name = lst.get('name', '')
                    if name:
                        owner = lst.get('user', {}).get('screen_name', 'Unknown')
                        list_id = lst.get('id_str', '')
                        memberships.append({
                            'name': name,
                            'owner': owner,
                            'id': list_id,
                        })

                cursor = str(response.get('next_cursor_str', '0'))
                if cursor == '0' or not cursor or len(memberships) > 500:
                    break

            print(f"[OK] Found {len(memberships)} memberships for @{username} via twikit")
            return memberships
        except Exception as e:
            print(f"[ERR] Twikit error fetching memberships for @{username}: {e}")
            return []
