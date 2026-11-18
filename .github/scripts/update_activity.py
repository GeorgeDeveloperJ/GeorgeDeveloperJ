"""Refresh the profile README from the user's public GitHub events."""

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

START = "<!-- activity:start -->"
END = "<!-- activity:end -->"


def activity_lines(events, username):
    lines = []
    for event in events:
        if not event["public"] or event["actor"]["login"].casefold() != username.casefold():
            continue

        repository = event["repo"]["name"]
        if not re.fullmatch(r"[A-Za-z0-9-]+/[A-Za-z0-9_.-]+", repository):
            continue

        payload = event["payload"]
        url = f"https://github.com/{repository}"
        match event["type"]:
            case "PushEvent":
                commit = payload.get("head", "")
                label = "Pushed to"
                if re.fullmatch(r"[0-9a-f]{40}", commit or ""):
                    url += f"/commit/{commit}"
            case "PullRequestEvent":
                number = payload.get("number") or payload.get("pull_request", {}).get("number")
                if not isinstance(number, int) or number < 1:
                    continue
                label = "Updated a pull request in"
                url += f"/pull/{number}"
            case "ReleaseEvent":
                if payload["action"] != "published" or payload["release"]["draft"]:
                    continue
                tag = quote(payload["release"]["tag_name"], safe="").replace("(", "%28").replace(")", "%29")
                label = "Published a release in"
                url += f"/releases/tag/{tag}"
            case _:
                continue

        date = datetime.fromisoformat(event["created_at"].replace("Z", "+00:00")).date()
        lines.append(f"- {date} · {label} [{repository}]({url})")
        if len(lines) == 5:
            break
    return "\n".join(lines)


def fetch_json(path):
    request = Request(
        f"https://api.github.com/{path}",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "github-profile-readme"},
    )
    with urlopen(request, timeout=20) as response:
        return json.load(response)


def refresh(readme, username, profile_repository):
    original = readme.read_text(encoding="utf-8")
    if original.count(START) != 1 or original.count(END) != 1 or original.index(START) > original.index(END):
        raise ValueError("README must contain exactly one pair of ordered activity markers")

    events = fetch_json(f"users/{quote(username, safe='')}/events/public?per_page=100")
    activity = activity_lines(events, username)
    if not activity:
        repository = quote(profile_repository, safe="/")
        commits = fetch_json(f"repos/{repository}/commits?author={quote(username, safe='')}&per_page=1")
        activity = "_No recent public work._"
        if commits:
            commit = commits[0]
            date = datetime.fromisoformat(commit["commit"]["author"]["date"].replace("Z", "+00:00")).date()
            sha = commit["sha"]
            if not re.fullmatch(r"[0-9a-f]{40}", sha):
                raise ValueError("Invalid commit SHA in GitHub response")
            activity = f"- {date} · [Latest profile edit](https://github.com/{repository}/commit/{sha})"

    before, _, rest = original.partition(START)
    _, _, after = rest.partition(END)
    updated = f"{before}{START}\n{activity}\n{END}{after}"
    if updated != original:
        readme.write_text(updated, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("username")
    parser.add_argument("profile_repository")
    args = parser.parse_args()
    try:
        refresh(Path("README.md"), args.username, args.profile_repository)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"Could not refresh GitHub activity: {error}\n")


if __name__ == "__main__":
    main()
