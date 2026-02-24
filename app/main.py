"""
X Persona — Main FastAPI application.
Public-facing web app for analyzing X account personas via list memberships.
"""
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from fastapi import FastAPI, Request, Form, Depends, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from sqlalchemy import select

from app.database import init_db, get_db, async_session
from app.models import Profile, ProfileRequest
from app.api.provider import get_provider
from app.word_cloud import extract_word_scores, group_lists_by_word
from app.auth import (
    verify_password, create_session_token, get_admin_credentials,
    admin_login_required, verify_session_token
)

# ── App Configuration ─────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
APP_NAME = os.getenv("APP_NAME", "X Persona")
RATE_LIMIT = os.getenv("RATE_LIMIT_PER_HOUR", "10")


# ── Lifecycle ─────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    print(f"[OK] {APP_NAME} database initialized")
    yield


# ── App Init ──────────────────────────────────
app = FastAPI(title=APP_NAME, lifespan=lifespan)

# Rate limiting
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return HTMLResponse(
        content="<h1>Rate Limit Exceeded</h1><p>Too many analysis requests. Cached lookups are unlimited — try again later.</p>",
        status_code=429,
    )

# Static files & templates
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


# ── Template Helpers ──────────────────────────
def format_datetime(dt: datetime) -> str:
    """Format datetime for display."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime("%B %d, %Y at %I:%M %p UTC")

def format_date_short(dt: datetime) -> str:
    """Format datetime as short date, e.g. 2/24/26."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return f"{dt.month}/{dt.day}/{str(dt.year)[2:]}"

templates.env.filters["format_datetime"] = format_datetime
templates.env.filters["format_date_short"] = format_date_short


def is_admin(request: Request) -> bool:
    """Check if the current request has a valid admin session."""
    return admin_login_required(request)

templates.env.globals["is_admin"] = is_admin


# ══════════════════════════════════════════════
#  PUBLIC ROUTES
# ══════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Landing page with search bar and recent profiles."""
    async with async_session() as db:
        result = await db.execute(
            select(Profile)
            .order_by(Profile.updated_at.desc())
            .limit(12)
        )
        recent = result.scalars().all()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "recent_profiles": recent,
        "app_name": APP_NAME,
    })


@app.post("/request")
@limiter.limit(f"{RATE_LIMIT}/hour")
async def request_profile(request: Request, username: str = Form(...)):
    """Public: submit a username request. Queues into profile_requests for admin to action."""
    clean = username.strip().lstrip("@").lower()
    if not clean:
        return RedirectResponse("/", status_code=303)

    async with async_session() as db:
        # Check if a complete profile already exists
        result = await db.execute(select(Profile).where(Profile.username == clean))
        existing_profile = result.scalar_one_or_none()

        if existing_profile and not existing_profile.is_stale:
            return templates.TemplateResponse("index.html", {
                "request": request,
                "info": f"Persona already created for @{clean}.",
                "profile_link": f"/@{clean}",
                "profile_link_label": f"View @{clean}'s Persona",
                "recent_profiles": [],
                "app_name": APP_NAME,
            })

        # Check if already in the request queue
        result = await db.execute(select(ProfileRequest).where(ProfileRequest.username == clean))
        existing_request = result.scalar_one_or_none()

        if existing_request:
            return templates.TemplateResponse("index.html", {
                "request": request,
                "info": f"@{clean} has already been requested. Check back soon.",
                "recent_profiles": [],
                "app_name": APP_NAME,
            })

        # Add to request queue (no Profile record created)
        db.add(ProfileRequest(username=clean))
        await db.commit()

    return templates.TemplateResponse("index.html", {
        "request": request,
        "info": f"Request submitted for @{clean}. Check back soon!",
        "recent_profiles": [],
        "app_name": APP_NAME,
    })


