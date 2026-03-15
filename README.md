# Google Alerts Bot

Monitors Google Alert RSS feeds for your clients, analyses new articles with Claude,
and sends a morning email digest via SendGrid when anything interesting is found.

**Clients monitored:** Bapcor · Brisbane Airport · Adore Beauty · Sparesbox · Repco

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in:

| Variable | Where to get it |
|---|---|
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) |
| `SENDGRID_API_KEY` | [app.sendgrid.com → Settings → API Keys](https://app.sendgrid.com/settings/api_keys) |
| `TO_EMAIL` | Your email address |
| `FROM_EMAIL` | A sender address verified in SendGrid |
| `RSS_*` | See step 3 below |

### 3. Set up Google Alerts RSS feeds

For **each client**, do this once:

1. Go to [google.com/alerts](https://www.google.com/alerts)
2. Sign in with a Google account
3. In the search box, type the client name (e.g. `Bapcor`)
4. Click **Show options**
5. Under **Deliver to**, select **RSS feed**
6. Click **Create Alert**
7. On the Alerts page, hover over the RSS icon next to the alert and **copy the URL**
   It will look like: `https://www.google.com/alerts/feeds/123456789/987654321`
8. Paste the URL into the matching `RSS_*` variable in your `.env` file

Repeat for all five clients.

### 4. Test it manually

```bash
python main.py
```

On first run it will:
- Fetch all current articles from each RSS feed
- Ask Claude to analyse them
- Email you if anything interesting is found (or print "nothing noteworthy" otherwise)
- Save a `seen_articles.json` file so future runs only look at genuinely new articles

---

## Scheduling — GitHub Actions (recommended, laptop-free)

GitHub runs the bot on its own servers every morning for free. Your laptop can be off.

### One-time setup

**1. Push this repo to GitHub**
```bash
git init
git add .
git commit -m "Initial commit"
# Create a new repo at github.com, then:
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

**2. Add your secrets to GitHub**

Go to your repo → **Settings → Secrets and variables → Actions → New repository secret**

Add one secret for each of these (same values as your `.env` file):

| Secret name | Value |
|---|---|
| `ANTHROPIC_API_KEY` | Your Anthropic key |
| `SENDGRID_API_KEY` | Your SendGrid key |
| `TO_EMAIL` | Your email address |
| `FROM_EMAIL` | Verified sender address |
| `RSS_BAPCOR` | Google Alerts RSS URL |
| `RSS_BRISBANE_AIRPORT` | Google Alerts RSS URL |
| `RSS_ADORE_BEAUTY` | Google Alerts RSS URL |
| `RSS_SPARESBOX` | Google Alerts RSS URL |
| `RSS_REPCO` | Google Alerts RSS URL |

**3. That's it.** The workflow at `.github/workflows/daily-alerts.yml` runs automatically
at 7:30 AM AEST every day. After each run, GitHub commits the updated `seen_articles.json`
back to the repo so no articles are ever double-processed.

### Trigger a manual run

Go to your repo → **Actions → Daily Client Media Briefing → Run workflow**.

### Adjust the schedule

Edit the `cron` line in `.github/workflows/daily-alerts.yml`.
Times are in UTC — AEST is UTC+10, AEDT (daylight saving) is UTC+11.

| Want | Cron (UTC) |
|---|---|
| 7:30 AM AEST | `30 21 * * *` |
| 7:30 AM AEDT | `30 20 * * *` |
| 8:00 AM AEST | `0 22 * * *` |

---

## Schedule with Windows Task Scheduler (requires laptop to be on)

Only use this if you prefer not to use GitHub Actions.

1. Open **Task Scheduler** (search in Start menu)
2. Click **Create Basic Task…**
3. Name: `Google Alerts Bot`
4. Trigger: **Daily** at your preferred time (e.g. 7:30 AM)
5. Action: **Start a program**
   - Program: path to your Python executable, e.g.
     `C:\Users\YourName\AppData\Local\Programs\Python\Python312\python.exe`
   - Arguments: `main.py`
   - Start in: full path to this folder, e.g.
     `C:\Users\YourName\OneDrive\Documents\Claude Code\Google-Trends-Bot`
6. Finish → the bot will run every morning automatically

---

## How it works

```
RSS Feeds (5 clients)
      │
      ▼
feedparser polls each feed
      │
      ▼
New articles only (seen_articles.json tracks what's been processed)
      │
      ▼
Claude (claude-opus-4-6) analyses the batch
  - Flags: acquisitions, lawsuits, crises, leadership changes, etc.
  - Ignores: routine press releases, minor mentions
      │
      ├── "Action required" → SendGrid email to you
      └── "Nothing noteworthy" → No email, silent exit
```

---

## Files

| File | Purpose |
|---|---|
| `main.py` | Main bot script |
| `.env` | Your secrets — never commit this |
| `.env.example` | Config template — safe to commit |
| `requirements.txt` | Python dependencies |
| `seen_articles.json` | Tracks processed articles (committed so GitHub Actions persists it) |
| `.github/workflows/daily-alerts.yml` | GitHub Actions schedule |
| `.gitignore` | Excludes `.env` from git |

---

## Adding or changing clients

Edit the `CLIENTS` dict at the top of `main.py` and add matching `RSS_*` variables to `.env`.
