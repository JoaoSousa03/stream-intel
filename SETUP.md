# Stream Intelligence — Setup Guide

## What's new in this version

- **SQLite database** (`stream_intel.db`) replaces loose JSON files
- **User authentication** — username + password, server-side session tokens
- **Per-user library** — favourites, watch status, and notes stored in the DB
- **Poster cache** — TMDb results cached server-side, no re-fetching on every load
- **Scrape run log** — every scrape recorded with timestamp, mode, region, title count
- **Notes field** — write personal notes on any title from the modal

---

## Directory layout

```
your-folder/
├── app.py                  ← Flask backend (run this)
├── streaming_scraper.py    ← Scraper (called by app.py, or run directly)
├── stream_intel.db         ← SQLite database (auto-created on first run)
├── ui/
│   └── index.html          ← Frontend (served by Flask)
└── output/                 ← Legacy JSON files (can be imported into DB)
```

**Important:** copy `index.html` into a `ui/` subfolder next to `app.py`.

```bash
mkdir ui
mv index.html ui/
```

---

## Install

```bash
pip install flask werkzeug requests fake-useragent tqdm
```

That's it. No extra database server needed — SQLite is built into Python.

---

## First run

```bash
python app.py
```

On the very first run, you'll be prompted to create your admin account:

```
============================================================
  FIRST RUN — Create your admin account
============================================================
  Username: alice
  Password: ••••••••

  Account 'alice' created.

  Dashboard → http://localhost:5000
  Database  → /your/path/stream_intel.db
============================================================
```

Open `http://localhost:5000`, sign in, and you're ready.

---

## Adding more users

Once you're signed in as admin, POST to the register endpoint:

```bash
curl -X POST http://localhost:5000/api/auth/register \
  -H "Content-Type: application/json" \
  -b "si_token=YOUR_TOKEN" \
  -d '{"username": "bob", "password": "password123"}'
```

Or open the browser console on the dashboard and run:

```javascript
fetch('/api/auth/register', {
  method: 'POST',
  headers: {'Content-Type':'application/json'},
  credentials: 'same-origin',
  body: JSON.stringify({username:'bob', password:'password123'})
}).then(r=>r.json()).then(console.log)
```

---

## Migrating existing data

If you have old JSON scrape files in an `output/` folder, click **"⬆ Import old JSON files"** in the sidebar. This is a one-time migration that imports everything into the database. Safe to run multiple times — duplicates are ignored.

---

## Running the scraper

**From the UI:** Select mode and regions in the sidebar, click **Run Scraper**. Progress streams live to the log panel.

**From the command line:**

```bash
# Trending titles for US only
python streaming_scraper.py --mode trending --regions US

# Full catalog for multiple regions
python streaming_scraper.py --mode catalog --regions US GB PT DE FR

# Everything, all regions (slow — ~30 regions × 26 queries each)
python streaming_scraper.py --mode all
```

---

## API reference

All endpoints (except auth) require authentication via cookie (`si_token`) or `Authorization: Bearer <token>` header.

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/auth/register` | Create account (open if no users exist) |
| `POST` | `/api/auth/login` | Sign in, returns `si_token` cookie |
| `POST` | `/api/auth/logout` | Revoke current session |
| `GET`  | `/api/auth/me` | Current user info + library stats |
| `POST` | `/api/auth/change-password` | Change password |
| `GET`  | `/api/titles` | Query titles (params: `platform`, `region`, `type`, `trending`, `search`, `sort`, `limit`, `offset`) |
| `GET`  | `/api/titles/stats` | Dashboard counts |
| `GET`  | `/api/library` | Your favourites + watch list |
| `POST` | `/api/library` | Save fav/status/notes for a title |
| `GET`  | `/api/posters/cache` | Bulk-fetch cached TMDb poster URLs |
| `POST` | `/api/posters/cache` | Save new poster URLs to cache |
| `GET`  | `/api/runs` | Scrape run history |
| `GET`  | `/api/run/<mode>/<regions>` | Start a scrape (SSE stream) |
| `POST` | `/api/import-json` | Import legacy JSON files from `output/` |

---

## Database tables

| Table | Stores |
|-------|--------|
| `users` | Usernames and bcrypt password hashes |
| `tokens` | Session tokens with expiry (30 days) and revocation |
| `titles` | All scraped content — deduplicated by platform + region + title |
| `scrape_runs` | Log of every scrape with status and title count |
| `library` | Per-user favourites, watch status, and notes |
| `poster_cache` | TMDb poster/backdrop URLs so they're never fetched twice |

---

## Security notes

- Passwords are hashed with **bcrypt** via Werkzeug — never stored in plain text
- Session tokens are **32-byte cryptographically random** strings
- Tokens are stored server-side and can be individually revoked (e.g. on logout or password change)
- Registration is **closed** once any user exists — only authenticated users can add new accounts
- The `SECRET_KEY` environment variable controls token signing. Set it in production:
  ```bash
  SECRET_KEY=your-long-random-secret python app.py
  ```

---

## Backing up

Just copy `stream_intel.db`. That single file contains your entire database — all titles, user accounts, library data, and poster cache.

```bash
cp stream_intel.db stream_intel.backup.db
```
