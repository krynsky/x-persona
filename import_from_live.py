"""
Import personas from a live X Persona site into a local SQLite snapshot DB.

Usage:
    python import_from_live.py https://xpersona.krynsky.com [out.db]

Scrapes /personas and each /@username page (public data only) and writes the
rows into out.db (default data/live_snapshot.db), using the same schema as the
app's DB. Then build the static site from it:

    python build_static.py data/live_snapshot.db
"""
import html
import json
import re
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

from app.word_cloud import extract_word_scores

BASE_DIR = Path(__file__).resolve().parent
SCHEMA = """
CREATE TABLE profile_requests (
    id VARCHAR(36) NOT NULL PRIMARY KEY, username VARCHAR(50) NOT NULL UNIQUE, created_at DATETIME);
CREATE TABLE profiles (
    id VARCHAR(36) NOT NULL PRIMARY KEY, username VARCHAR(50) NOT NULL UNIQUE,
    display_name VARCHAR(100), profile_image_url VARCHAR(500), bio VARCHAR(500),
    membership_count INTEGER, memberships JSON NOT NULL, word_scores JSON NOT NULL,
    created_at DATETIME, updated_at DATETIME);
"""


def txt(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", s)).strip()


def parse_profile(page: str) -> dict:
    avatar = re.search(r'<img src="([^"]+)" alt="@[^"]+" class="profile-avatar"', page)
    bio = re.search(r'<p class="profile-bio">(.*?)</p>', page, re.S)
    count = int(re.search(r'class="stat-number">(\d+)<', page).group(1))
    words = {
        html.unescape(w): int(s)
        for w, s in re.findall(r'class="cloud-word" data-word="([^"]*)" data-score="(\d+)"', page)
    }
    rows = re.findall(
        r'<tr class="membership-row">\s*<td[^>]*>\d+</td>\s*<td class="bold">(.*?)</td>\s*'
        r'<td class="dim">@(.*?)</td>\s*<td><a href="https://x\.com/i/lists/(\d+)"',
        page, re.S,
    )
    return {
        "profile_image_url": html.unescape(avatar.group(1)) if avatar else None,
        "bio": txt(bio.group(1)) if bio else None,
        "membership_count": count,
        "word_scores": words,
        "memberships": [{"name": txt(n), "owner": txt(o), "id": i} for n, o, i in rows],
    }


def main():
    base = sys.argv[1].rstrip("/")
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else BASE_DIR / "data" / "live_snapshot.db"
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()

    client = httpx.Client(timeout=30, follow_redirects=True)
    index = client.get(f"{base}/personas").text
    # card date per user, e.g. "February 24, 2026 at 12:30 AM UTC"
    cards = re.findall(
        r'href="/@([^"]+)" class="profile-card".*?class="profile-card-date">([^<]+)<', index, re.S)
    print(f"Found {len(cards)} personas on {base}")

    conn = sqlite3.connect(out)
    conn.executescript(SCHEMA)
    problems = 0
    for username, date_str in cards:
        p = parse_profile(client.get(f"{base}/@{username}").text)
        updated = datetime.strptime(date_str.strip(), "%B %d, %Y at %I:%M %p UTC")
        if len(p["memberships"]) != p["membership_count"]:
            print(f"  [WARN] @{username}: parsed {len(p['memberships'])} memberships, page says {p['membership_count']}")
            problems += 1
        if p["word_scores"] != extract_word_scores(p["memberships"]):
            print(f"  [WARN] @{username}: word scores differ from recomputed scores")
            problems += 1
        conn.execute(
            "INSERT INTO profiles (id, username, profile_image_url, bio, membership_count, memberships,"
            " word_scores, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (username, username, p["profile_image_url"], p["bio"], p["membership_count"],
             json.dumps(p["memberships"]), json.dumps(p["word_scores"]), updated, updated),
        )
        print(f"  [OK] @{username}: {p['membership_count']} lists, {len(p['word_scores'])} words")
        time.sleep(0.3)
    conn.commit()
    conn.close()
    print(f"[DONE] Wrote {len(cards)} personas to {out} ({problems} warnings)")


if __name__ == "__main__":
    main()
