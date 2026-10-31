#!/usr/bin/env python3
"""Reads every page the way LinkedIn's crawler does and checks its preview.

Usage: python3 check.py [base-url]    Default: the published site.
"""
import sys
import urllib.request
from html.parser import HTMLParser

from build import BASE, EMAIL, PROJECTS, describe

CRAWLER = "LinkedInBot/1.0 (compatible; Mozilla/5.0; Apache-HttpClient +http://www.linkedin.com)"
REQUIRED = ("og:title", "og:description", "og:url")
MESSAGE = """Subject

## Summary

First line, note: this
is the same paragraph.

- a list item

    indented code

Signed-off-by: Someone <someone@example.org>
R=someone@example.org
"""
DESCRIPTION = """Summary

First line, note: this is the same paragraph.

- a list item

    indented code"""


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.og, self.canonical, self.commits, self.refresh, self.listed, self.projects = {}, None, None, False, 0, []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "meta" and a.get("property", "").startswith("og:"):
            self.og[a["property"]] = a.get("content")
        elif tag == "meta" and a.get("http-equiv", "").lower() == "refresh":
            self.refresh = True
        elif tag == "link" and a.get("rel") == "canonical":
            self.canonical = a.get("href")
        elif tag == "a" and a.get("id") == "commits":
            self.commits = a.get("href")
        elif tag == "a" and "/commit/" in a.get("href", ""):
            self.listed += 1
        elif tag == "a" and a.get("href", "").endswith("/") and not a["href"].startswith((".", "http")):
            self.projects.append(a["href"])


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": CRAWLER})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.url, response.read()


def problems(base, path, commits):
    url = base + path
    final, body = fetch(url)
    page = Page()
    page.feed(body.decode())
    expected = BASE + path

    if final != url:
        yield f"HTTP redirect to {final}"
    if page.refresh:
        yield "meta refresh would send crawlers away"
    for tag in REQUIRED:
        if not page.og.get(tag):
            yield f"missing {tag}"
    if page.og.get("og:url") != expected:
        yield f"og:url is {page.og.get('og:url')}"
    if page.canonical != expected:
        yield f"canonical is {page.canonical}"
    if commits and page.commits != commits:
        yield f"button points to {page.commits}"
    if commits is not None and not page.listed:
        yield "no commits listed"
    if EMAIL.search(body.decode()):
        yield "e-mail address on the page"


def main():
    assert describe(MESSAGE) == DESCRIPTION
    base = sys.argv[1].rstrip("/") + "/" if len(sys.argv) > 1 else BASE
    home = Page()
    home.feed(fetch(base)[1].decode())
    # Pages found from forks are not in PROJECTS, so only their list is checked, not their button.
    buttons = {f"{p['slug']}/": p["commits"] for p in PROJECTS}
    pages = [("", None)] + [(path, buttons.get(path, "")) for path in dict.fromkeys([*buttons, *home.projects])]
    failed = False
    for path, commits in pages:
        found = list(problems(base, path, commits))
        failed = failed or bool(found)
        print(f"{'FAIL' if found else 'ok'}  /{path}")
        for problem in found:
            print(f"      {problem}")
    sys.exit(failed)


if __name__ == "__main__":
    main()
