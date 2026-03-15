"""
Google Alerts Bot
Fetches RSS feeds for client alerts, analyses them with Claude,
and sends a morning briefing email via SendGrid when interesting news is found.
"""

import os
import json
import textwrap
from datetime import datetime
from pathlib import Path

import feedparser
import anthropic
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CLIENTS: dict[str, str | None] = {
    "Bapcor":           os.getenv("RSS_BAPCOR"),
    "Brisbane Airport": os.getenv("RSS_BRISBANE_AIRPORT"),
    "Adore Beauty":     os.getenv("RSS_ADORE_BEAUTY"),
    "Sparesbox":        os.getenv("RSS_SPARESBOX"),
    "Repco":            os.getenv("RSS_REPCO"),
}

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
SENDGRID_API_KEY  = os.getenv("SENDGRID_API_KEY")
TO_EMAIL          = os.getenv("TO_EMAIL")
FROM_EMAIL        = os.getenv("FROM_EMAIL")

SEEN_ARTICLES_FILE = Path("seen_articles.json")

# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

def load_seen_ids() -> set[str]:
    if SEEN_ARTICLES_FILE.exists():
        with open(SEEN_ARTICLES_FILE) as f:
            return set(json.load(f))
    return set()


def save_seen_ids(seen: set[str]) -> None:
    with open(SEEN_ARTICLES_FILE, "w") as f:
        json.dump(sorted(seen), f, indent=2)

# ---------------------------------------------------------------------------
# RSS fetching
# ---------------------------------------------------------------------------

def fetch_new_articles(seen_ids: set[str]) -> dict[str, list[dict]]:
    """Return only articles not yet seen, grouped by client name."""
    new: dict[str, list[dict]] = {}

    for client, rss_url in CLIENTS.items():
        if not rss_url:
            print(f"  [SKIP] No RSS URL configured for {client}")
            continue

        feed = feedparser.parse(rss_url)

        if feed.bozo:
            print(f"  [WARN] Could not parse feed for {client}: {feed.bozo_exception}")
            continue

        client_new = []
        for entry in feed.entries:
            article_id = entry.get("id") or entry.get("link", "")
            if article_id and article_id not in seen_ids:
                client_new.append({
                    "id":        article_id,
                    "title":     entry.get("title", "No title"),
                    "link":      entry.get("link", ""),
                    "summary":   entry.get("summary", ""),
                    "published": entry.get("published", ""),
                })
                seen_ids.add(article_id)

        if client_new:
            new[client] = client_new
            print(f"  [OK] {client}: {len(client_new)} new article(s)")
        else:
            print(f"  [OK] {client}: nothing new")

    return new

# ---------------------------------------------------------------------------
# Claude analysis
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = textwrap.dedent("""
    You are a senior media monitoring analyst at a PR and communications agency.
    Your job is to review Google Alert news items and identify anything that is
    GENUINELY significant for the following clients:
    Bapcor, Brisbane Airport, Adore Beauty, Sparesbox, Repco.

    Flag items that relate to:
    - Major business events (acquisitions, mergers, IPOs, leadership changes)
    - Reputation risks (negative press, lawsuits, recalls, data breaches, scandals)
    - Industry-shifting news that affects the client's sector
    - Significant awards, achievements, or growth milestones
    - Crises, safety incidents, or service outages

    Ignore: routine press releases, generic industry trend pieces, minor product mentions,
    syndicated marketing content, and anything low-stakes.

    Return your response in two sections:
    1. INTERESTING FINDINGS — bullet points, each with: client name, headline,
       why it matters, and recommended action.
    2. VERDICT — one sentence: either "Action required" or "Nothing noteworthy today."

    Be concise. If truly nothing stands out, say so honestly.
""").strip()


def analyse_with_claude(articles_by_client: dict[str, list[dict]]) -> tuple[str, bool]:
    """
    Returns (analysis_text, is_interesting).
    is_interesting is True when Claude flags actionable findings.
    """
    # Build the article listing
    lines = []
    for company, articles in articles_by_client.items():
        lines.append(f"### {company}")
        for i, art in enumerate(articles, 1):
            summary_snippet = art["summary"][:400].replace("\n", " ")
            lines.append(f"{i}. {art['title']}")
            lines.append(f"   Summary: {summary_snippet}")
            lines.append(f"   Link: {art['link']}")
            lines.append(f"   Published: {art['published']}")
            lines.append("")
        lines.append("")

    user_message = "Here are today's Google Alert articles:\n\n" + "\n".join(lines)

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1500,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    analysis = response.content[0].text
    is_interesting = "action required" in analysis.lower()
    return analysis, is_interesting

# ---------------------------------------------------------------------------
# Email sending
# ---------------------------------------------------------------------------

