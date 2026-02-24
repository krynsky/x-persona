# X Persona

> ✦ **v1.0.0** — Community-curated persona analysis for X/Twitter accounts

A public-facing web application that analyzes any X account's community perception by examining their list memberships. Enter a username to generate an interactive word cloud showing how the X community categorizes that account.

## ✨ Features

- **☁️ Interactive Word Cloud**: Visual, colorized word cloud built from list membership names
- **🔍 Drill-down**: Click any word to see the exact lists that contributed to it
- **👤 Profile Pages**: Avatar, bio, membership count, and full list table per account
- **📋 List Filter**: Search/filter the full membership table on each profile page
- **📊 Personas Directory**: Browse all analyzed accounts with avatar and bio preview
- **📬 Public Requests**: Visitors can request an account — admin analyzes on demand
- **🔐 Admin Dashboard**: Analyze profiles, manage the request queue, refresh cached data, upload twikit cookies
- **💾 Smart Caching**: Configurable TTL (default 7 days) — repeat lookups skip the API entirely
- **⚡ Dual API Support**: Twikit (cookie-based, free) for local dev; Official X API v2 (pay-as-you-go) for production
- **🛡️ Rate Limiting**: Configurable per-hour limits on public requests
- **🎨 Dark UI**: Clean dark design with Inter font

## 🚀 Quick Start

### 1. Clone & Setup

```bash
git clone https://github.com/krynsky/x-persona.git
cd x-persona
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
```

Edit `.env` with your settings:
- Set `SECRET_KEY` to a long random string
- Set `ADMIN_PASSWORD_HASH` (generate with the command below)
- Set `ENVIRONMENT=development` for local dev (enables hot-reload)

```bash
python -c "import bcrypt; print(bcrypt.hashpw(b'yourpassword', bcrypt.gensalt()).decode())"
```

### 3. Run

```bash
python -m app.main
```

Open **http://localhost:8000** in your browser.

## 🔑 API Provider Modes

| Mode | Setting | Auth | Use Case |
|------|---------|------|----------|
| **Twikit** | `X_API_PROVIDER=twikit` | Browser cookies (`browser_session/cookies.json`) | Local dev, free |
| **Official** | `X_API_PROVIDER=official` | Bearer Token | Production, pay-as-you-go (~$0.008/request) |

> ⚠️ **Note:** The official X API can be expensive for accounts with many list memberships. @elonmusk (553 lists) cost ~$4. Twikit is recommended for personal/dev use.

## 👤 Admin Access

The admin dashboard (`/admin`) lets you:
- Analyze new profiles via twikit
- Review and action public requests
- Refresh existing cached profiles
- Upload a fresh `cookies.json` when your X session expires
- Configure the X API provider and Bearer Token

## 🚢 Deployment (Railway)

1. Push this repo to GitHub
2. Create a new project on [railway.app](https://railway.app) from the GitHub repo
3. Add a **persistent volume** mounted at `/app/data` (keeps the SQLite database across deploys)
4. Set the following environment variables in Railway:

```
ENVIRONMENT=production
APP_NAME=X Persona
SECRET_KEY=<random string>
ADMIN_USERNAME=<your username>
ADMIN_PASSWORD_HASH=<bcrypt hash>
X_API_PROVIDER=twikit
DATABASE_URL=sqlite+aiosqlite:////app/data/xpersona.db
TWIKIT_COOKIES_PATH=/app/data/cookies.json
CACHE_TTL_DAYS=7
RATE_LIMIT_PER_HOUR=10
```

5. Deploy — Railway auto-detects Python via `nixpacks`
6. Upload your `cookies.json` via the Admin Dashboard → Twikit Cookies section

## 📁 Project Structure

```
x-persona/
├── app/
│   ├── main.py              # FastAPI routes & startup
│   ├── database.py          # Async SQLAlchemy engine
│   ├── models.py            # Profile & ProfileRequest models
│   ├── auth.py              # Admin authentication
│   ├── word_cloud.py        # Word extraction & scoring
│   └── api/
│       ├── provider.py      # Abstract base & factory
│       ├── x_api_v2.py      # Official X API v2 client
│       └── twikit_client.py # Twikit cookie-based client
├── templates/               # Jinja2 HTML templates
│   ├── admin/               # Admin login & dashboard
│   ├── base.html            # Shared layout & nav
│   ├── index.html           # Home page
│   ├── profile.html         # Individual persona page
│   ├── profiles.html        # Personas directory
│   └── methodology.html     # How it works
├── static/
│   ├── css/style.css        # All styles
│   └── js/cloud.js          # Word cloud colorization & drill-down
├── .env.example             # Configuration template
├── Procfile                 # Railway/Render start command
├── railway.toml             # Railway build config
└── requirements.txt         # Python dependencies
```

## 🛡️ Security

- Admin password stored as a **bcrypt hash** (never plaintext)
- Session cookies are **signed** with `itsdangerous`
- All secrets loaded from environment variables — never hardcoded
- `.env`, database, and cookies files are excluded from the repo via `.gitignore`
- Public users can only request profiles — analysis is admin-only

---

**Made with ❤️ by krynsky**
