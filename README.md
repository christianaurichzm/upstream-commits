# Upstream Commits

A page with your open source contributions that updates itself. Every project you have
commits in gets a page listing them with their full descriptions, plus a home page with
all of them. The pages have their own link previews, so they work in LinkedIn Featured,
a résumé, a personal site or a chat message, and visitors read your commits without
running into GitHub's rate limit for logged-out users.

Example: https://christianaurichzm.github.io/upstream-commits/

It runs on GitHub Pages and GitHub Actions, for free, with no server and no dependencies.

## Use it

1. Click **Use this template** and create a public repository.
2. In the new repository, open **Settings > Pages** and set **Source** to **GitHub Actions**.
3. Edit `site.toml`: replace the `[[project]]` sections with your own projects or delete
   them, and rewrite `home_description` and `notice`.
4. Open **Actions > Publish** and click **Run workflow**.

The site is published at `https://<your-user>.github.io/<repository>/` and rebuilt every
day, so new commits and projects show up on their own.

## Which commits show up

Your commits are found with GitHub's commit search, in two places:

- the projects in `site.toml`, which come first and can have their own text;
- every repository one of your public forks was made from, once it has a commit of yours.
  These pages use `other_description` from `site.toml`. To leave one out, add it to `hide`.

Commit search only sees the default branch of each repository and commits made with an
e-mail address linked to your GitHub account. Commit trailers and any line with an e-mail
address are left out of the descriptions.

## Edit

Everything can be edited in the GitHub web editor, and a push to `main` publishes it:

- `site.toml`: texts, colors, projects and the optional preview image.
- `templates/*.html`: the layout of each page. Words starting with `$`, such as `$name`
  or `$items`, are filled in by the build.
- `templates/style.css`: the styles.

If a change breaks the build, the deploy stops, the site keeps its last version and the
error shows in the Actions tab.

## Preview image

Pages have no preview image unless `site.toml` sets `image` to a PNG or JPEG in the
repository, ideally 1200x627. A project can set its own `image` too. LinkedIn keeps an
image it has seen, so the build adds a content hash to the image URL. After a change,
paste the URL into the [Post Inspector](https://www.linkedin.com/post-inspector/) to
refresh LinkedIn's preview.

## Build and check locally

```bash
GITHUB_TOKEN=$(gh auth token) python3 build.py
python3 -m http.server 8000 --directory docs
python3 check.py http://localhost:8000/
```

`check.py` reads each page as LinkedIn's crawler would, with no JavaScript, and checks the
link preview tags, the commit lists and that no e-mail address reached a page. Without an
argument it checks the published site.
