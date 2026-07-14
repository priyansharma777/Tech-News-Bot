# 🤖 Automated Daily Tech News

A zero-maintenance GitHub Action that runs every day at **08:00 UTC**, fetches:

- 🔥 Top 10 stories from **Hacker News**
- ⭐ Top 10 **trending GitHub repositories** (created in the last 7 days, sorted by stars)

...and commits the result as a formatted report to [`NEWS.md`](./NEWS.md) in this repo.

No API keys, no external services, no cost — it only uses the free Hacker News
Firebase API and the GitHub REST API (authenticated automatically with the
built-in `GITHUB_TOKEN`).

---

## 📁 Repository structure

```
tech-news-bot/
├── .github/
│   └── workflows/
│       └── daily_news.yml   # The scheduled workflow (cron: 08:00 UTC)
├── main.py                  # Fetch + format logic
├── requirements.txt         # Python dependencies (just `requests`)
├── NEWS.md                  # Auto-generated output — updated daily
└── README.md                # You are here
```

---

## 🚀 Setup instructions

### 1. Create the repository

Create a new **fresh** GitHub repository and push this entire folder structure
to the `main` branch (see "Pushing this project" below if you need help).

### 2. Enable "Read and write permissions" for GitHub Actions

This is the **most important step**. By default, GitHub Actions can only
*read* your repository, so the workflow won't be able to push the updated
`NEWS.md` file back. You must explicitly grant write access:

1. Open your repository on GitHub.com.
2. Click **Settings** (top navigation bar of the repo — not your account settings).
3. In the left sidebar, click **Actions** → **General**.
4. Scroll down to the **"Workflow permissions"** section near the bottom of the page.
5. Select the radio button **"Read and write permissions"**.
6. Click **Save**.

Your screen should end up looking like this:

```
Workflow permissions
  ○ Read repository contents and packages permissions
  ● Read and write permissions          <-- select this one
     Workflows have read and write permissions in the repository for all scopes.

  ☐ Allow GitHub Actions to create and approve pull requests   (leave unchecked, not needed)

  [ Save ]
```

Without this step, the workflow will run successfully up until the final
`git push` step, which will fail with a `403` permission error.

> Note: The workflow file also explicitly declares `permissions: contents: write`
> at the top level. This is a **defense-in-depth** best practice recommended
> for production workflows — it scopes the token down to exactly what's
> needed even if the repository-wide default above is more permissive. Both
> settings are required together for the push to succeed.

### 3. Enable the Actions tab (if disabled)

If this is a brand-new repository, Actions are enabled by default. If you
imported/forked the repo and Actions are disabled, go to the **Actions** tab
and click **"I understand my workflows, go ahead and enable them"**.

### 4. Run it

The workflow will run automatically every day at **08:00 UTC**. To test it
immediately instead of waiting:

1. Go to the **Actions** tab.
2. Click **"Automated Daily Tech News"** in the left sidebar.
3. Click **"Run workflow"** → **"Run workflow"** (green button).
4. After ~30 seconds, refresh — you should see a new commit updating `NEWS.md`.

---

## 🔧 Configuration

All tunables live at the top of `main.py`:

| Variable | Default | Description |
|---|---|---|
| `HN_STORY_COUNT` | `10` | Number of Hacker News stories to include |
| `GITHUB_REPO_COUNT` | `10` | Number of trending repos to include |
| `GITHUB_TRENDING_WINDOW_DAYS` | `7` | How recently a repo must have been created to count as "trending" |
| `REQUEST_TIMEOUT` | `10` | Per-request timeout (seconds) |
| `MAX_RETRIES` | `3` | Retry attempts per HTTP request before giving up |

To change the schedule, edit the `cron` expression in
`.github/workflows/daily_news.yml`:

```yaml
on:
  schedule:
    - cron: "0 8 * * *"   # minute hour day month day-of-week, all in UTC
```

Use [crontab.guru](https://crontab.guru/) to build custom schedules.

> ⚠️ GitHub's scheduled workflows are **best-effort**: during periods of high
> load, a run can be delayed by several minutes to (rarely) longer. This is
> a platform-level limitation, not a bug in this project.

---

## 🛡️ Why this is production-ready

- **Retries with backoff** on every HTTP call — a single flaky request
  won't crash the run.
- **Graceful degradation** — if one data source (HN or GitHub) fails, the
  report is still generated with whichever source succeeded. It only aborts
  (and skips overwriting `NEWS.md`) if *both* sources fail, so you never end
  up with a blank report overwriting good historical data.
- **Authenticated GitHub API calls** using the auto-provided `GITHUB_TOKEN`,
  avoiding the unauthenticated 60 requests/hour rate limit.
- **Idempotent commits** — if the fetched content is identical to what's
  already committed, the workflow exits cleanly without creating an empty
  commit.
- **Concurrency guard** (`concurrency:` block) prevents overlapping runs
  from racing each other on the same branch.
- **Push retry with rebase** guards against the rare case of a conflicting
  commit landing between checkout and push.
- **Least-privilege token scope** via `permissions: contents: write`,
  rather than relying solely on the repository-wide default.

---

## 🧪 Running locally

```bash
git clone <your-repo-url>
cd tech-news-bot
pip install -r requirements.txt
python main.py
```

This will fetch live data and overwrite `NEWS.md` locally — no GitHub token
is required to run it locally (the script falls back to unauthenticated
GitHub API calls, just with a lower rate limit).

---

## 📄 License

Free to use, modify, and distribute for any purpose.
