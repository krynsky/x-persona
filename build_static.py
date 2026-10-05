"""
Build the read-only static showcase site into ./site from the local SQLite DB.

Usage:
    python build_static.py [path/to/xpersona.db]

Run the full app locally (admin dashboard) to analyze accounts, then run this
script and commit/push ./site. Vercel serves ./site as-is.
"""
import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.word_cloud import group_lists_by_word

BASE_DIR = Path(__file__).resolve().parent
OUT_DIR = BASE_DIR / "site"
DEFAULT_DB = BASE_DIR / "data" / "xpersona.db"

APP_NAME = os.getenv("APP_NAME", "X Persona")
SITE_URL = os.getenv("SITE_URL", "https://xpersona.krynsky.com").rstrip("/")
GITHUB_URL = "https://github.com/krynsky/x-persona"


class StaticUrl:
    def __init__(self, path: str):
        self.path = path

    def __str__(self):
        return SITE_URL + self.path


class StaticRequest:
    """Minimal stand-in for the request object the templates expect."""
    def __init__(self, path: str):
        self.url = StaticUrl(path)
        self.base_url = SITE_URL + "/"


def parse_dt(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def format_datetime(dt: datetime) -> str:
    return dt.strftime("%B %d, %Y at %I:%M %p UTC")


def format_date_short(dt: datetime) -> str:
    return f"{dt.month}/{dt.day}/{str(dt.year)[2:]}"


def load_profiles(db_path: Path) -> list[SimpleNamespace]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM profiles ORDER BY updated_at DESC").fetchall()
    conn.close()
    return [
        SimpleNamespace(
            username=r["username"],
            display_name=r["display_name"],
            profile_image_url=r["profile_image_url"],
            bio=r["bio"],
            membership_count=r["membership_count"],
            memberships=json.loads(r["memberships"]),
            word_scores=json.loads(r["word_scores"]),
            updated_at=parse_dt(r["updated_at"]),
        )
        for r in rows
    ]


def main():
    db_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DB
    profiles = load_profiles(db_path)

    env = Environment(
        loader=FileSystemLoader(BASE_DIR / "templates"),
        autoescape=select_autoescape(["html"]),
    )
    env.filters["format_datetime"] = format_datetime
    env.filters["format_date_short"] = format_date_short
    env.globals["is_admin"] = lambda request: False
    env.globals["static_site"] = True
    env.globals["github_url"] = GITHUB_URL

    def render(template: str, path: str, **ctx) -> str:
        request = StaticRequest(path)
        return env.get_template(template).render(
            request=request, app_name=APP_NAME, **ctx
        )

    OUT_DIR.mkdir(exist_ok=True)
    for child in OUT_DIR.iterdir():
        if child.name == ".vercel":  # keep the Vercel project link
            continue
        shutil.rmtree(child) if child.is_dir() else child.unlink()
    shutil.copytree(BASE_DIR / "static", OUT_DIR / "static")

    def write(rel: str, content: str):
        (OUT_DIR / rel).write_text(content, encoding="utf-8")

    write("index.html", render("index.html", "/", recent_profiles=profiles[:12]))
    write("personas.html", render("profiles.html", "/personas", profiles=profiles))
    write("methodology.html", render("methodology.html", "/methodology"))
    write("about.html", render("about.html", "/about"))
    write("404.html", render("profile.html", "/404", profile=None,
                             error="That page doesn't exist. Browse the personas instead."))

    (OUT_DIR / "data").mkdir()
    for p in profiles:
        write(f"@{p.username}.html", render("profile.html", f"/@{p.username}", profile=p))
        word_lists = {
            w: group_lists_by_word(w, p.memberships) for w in p.word_scores
        }
        write(f"data/{p.username}.json", json.dumps(word_lists, separators=(",", ":")))

    write("vercel.json", json.dumps({
        "cleanUrls": True,
        # Explicit root rewrite: with cleanUrls alone, "/" 404s on Vercel here.
        "rewrites": [{"source": "/", "destination": "/index"}],
        "redirects": [
            {"source": "/profiles", "destination": "/personas", "permanent": True},
            {"source": "/admin/:path*", "destination": "/", "permanent": False},
        ],
    }, indent=2))

    print(f"[OK] Built {len(profiles)} personas into {OUT_DIR}")


if __name__ == "__main__":
    main()
