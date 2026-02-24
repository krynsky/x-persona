"""
Official X API v2 client using Bearer Token authentication.
Used in production to fetch user data and list memberships.
"""
import os
import httpx
from app.api.provider import XAPIProvider

BASE_URL = "https://api.x.com/2"


class OfficialAPIProvider(XAPIProvider):
    """Production provider using X API v2 Bearer Token."""

    def __init__(self):
        self.bearer_token = os.getenv("X_API_BEARER_TOKEN", "")
        if not self.bearer_token:
            raise ValueError("X_API_BEARER_TOKEN environment variable is required for official API provider.")
        self.headers = {
            "Authorization": f"Bearer {self.bearer_token}",
            "Content-Type": "application/json",
        }

    async def get_user_info(self, username: str) -> dict | None:
        """Resolve username to user info dict via X API v2."""
        url = f"{BASE_URL}/users/by/username/{username}"
        params = {"user.fields": "id,name,username,profile_image_url,description"}
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                resp = await client.get(url, headers=self.headers, params=params)
                resp.raise_for_status()
                data = resp.json()
                user_data = data.get("data", {})
                image_url = user_data.get("profile_image_url")
                if image_url:
                    image_url = image_url.replace('_normal.', '_400x400.')
                return {
                    'id': user_data.get("id"),
                    'display_name': user_data.get("name"),
                    'profile_image_url': image_url,
                    'bio': user_data.get("description"),
                }
            except httpx.HTTPStatusError as e:
                print(f"[ERR] X API error resolving @{username}: {e.response.status_code} — {e.response.text}")
                return None
            except Exception as e:
                print(f"[ERR] Error resolving @{username}: {e}")
                return None

    async def get_memberships(self, user_id: str, username: str) -> list[dict]:
        """Fetch all list memberships for a user via X API v2."""
        url = f"{BASE_URL}/users/{user_id}/list_memberships"
        params = {
            "list.fields": "id,name,owner_id",
            "expansions": "owner_id",
            "user.fields": "username",
            "max_results": 100,
        }
        all_memberships = []
        pagination_token = None

        async with httpx.AsyncClient(timeout=20.0) as client:
            while True:
                if pagination_token:
                    params["pagination_token"] = pagination_token

                try:
                    resp = await client.get(url, headers=self.headers, params=params)
                    resp.raise_for_status()
                    data = resp.json()
                except httpx.HTTPStatusError as e:
                    print(f"[ERR] X API error fetching memberships for {username}: {e.response.status_code}")
                    break
                except Exception as e:
                    print(f"[ERR] Error fetching memberships for {username}: {e}")
                    break

                # Build owner lookup from includes
                owner_map = {}
                for user in data.get("includes", {}).get("users", []):
                    owner_map[user["id"]] = user.get("username", "Unknown")

                # Parse list data
                for lst in data.get("data", []):
                    name = lst.get("name", "")
                    if name:
                        owner_id = lst.get("owner_id", "")
                        all_memberships.append({
                            "name": name,
                            "owner": owner_map.get(owner_id, "Unknown"),
                            "id": lst.get("id", ""),
                        })

                # Pagination
                meta = data.get("meta", {})
                pagination_token = meta.get("next_token")
                if not pagination_token or len(all_memberships) > 500:
                    break

        print(f"[OK] Found {len(all_memberships)} memberships for @{username} via X API v2")
        return all_memberships