@app.post("/analyze")
async def analyze(request: Request, username: str = Form(...)):
    """Admin only: analyze a username immediately via API."""
    if not admin_login_required(request):
        return RedirectResponse("/admin/login", status_code=303)

    clean = username.strip().lstrip("@").lower()
    if not clean:
        return RedirectResponse("/admin", status_code=303)

    # Check cache — show link if fresh complete profile already exists
    async with async_session() as db:
        result = await db.execute(select(Profile).where(Profile.username == clean))
        profile = result.scalar_one_or_none()
        if profile and not profile.is_stale:
            return templates.TemplateResponse("index.html", {
                "request": request,
                "info": f"Persona already created for @{clean}.",
                "profile_link": f"/@{clean}",
                "profile_link_label": f"View @{clean}'s Persona",
                "recent_profiles": [],
                "app_name": APP_NAME,
            })

    return await _run_analysis(request, clean)


@app.post("/admin/analyze-profile")
async def admin_analyze_profile(request: Request, username: str = Form(...)):
    """Admin only: run analysis on a requested profile, then remove from request queue."""
    if not admin_login_required(request):
        return RedirectResponse("/admin/login", status_code=303)

    clean = username.strip().lstrip("@").lower()
    response = await _run_analysis(request, clean, redirect_to_admin=True)

    # Remove from request queue on success (redirect means analysis succeeded)
    if hasattr(response, "status_code") and response.status_code == 303:
        async with async_session() as db:
            result = await db.execute(select(ProfileRequest).where(ProfileRequest.username == clean))
            req = result.scalar_one_or_none()
            if req:
                await db.delete(req)
                await db.commit()

    return response


async def _run_analysis(request: Request, clean: str, redirect_to_admin: bool = False):
    """Shared analysis logic used by both admin analyze routes."""
    error_redirect = "/admin" if redirect_to_admin else "/"

    try:
        provider = get_provider()
        user_info = await provider.get_user_info(clean)
        if not user_info or not user_info.get('id'):
            if redirect_to_admin:
                return RedirectResponse(f"/admin?error=Could+not+find+@{clean}", status_code=303)
            return templates.TemplateResponse("index.html", {
                "request": request,
                "error": f"Could not find user @{clean} on X.",
                "recent_profiles": [],
                "app_name": APP_NAME,
            })

        user_id = user_info['id']
        memberships = await provider.get_memberships(user_id, clean)
        word_scores = extract_word_scores(memberships)

        async with async_session() as db:
            result = await db.execute(select(Profile).where(Profile.username == clean))
            profile = result.scalar_one_or_none()

            if profile:
                profile.membership_count = len(memberships)
                profile.memberships = memberships
                profile.word_scores = word_scores
                profile.display_name = user_info.get('display_name')
                profile.profile_image_url = user_info.get('profile_image_url')
                profile.bio = user_info.get('bio')
                profile.updated_at = datetime.now(timezone.utc)
            else:
                profile = Profile(
                    username=clean,
                    display_name=user_info.get('display_name'),
                    profile_image_url=user_info.get('profile_image_url'),
                    bio=user_info.get('bio'),
                    membership_count=len(memberships),
                    memberships=memberships,
                    word_scores=word_scores,
                )
                db.add(profile)

            await db.commit()

    except FileNotFoundError as e:
        if redirect_to_admin:
            return RedirectResponse("/admin?error=Cookies+not+found", status_code=303)
        return templates.TemplateResponse("index.html", {
            "request": request,
            "error": str(e),
            "recent_profiles": [],
            "app_name": APP_NAME,
        })
    except Exception as e:
        if redirect_to_admin:
            return RedirectResponse(f"/admin?error=Analysis+failed", status_code=303)
        return templates.TemplateResponse("index.html", {
            "request": request,
            "error": f"Analysis failed: {e}",
            "recent_profiles": [],
            "app_name": APP_NAME,
        })

    return RedirectResponse(f"/@{clean}", status_code=303)


