#!/usr/bin/env python3
"""Generates docs/ from site.toml, templates/ and the commits found by the GitHub API. Needs GITHUB_TOKEN."""
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import time
import tomllib
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from string import Template

ROOT = Path(__file__).resolve().parent
DOCS = ROOT / "docs"
TEMPLATES = ROOT / "templates"
SITE = tomllib.loads((ROOT / "site.toml").read_text())


def repository():
    """Returns owner/name of this repository, from GitHub Actions or the git remote."""
    if "GITHUB_REPOSITORY" in os.environ:
        return os.environ["GITHUB_REPOSITORY"]
    remote = subprocess.run(["git", "-C", ROOT, "remote", "get-url", "origin"], capture_output=True, text=True, check=True)
    return re.search(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?$", remote.stdout.strip()).group(1)


OWNER, NAME = repository().split("/")
USER = SITE.get("user", OWNER)
# A repository named <owner>.github.io is served at the root of that domain.
PAGES = f"https://{OWNER.lower()}.github.io/"
BASE = SITE.get("url") or (PAGES if NAME.lower() == f"{OWNER.lower()}.github.io" else f"{PAGES}{NAME}/")
# GitHub's commit list times out on these repositories when filtered by author.
SEARCH_BUTTON = {"torvalds/linux"}


def with_defaults(project):
    """Fills in what a project from site.toml or from a fork leaves out."""
    repo = project["repo"]
    name = repo.split("/")[1]
    if repo.lower() in SEARCH_BUTTON:
        query = {"q": f"repo:{repo} author:{USER}", "type": "commits", "s": "author-date", "o": "desc"}
        commits = f"https://github.com/search?{urllib.parse.urlencode(query)}"
    else:
        commits = f"https://github.com/{repo}/commits?author={USER}"
    project = {
        "slug": name.lower(),
        "name": name,
        "commits": commits,
        "accent": SITE["accent"],
        "description": Template(SITE["other_description"]).safe_substitute(repo=project["repo"]),
        **project,
    }
    project["commits"] = Template(project["commits"]).safe_substitute(user=USER)
    return project


PROJECTS = [with_defaults(p) for p in SITE.get("project", [])]
TRAILER = re.compile(
    r"(Signed-off-by|Reviewed-by|Suggested-by|Reported-by|Tested-by|Acked-by|Co-authored-by|Cc|PR-URL|Refs|Fixes"
    r"|Link|Approved by|Pull Request resolved|Change-Id|Bug|Commit-Queue|Reviewed-on|Cr-Commit-Position):\s",
    re.I,
)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
OWN_LINE = re.compile(r"\s|[-*#]|\d+\. ")


def read(name):
    return (TEMPLATES / name).read_text().rstrip("\n")


CSS = read("style.css")
PAGE, PROJECT, COMMIT, HOME, ITEM = (
    Template(read(f"{name}.html")) for name in ("page", "project", "commit", "home", "item")
)

e = html.escape


def fetch_commits(repo):
    commits, page = [], 1
    while True:
        query = {"q": f"repo:{repo} author:{USER}", "sort": "author-date", "order": "desc", "per_page": 100, "page": page}
        request = urllib.request.Request(
            f"https://api.github.com/search/commits?{urllib.parse.urlencode(query)}",
            headers={"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}", "Accept": "application/vnd.github+json"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.load(response)
            # Commit search allows 30 requests a minute, fewer than a build makes with many forks.
            if response.headers["X-RateLimit-Remaining"] == "0":
                time.sleep(max(0, int(response.headers["X-RateLimit-Reset"]) - time.time()) + 1)
        commits += result["items"]
        if not result["items"] or len(commits) >= result["total_count"]:
            break
        page += 1
    # Stopping here keeps the published site as it is instead of replacing it with a short list.
    if result["incomplete_results"] or len(commits) < result["total_count"]:
        sys.exit(f"incomplete commit search for {repo}")
    return commits


def fetch_profile():
    """Returns the user's display name, LinkedIn URL and the repositories their public forks were made from."""
    # A local token also sees private forks, whose names must not reach the site.
    # ponytail: first 100 forks only, paginate with pageInfo past that.
    query = "query($login:String!){user(login:$login){name socialAccounts(first:10){nodes{provider url}} repositories(first:100,isFork:true,privacy:PUBLIC){nodes{parent{nameWithOwner}}}}}"
    request = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": {"login": USER}}).encode(),
        headers={"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        user = json.load(response)["data"]["user"]
    linkedin = next((a["url"] for a in user["socialAccounts"]["nodes"] if a["provider"] == "LINKEDIN"), None)
    return user["name"], linkedin, [n["parent"]["nameWithOwner"] for n in user["repositories"]["nodes"] if n["parent"]]


def discover(forked):
    """Returns a project with generic text for each forked repository not in PROJECTS or hide."""
    skip = {p["repo"].lower() for p in PROJECTS} | {repo.lower() for repo in SITE.get("hide", [])}
    slugs = {p["slug"] for p in PROJECTS}
    projects = []
    for repo in forked:
        if repo.lower() in skip:
            continue
        owner, name = repo.lower().split("/")
        slug = name if name not in slugs else f"{owner}-{name}"
        slugs.add(slug)
        projects.append(with_defaults({"repo": repo, "slug": slug}))
    return projects


def image_tags(path, title):
    """Returns the preview image tags for an image in the repository, which is copied into docs/."""
    if not path:
        return ""
    source = ROOT / path
    shutil.copy(source, DOCS / source.name)
    # LinkedIn caches images by URL and keeps the old one even after a new scrape.
    version = hashlib.sha256(source.read_bytes()).hexdigest()[:8]
    return (
        f'<meta property="og:image" content="{e(BASE + source.name)}?v={version}">\n'
        f'<meta property="og:image:alt" content="{e(title)}">\n'
        '<meta name="twitter:card" content="summary_large_image">'
    )


def describe(message):
    """Returns a commit's body without trailers or e-mail addresses, and with hard wraps removed."""
    lines, fenced = [], False
    for line in message.partition("\n")[2].split("\n"):
        if line.startswith("```"):
            fenced = not fenced
            lines.append("")
        elif TRAILER.match(line) or EMAIL.search(line):
            continue
        elif fenced or not line or OWN_LINE.match(line) or not lines or not lines[-1] or re.match(r"\s|#", lines[-1]):
            lines.append(line)
        else:
            lines[-1] += " " + line
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    return re.sub(r"^#+ ", "", text, flags=re.M)


def about(project):
    """Returns the description paragraph, which pages made from forks leave out."""
    return f"<p>{e(project['description'])}</p>" if project in PROJECTS else ""


def count_label(commits):
    return f"{len(commits)} commit{'' if len(commits) == 1 else 's'}"


def write_page(path, title, description, accent, body, image):
    page = PAGE.substitute(
        title=e(title),
        description=e(description),
        url=e(BASE + path),
        image=image_tags(image, title),
        accent=accent,
        css=CSS,
        body=body,
        notice=e(SITE["notice"]),
    )
    out = DOCS / path / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page)


def main():
    name, linkedin, forked = fetch_profile()
    author = SITE.get("author") or name or USER
    others = discover(forked)
    found = {p["slug"]: fetch_commits(p["repo"]) for p in PROJECTS + others}
    for p in PROJECTS:
        if not found[p["slug"]]:
            sys.exit(f"no commits by {USER} in {p['repo']}: remove it from site.toml or check your commit e-mail")
    others = sorted((p for p in others if found[p["slug"]]), key=lambda p: (-len(found[p["slug"]]), p["slug"]))
    projects = PROJECTS + others
    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    shutil.rmtree(DOCS, ignore_errors=True)
    DOCS.mkdir()

    for p in projects:
        commits = found[p["slug"]]
        items = "\n".join(
            COMMIT.substitute(
                date=c["commit"]["author"]["date"][:10],
                url=e(c["html_url"]),
                subject=e(c["commit"]["message"].split("\n")[0]),
                message=e(describe(c["commit"]["message"])),
            )
            for c in commits
        )
        body = PROJECT.substitute(
            name=e(p["name"]),
            repo=e(p["repo"]),
            about=about(p),
            commits=e(p["commits"]),
            count=count_label(commits),
            items=items,
            updated=updated,
            user=USER,
            author=e(author),
        )
        title = f"{p['name']} Upstream Commits | {author}"
        write_page(f"{p['slug']}/", title, p["description"], p["accent"], body, p.get("image", SITE.get("image")))

    links = f'<a href="https://github.com/{USER}">GitHub</a>'
    if linkedin:
        links += f' · <a href="{e(linkedin)}">LinkedIn</a>'
    items = "\n".join(
        ITEM.substitute(
            accent=p["accent"],
            name=e(p["name"]),
            repo=e(p["repo"]),
            count=count_label(found[p["slug"]]),
            about=about(p),
            slug=p["slug"],
        )
        for p in projects
    )
    write_page(
        "",
        f"Upstream Commits | {author}",
        SITE["home_description"],
        SITE["accent"],
        HOME.substitute(author=e(author), links=links, items=items),
        SITE.get("image"),
    )


if __name__ == "__main__":
    main()
