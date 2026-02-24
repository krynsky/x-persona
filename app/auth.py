"""
Admin authentication system.
Single admin account with bcrypt password hashing and signed session cookies.
"""
import os
import bcrypt
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from fastapi import Request, HTTPException
from fastapi.responses import RedirectResponse

SECRET_KEY = os.getenv("SECRET_KEY", "change-me-to-a-random-secret-string")
SESSION_MAX_AGE = 86400 * 7  # 7 days

serializer = URLSafeTimedSerializer(SECRET_KEY)


def verify_password(plain: str, hashed: str) -> bool:
    """Check a plaintext password against a bcrypt hash."""
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def hash_password(plain: str) -> str:
    """Generate a bcrypt hash for a plaintext password."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def create_session_token(username: str) -> str:
    """Create a signed session token."""
    return serializer.dumps({"user": username})


def verify_session_token(token: str) -> dict | None:
    """Verify and decode a session token. Returns payload or None."""
    try:
        return serializer.loads(token, max_age=SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None


def get_admin_credentials() -> tuple[str, str]:
    """Get admin username and password hash from environment."""
    username = os.getenv("ADMIN_USERNAME", "admin")
    password_hash = os.getenv("ADMIN_PASSWORD_HASH", "")
    return username, password_hash


async def require_admin(request: Request):
    """FastAPI dependency that enforces admin authentication."""
    token = request.cookies.get("session")
    if not token:
        raise HTTPException(status_code=303, headers={"Location": "/admin/login"})
    payload = verify_session_token(token)
    if not payload:
        raise HTTPException(status_code=303, headers={"Location": "/admin/login"})
    return payload


def admin_login_required(request: Request) -> bool:
    """Check if the current request has a valid admin session (non-raising)."""
    token = request.cookies.get("session")
    if not token:
        return False
    payload = verify_session_token(token)
    return payload is not None
