#!/usr/bin/env python3
"""
Automated Daily Tech News
--------------------------
Fetches:
  1. Top stories from Hacker News (via the official Firebase API - no key required)
  2. Trending GitHub repositories created in the last 7 days (via the GitHub REST API)

...and writes the result as a formatted Markdown report to NEWS.md.

Designed to be run unattended inside a GitHub Actions workflow. All network
calls are wrapped in retries + timeouts so a single flaky request never
crashes the whole job, and the script always writes *something* useful to
NEWS.md even if one of the two sources fails.
"""

from __future__ import annotations

import datetime as dt
import logging
import os
import sys
import time
from dataclasses import dataclass

import requests

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

HN_TOP_STORIES_URL = "https://hacker-news.firebaseio.com/v0/topstories.json"
HN_ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{item_id}.json"
GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"

HN_STORY_COUNT = 10
GITHUB_REPO_COUNT = 10
GITHUB_TRENDING_WINDOW_DAYS = 7

REQUEST_TIMEOUT = 10          # seconds
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 2

OUTPUT_FILE = "NEWS.md"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("daily-tech-news")


# --------------------------------------------------------------------------- #
# Data models
# --------------------------------------------------------------------------- #

@dataclass
class HNStory:
    title: str
    url: str
    score: int
    comments: int
    hn_id: int

    @property
    def discussion_url(self) -> str:
        return f"https://news.ycombinator.com/item?id={self.hn_id}"


@dataclass
class TrendingRepo:
    full_name: str
    url: str
    description: str
    stars: int
    language: str


# --------------------------------------------------------------------------- #
# HTTP helper with retry logic
# --------------------------------------------------------------------------- #

def get_with_retries(url: str, *, params: dict | None = None,
                      headers: dict | None = None) -> requests.Response | None:
    """GET a URL with basic retry + exponential backoff. Returns None on total failure."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            return resp
        except requests.exceptions.RequestException as exc:
            log.warning("Request to %s failed (attempt %d/%d): %s", url, attempt, MAX_RETRIES, exc)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF_SECONDS * attempt)
    log.error("Giving up on %s after %d attempts", url, MAX_RETRIES)
    return None


# --------------------------------------------------------------------------- #
# Fetchers
# --------------------------------------------------------------------------- #

def fetch_hacker_news(limit: int = HN_STORY_COUNT) -> list[HNStory]:
    """Fetch the current top Hacker News stories."""
    log.info("Fetching top %d Hacker News stories...", limit)
    resp = get_with_retries(HN_TOP_STORIES_URL)
    if resp is None:
        log.error("Could not reach Hacker News API. Skipping this section.")
        return []

    try:
        story_ids = resp.json()[:limit]
    except (ValueError, TypeError) as exc:
        log.error("Unexpected Hacker News response format: %s", exc)
        return []

    stories: list[HNStory] = []
    for story_id in story_ids:
        item_resp = get_with_retries(HN_ITEM_URL.format(item_id=story_id))
        if item_resp is None:
            continue
        try:
            data = item_resp.json()
            if not data or data.get("type") != "story":
                continue
            stories.append(
                HNStory(
                    title=data.get("title", "Untitled"),
                    url=data.get("url", f"https://news.ycombinator.com/item?id={story_id}"),
                    score=data.get("score", 0),
                    comments=data.get("descendants", 0),
                    hn_id=story_id,
                )
            )
        except (ValueError, TypeError) as exc:
            log.warning("Skipping malformed HN item %s: %s", story_id, exc)
            continue

    log.info("Fetched %d Hacker News stories.", len(stories))
    return stories


def fetch_trending_github_repos(limit: int = GITHUB_REPO_COUNT) -> list[TrendingRepo]:
    """
    Fetch trending GitHub repos using the Search API, sorted by stars,
    restricted to repos created within the last GITHUB_TRENDING_WINDOW_DAYS days.

    GitHub has no official "trending" API, so this is the standard
    community-accepted approximation.
    """
    log.info("Fetching trending GitHub repositories...")

    since_date = (dt.datetime.utcnow() - dt.timedelta(days=GITHUB_TRENDING_WINDOW_DAYS)).strftime("%Y-%m-%d")
    query = f"created:>{since_date}"

    headers = {"Accept": "application/vnd.github+json"}
    # GITHUB_TOKEN is automatically injected by GitHub Actions and greatly
    # raises the API rate limit (60/hr unauthenticated -> 5000/hr authenticated).
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    params = {
        "q": query,
        "sort": "stars",
        "order": "desc",
        "per_page": limit,
    }

    resp = get_with_retries(GITHUB_SEARCH_URL, params=params, headers=headers)
    if resp is None:
        log.error("Could not reach GitHub Search API. Skipping this section.")
        return []

    try:
        items = resp.json().get("items", [])
    except (ValueError, TypeError) as exc:
        log.error("Unexpected GitHub response format: %s", exc)
        return []

    repos: list[TrendingRepo] = []
    for item in items:
        try:
            repos.append(
                TrendingRepo(
                    full_name=item["full_name"],
                    url=item["html_url"],
                    description=(item.get("description") or "No description provided.").strip(),
                    stars=item.get("stargazers_count", 0),
                    language=item.get("language") or "Unknown",
                )
            )
        except KeyError as exc:
            log.warning("Skipping malformed repo entry: %s", exc)
            continue

    log.info("Fetched %d trending GitHub repositories.", len(repos))
    return repos


# --------------------------------------------------------------------------- #
# Markdown rendering
# --------------------------------------------------------------------------- #

def render_markdown(stories: list[HNStory], repos: list[TrendingRepo]) -> str:
    today = dt.datetime.utcnow().strftime("%Y-%m-%d")
    now = dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    lines: list[str] = []
    lines.append(f"# 📰 Daily Tech News — {today}")
    lines.append("")
    lines.append(f"_Last updated: {now}_")
    lines.append("")

    lines.append("## 🔥 Hacker News — Top Stories")
    lines.append("")
    if stories:
        for i, s in enumerate(stories, start=1):
            lines.append(
                f"{i}. **[{s.title}]({s.url})** — {s.score} pts, "
                f"{s.comments} comments ([discussion]({s.discussion_url}))"
            )
    else:
        lines.append("_Could not fetch Hacker News stories today._")
    lines.append("")

    lines.append(f"## ⭐ Trending GitHub Repositories (last {GITHUB_TRENDING_WINDOW_DAYS} days)")
    lines.append("")
    if repos:
        for i, r in enumerate(repos, start=1):
            lines.append(
                f"{i}. **[{r.full_name}]({r.url})** — ⭐ {r.stars} — `{r.language}`  \n"
                f"   {r.description}"
            )
    else:
        lines.append("_Could not fetch trending GitHub repositories today._")
    lines.append("")

    lines.append("---")
    lines.append("_Generated automatically by [Automated Daily Tech News](.github/workflows/daily_news.yml)._")
    lines.append("")

    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main() -> int:
    log.info("Starting Automated Daily Tech News run...")

    stories = fetch_hacker_news()
    repos = fetch_trending_github_repos()

    if not stories and not repos:
        log.error("Both data sources failed. Aborting without overwriting NEWS.md.")
        return 1

    markdown = render_markdown(stories, repos)

    try:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write(markdown)
    except OSError as exc:
        log.error("Failed to write %s: %s", OUTPUT_FILE, exc)
        return 1

    log.info("Successfully wrote report to %s", OUTPUT_FILE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