@app.get("/@{username}", response_class=HTMLResponse)
async def view_profile(request: Request, username: str):
    """View a cached profile analysis (shareable URL)."""
    clean = username.strip().lstrip("@").lower()
    async with async_session() as db:
        result = await db.execute(select(Profile).where(Profile.username == clean))
        profile = result.scalar_one_or_none()

    if not profile:
        return templates.TemplateResponse("profile.html", {
            "request": request,
            "profile": None,
            "error": f"No analysis found for @{clean}. Run one from the home page.",
            "app_name": APP_NAME,
        })

    return templates.TemplateResponse("profile.html", {
        "request": request,
        "profile": profile,
        "app_name": APP_NAME,
    })


@app.get("/profiles", response_class=HTMLResponse)
async def browse_profiles(request: Request):
    """Browse all analyzed profiles."""
    async with async_session() as db:
        result = await db.execute(
            select(Profile).order_by(Profile.updated_at.desc())
        )
        profiles = result.scalars().all()

    return templates.TemplateResponse("profiles.html", {
        "request": request,
        "profiles": profiles,
        "app_name": APP_NAME,
    })


@app.get("/methodology", response_class=HTMLResponse)
async def methodology(request: Request):
    """Methodology page explaining how the persona analysis works."""
    return templates.TemplateResponse("methodology.html", {
        "request": request,
        "app_name": APP_NAME,
    })


@app.get("/about", response_class=HTMLResponse)
async def about(request: Request):
    """About page."""
    return templates.TemplateResponse("about.html", {
        "request": request,
        "app_name": APP_NAME,
    })


# ── API endpoint for word cloud drill-down ────
@app.get("/api/lists-for-word")
async def lists_for_word(username: str, word: str):
    """Return lists whose names contain the given word (for word cloud click)."""
    async with async_session() as db:
        result = await db.execute(select(Profile).where(Profile.username == username.lower()))
        profile = result.scalar_one_or_none()

    if not profile:
        return JSONResponse({"error": "Profile not found"}, status_code=404)

    matching = group_lists_by_word(word, profile.memberships)
    return JSONResponse({"word": word, "lists": matching, "count": len(matching)})


# ══════════════════════════════════════════════
#  ADMIN ROUTES
# ══════════════════════════════════════════════

@app.get("/admin/login", response_class=HTMLResponse)
async def admin_login_page(request: Request):
    """Admin login form."""
    if admin_login_required(request):
        return RedirectResponse("/admin", status_code=303)
    return templates.TemplateResponse("admin/login.html", {
        "request": request,
        "app_name": APP_NAME,
    })


@app.post("/admin/login")
async def admin_login_submit(request: Request, password: str = Form(...)):
    """Process admin login."""
    admin_user, admin_hash = get_admin_credentials()

    if not admin_hash:
        return templates.TemplateResponse("admin/login.html", {
            "request": request,
            "error": "Admin password not configured. Set ADMIN_PASSWORD_HASH in .env.",
            "app_name": APP_NAME,
        })

    if verify_password(password, admin_hash):
        token = create_session_token(admin_user)
        response = RedirectResponse("/admin", status_code=303)
        response.set_cookie("session", token, httponly=True, samesite="lax", max_age=86400 * 7)
        return response

    return templates.TemplateResponse("admin/login.html", {
        "request": request,
        "error": "Invalid password.",
        "app_name": APP_NAME,
    })


@app.get("/admin/logout")
async def admin_logout():
    """Log out admin."""
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie("session")
    return response


@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    """Admin dashboard."""
    if not admin_login_required(request):
        return RedirectResponse("/admin/login", status_code=303)

    async with async_session() as db:
        result = await db.execute(select(Profile).order_by(Profile.updated_at.desc()))
        complete_profiles = result.scalars().all()

        result = await db.execute(select(ProfileRequest).order_by(ProfileRequest.created_at.desc()))
        requested_profiles = result.scalars().all()

    return templates.TemplateResponse("admin/settings.html", {
        "request": request,
        "requested_profiles": requested_profiles,
        "complete_profiles": complete_profiles,
        "total_profiles": len(complete_profiles),
        "pending_requests": len(requested_profiles),
        "provider": os.getenv("X_API_PROVIDER", "twikit"),
        "bearer_token": os.getenv("X_API_BEARER_TOKEN", ""),
        "cache_ttl": os.getenv("CACHE_TTL_DAYS", "7"),
        "rate_limit": RATE_LIMIT,
        "error": request.query_params.get("error"),
        "app_name": APP_NAME,
    })


