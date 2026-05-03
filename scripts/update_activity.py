#!/usr/bin/env python3
"""
Fetches recent GitHub activity (commits, issues, PRs) for a user
and updates the ACTIVITY:START / ACTIVITY:END block in README.md.
"""

import os
import re
import requests
from datetime import datetime, timezone

USERNAME = os.environ.get("GITHUB_USERNAME", "juushimatsu")
TOKEN    = os.environ.get("GITHUB_TOKEN", "")
LIMIT    = 10  # max events to show

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


def time_ago(iso: str) -> str:
    dt  = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    diff = now - dt
    s = int(diff.total_seconds())
    if s < 3600:
        return f"{s // 60}m ago"
    if s < 86400:
        return f"{s // 3600}h ago"
    if s < 604800:
        return f"{s // 86400}d ago"
    return f"{s // 604800}w ago"


def fetch_events() -> list[dict]:
    url = f"https://api.github.com/users/{USERNAME}/events/public?per_page=100"
    r   = requests.get(url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    return r.json()


def parse_events(events: list[dict]) -> list[str]:
    lines = []
    seen  = set()

    for ev in events:
        if len(lines) >= LIMIT:
            break

        etype  = ev.get("type", "")
        repo   = ev["repo"]["name"].replace(f"{USERNAME}/", "")
        when   = time_ago(ev["created_at"])
        key    = None
        label  = None

        # ── Commits ──────────────────────────────────────────────
        if etype == "PushEvent":
            commits = ev["payload"].get("commits", [])
            n = len(commits)
            if n == 0:
                continue
            msg = commits[-1]["message"].split("\n")[0][:48]
            key   = f"push-{ev['id']}"
            label = f"[{when:>6}]  pushed {n} commit{'s' if n>1 else ''}  →  {repo}  \"{msg}\""

        # ── Issues ───────────────────────────────────────────────
        elif etype == "IssuesEvent":
            action = ev["payload"]["action"]          # opened / closed / reopened
            title  = ev["payload"]["issue"]["title"][:48]
            key    = f"issue-{ev['id']}"
            label  = f"[{when:>6}]  issue {action:<8}  →  {repo}  \"{title}\""

        # ── Pull Requests ────────────────────────────────────────
        elif etype == "PullRequestEvent":
            action = ev["payload"]["action"]          # opened / closed / merged
            pr     = ev["payload"].get("pull_request", {})
            merged = pr.get("merged", False)
            if action == "closed" and merged:
                action = "merged"
            title  = pr.get("title", "untitled")[:48]
            key    = f"pr-{ev['id']}"
            label  = f"[{when:>6}]  PR {action:<10}  →  {repo}  \"{title}\""

        # ── PR Review ────────────────────────────────────────────
        elif etype == "PullRequestReviewEvent":
            title = ev["payload"].get("pull_request", {}).get("title", "untitled")[:48]
            key   = f"review-{ev['id']}"
            label = f"[{when:>6}]  PR reviewed    →  {repo}  \"{title}\""

        # ── Fork ─────────────────────────────────────────────────
        elif etype == "ForkEvent":
            forkee = ev["payload"]["forkee"]["full_name"]
            key    = f"fork-{ev['id']}"
            label  = f"[{when:>6}]  forked         →  {forkee}"

        # ── Create branch/tag ─────────────────────────────────────
        elif etype == "CreateEvent":
            ref_type = ev["payload"].get("ref_type", "")
            ref      = ev["payload"].get("ref") or repo
            if ref_type in ("branch", "tag"):
                key   = f"create-{ev['id']}"
                label = f"[{when:>6}]  created {ref_type:<6}  →  {repo}  \"{ref}\""

        # ── Release ─────────────────────────────────────────────────
        elif etype == "ReleaseEvent":
            action  = ev["payload"].get("action", "published")
            release = ev["payload"].get("release", {})
            tag     = release.get("tag_name", "")[:48]
            key     = f"release-{ev['id']}"
            label   = f"[{when:>6}]  release {action:<6}  →  {repo}  \"{tag}\""

        if key and key not in seen and label:
            seen.add(key)
            lines.append(label)

    return lines


def update_readme(lines: list[str]) -> None:
    readme_path = "README.md"
    with open(readme_path, "r", encoding="utf-8") as f:
        content = f.read()

    block = "```\n" + "\n".join(lines) + "\n```"
    new_content = re.sub(
        r"(<!-- ACTIVITY:START -->).*?(<!-- ACTIVITY:END -->)",
        rf"\1\n{block}\n\2",
        content,
        flags=re.DOTALL,
    )

    if new_content == content:
        print("README unchanged.")
        return

    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(new_content)
    print(f"README updated with {len(lines)} activity lines.")


if __name__ == "__main__":
    events = fetch_events()
    lines  = parse_events(events)
    if not lines:
        lines = ["no public activity found"]
    update_readme(lines)