def build_html_email(analysis: str, articles_by_client: dict[str, list[dict]]) -> str:
    today = datetime.now().strftime("%A, %B %d %Y")
    total = sum(len(a) for a in articles_by_client.values())

    # Article links section
    article_rows = ""
    for company, articles in articles_by_client.items():
        article_rows += f"""
        <tr>
          <td colspan="2" style="padding:12px 0 4px; font-weight:bold;
              color:#1a365d; font-size:15px;">{company}</td>
        </tr>"""
        for art in articles:
            title   = art["title"]
            link    = art["link"]
            pub     = art.get("published", "")
            article_rows += f"""
        <tr>
          <td style="padding:3px 0; font-size:13px;">
            &bull; <a href="{link}" style="color:#2b6cb0;">{title}</a>
          </td>
          <td style="padding:3px 0; font-size:11px; color:#718096;
              white-space:nowrap; padding-left:12px;">{pub}</td>
        </tr>"""

    # Convert Claude's plain-text analysis to simple HTML
    analysis_html = analysis.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    analysis_html = analysis_html.replace("\n", "<br>")

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f0f4f8;font-family:Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f0f4f8;">
    <tr><td align="center" style="padding:30px 10px;">
      <table width="680" cellpadding="0" cellspacing="0"
             style="background:#ffffff;border-radius:8px;overflow:hidden;
                    box-shadow:0 2px 8px rgba(0,0,0,0.08);">

        <!-- Header -->
        <tr>
          <td style="background:#1a365d;padding:24px 32px;">
            <h1 style="margin:0;color:#ffffff;font-size:22px;">
              Client Media Briefing
            </h1>
            <p style="margin:4px 0 0;color:#bee3f8;font-size:14px;">{today}</p>
          </td>
        </tr>

        <!-- Stats bar -->
        <tr>
          <td style="background:#ebf8ff;padding:10px 32px;
              font-size:13px;color:#2c5282;border-bottom:1px solid #bee3f8;">
            Scanned <strong>{total} new article(s)</strong> across
            <strong>{len(articles_by_client)} client(s)</strong>
          </td>
        </tr>

        <!-- Claude analysis -->
        <tr>
          <td style="padding:28px 32px 16px;">
            <h2 style="margin:0 0 14px;color:#1a365d;font-size:17px;">
              AI Analysis
            </h2>
            <div style="background:#f7fafc;border-left:4px solid #2b6cb0;
                padding:16px 20px;font-size:14px;line-height:1.7;color:#2d3748;">
              {analysis_html}
            </div>
          </td>
        </tr>

        <!-- Article links -->
        <tr>
          <td style="padding:16px 32px 32px;">
            <h2 style="margin:0 0 10px;color:#1a365d;font-size:17px;">
              All New Articles
            </h2>
            <table width="100%" cellpadding="0" cellspacing="0">
              {article_rows}
            </table>
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="background:#f7fafc;padding:14px 32px;
              border-top:1px solid #e2e8f0;font-size:11px;color:#a0aec0;">
            Google Alerts Bot &bull; {today}
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""


def send_email(analysis: str, articles_by_client: dict[str, list[dict]]) -> None:
    today = datetime.now().strftime("%B %d, %Y")
    html  = build_html_email(analysis, articles_by_client)

    message = Mail(
        from_email=FROM_EMAIL,
        to_emails=TO_EMAIL,
        subject=f"[Client Alerts] Interesting news — {today}",
        html_content=html,
    )

    sg = SendGridAPIClient(SENDGRID_API_KEY)
    response = sg.send(message)
    print(f"  Email sent → {TO_EMAIL}  (status {response.status_code})")

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    print(f"\n=== Google Alerts Bot  {datetime.now().strftime('%Y-%m-%d %H:%M')} ===\n")

    # Validate config
    missing = [k for k, v in {
        "ANTHROPIC_API_KEY": ANTHROPIC_API_KEY,
        "SENDGRID_API_KEY":  SENDGRID_API_KEY,
        "TO_EMAIL":          TO_EMAIL,
        "FROM_EMAIL":        FROM_EMAIL,
    }.items() if not v]
    if missing:
        raise SystemExit(f"Missing required environment variables: {', '.join(missing)}")

    seen_ids     = load_seen_ids()
    print("Fetching RSS feeds...")
    new_articles = fetch_new_articles(seen_ids)

    if not new_articles:
        print("\nNo new articles since last run. Nothing to do.")
        save_seen_ids(seen_ids)
        return

    total = sum(len(a) for a in new_articles.values())
    print(f"\nAnalysing {total} new article(s) with Claude...")
    analysis, is_interesting = analyse_with_claude(new_articles)

    # Always persist seen IDs so we don't reprocess
    save_seen_ids(seen_ids)

    if is_interesting:
        print("  Claude flagged interesting content — sending email...")
        send_email(analysis, new_articles)
    else:
        print("  Claude: nothing noteworthy today. No email sent.")

    print("\nDone.\n")


if __name__ == "__main__":
    main()