@app.post("/admin/upload-cookies")
async def admin_upload_cookies(request: Request, cookies_file: UploadFile = File(...)):
    """Upload a fresh cookies.json for twikit (admin only)."""
    if not admin_login_required(request):
        return RedirectResponse("/admin/login", status_code=303)

    if not cookies_file.filename.endswith(".json"):
        return RedirectResponse("/admin?cookies_error=File+must+be+a+.json+file", status_code=303)

    try:
        contents = await cookies_file.read()
        # Validate it's parseable JSON
        import json
        json.loads(contents)

        cookies_path = Path(os.getenv(
            "COOKIES_PATH",
            os.getenv("TWIKIT_COOKIES_PATH", str(BASE_DIR / "browser_session" / "cookies.json"))
        ))
        cookies_path.parent.mkdir(parents=True, exist_ok=True)
        cookies_path.write_bytes(contents)

        return RedirectResponse("/admin?cookies_saved=1", status_code=303)
    except Exception as e:
        return RedirectResponse(f"/admin?cookies_error=Upload+failed:+{str(e)[:80]}", status_code=303)


@app.post("/admin/delete-request")
async def admin_delete_request(request: Request, username: str = Form(...)):
    """Delete a pending request from the queue (admin only)."""
    if not admin_login_required(request):
        return RedirectResponse("/admin/login", status_code=303)

    async with async_session() as db:
        result = await db.execute(select(ProfileRequest).where(ProfileRequest.username == username.lower()))
        req = result.scalar_one_or_none()
        if req:
            await db.delete(req)
            await db.commit()

    return RedirectResponse("/admin", status_code=303)


@app.post("/admin/delete-profile")
async def admin_delete_profile(request: Request, username: str = Form(...)):
    """Delete a cached profile (admin only)."""
    if not admin_login_required(request):
        return RedirectResponse("/admin/login", status_code=303)

    async with async_session() as db:
        result = await db.execute(select(Profile).where(Profile.username == username.lower()))
        profile = result.scalar_one_or_none()
        if profile:
            await db.delete(profile)
            await db.commit()

    return RedirectResponse("/admin", status_code=303)


@app.post("/admin/save-api-config")
async def admin_save_api_config(
    request: Request,
    x_api_provider: str = Form(...),
    x_api_bearer_token: str = Form(""),
):
    """Save X API configuration to .env file (admin only)."""
    if not admin_login_required(request):
        return RedirectResponse("/admin/login", status_code=303)

    # Update env vars in the running process immediately
    os.environ["X_API_PROVIDER"] = x_api_provider
    os.environ["X_API_BEARER_TOKEN"] = x_api_bearer_token

    # Also persist to .env file if it exists (local dev only)
    env_path = BASE_DIR / ".env"
    if env_path.exists():
        import re
        env_content = env_path.read_text(encoding="utf-8")

        def set_env_value(content: str, key: str, value: str) -> str:
            pattern = rf'^{re.escape(key)}=.*$'
            replacement = f'{key}={value}'
            if re.search(pattern, content, flags=re.MULTILINE):
                return re.sub(pattern, replacement, content, flags=re.MULTILINE)
            return content + f'\n{replacement}'

        env_content = set_env_value(env_content, "X_API_PROVIDER", x_api_provider)
        env_content = set_env_value(env_content, "X_API_BEARER_TOKEN", x_api_bearer_token)
        env_path.write_text(env_content, encoding="utf-8")

    return RedirectResponse("/admin?saved=1", status_code=303)


# ── Entry Point ───────────────────────────────
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    dev_mode = os.getenv("ENVIRONMENT", "production") == "development"
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=dev_mode)
