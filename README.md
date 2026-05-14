# Facebook Groups Apartment Scraper

A personal, read-only monitor for apartment listings in Facebook groups you have legitimately joined.

## Important

- This is a **personal tool** — it reads only groups you are a member of.
- **Requires manual Facebook login** — no automated credential entry, CAPTCHA bypass, or 2FA bypass.
- Does **not** bypass any Facebook security mechanism.
- Low-frequency polling: high-priority groups every 15–30 min, medium every 60 min.
- Stores only apartment-relevant data. Does not collect private profile data, group member lists, or reactions.

---

## Setup

### 1. Install dependencies

```bash
pip install -e .
playwright install chromium
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env — set DATABASE_URL, Telegram tokens, etc.
```

### 3. Configure groups

Edit `config/groups.yaml` — replace `PUT_GROUP_ID_HERE` with real group URLs you have access to.

### 4. Start Postgres

```bash
docker-compose up postgres -d
```

---

## Login (required once)

```bash
python scripts/init_login.py
```

A Chrome window opens. Log in to Facebook manually. Press Enter in the terminal when you are on the feed. The session is saved and reused on every run.

---

## Run a single scrape

```bash
python scripts/run_once.py
```

Scrapes all enabled groups once, stores results in Postgres, and sends Telegram alerts for high-scoring listings.

---

## Debug extraction failure

```bash
python scripts/debug_group.py --group-id hod_hasharon_rentals
```

Outputs to `runtime/debug/hod_hasharon_rentals/`:
- `screenshot.png` — page state
- `page.html` — raw HTML
- `posts.json` — extracted posts summary

---

## Scheduled mode

```bash
python -m app.main
```

Runs indefinitely on a schedule derived from each group's `priority`.

---

## Add a group

In `config/groups.yaml`, add:

```yaml
- id: my_group_id
  name: "Group display name"
  url: "https://www.facebook.com/groups/GROUP_ID_OR_SLUG"
  enabled: true
  priority: medium
  max_posts_per_run: 20
  scrape_comments: true
  max_comments_per_post: 10
  scrape_images: true
```

---

## Telegram setup

1. Create a Telegram bot via @BotFather and get the token.
2. Get your chat ID (send a message to the bot, then call `getUpdates`).
3. Set in `.env`:

```
TELEGRAM_BOT_TOKEN=your_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
```

Alerts include score, location, price, rooms, and a direct post link. Inline buttons let you mark listings as relevant, rejected, contacted, duplicate, too expensive, or bad location.

---

## Adjust apartment criteria

Edit `config/criteria.yaml` to change preferred cities, neighborhoods, price ceiling, and minimum rooms.

---

## Run tests

```bash
pytest tests/
```

---

## Architecture

```
config.yaml
  ↓
scheduler (APScheduler)
  ↓
Playwright Facebook reader (persistent logged-in session)
  ↓
raw HTML/screenshot snapshot on failure
  ↓
post extractor
  ↓
image extractor
  ↓
comment extractor (only for likely listings)
  ↓
dedupe + Postgres persistence
  ↓
apartment relevance classifier (Hebrew rules)
  ↓
Telegram notifier
```
  screen -S scraper
  uv run python app/main.py

  Press Ctrl+A then D to detach. The process keeps running in the background, and
  you can safely close the SSH window. The VM and everything else on it is
  untouched.

  To come back later:
  screen -r scraper        # reattach to see logs
  screen -ls               # list all running screens

  To stop it when needed:
  screen -r scraper        # reattach first
  # then Ctrl+C