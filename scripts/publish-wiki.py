#!/usr/bin/env python3
"""Publish the Transversal manuals to the repository's GitHub wiki.

The vault in `docs/` is the source of truth; the wiki is a derived reading
surface, so it is generated rather than hand-edited. This script converts the
Obsidian notes in `docs/Manual/` into GitHub wiki pages:

  * YAML frontmatter is dropped (GitHub renders it as a metadata table, and the
    notes all carry an `# H1` title already).
  * Obsidian callouts (`> [!warning] Title`) become a quoted bold lead-in with
    the body un-quoted, so tables and lists inside them render normally.
  * `[[wikilinks]]` become wiki page links for the manuals, and links to the
    repository's rendered markdown for every other note they point at, so
    nothing dangles. A note the repository does not publish (the coordination
    layer was redacted when the repo went public) keeps its words as plain
    text rather than becoming a link a reader cannot follow.

Usage:
    python3 scripts/publish-wiki.py                 # generate into a temp dir
    python3 scripts/publish-wiki.py --out DIR       # generate somewhere else
    python3 scripts/publish-wiki.py --push          # generate, then push

`--push` needs the wiki git repository to exist, and GitHub only creates it
once a first page has been saved in the browser (there is no API for it). Until
then this prints the one manual step instead of failing obscurely.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
from pathlib import Path

REPO = "Davografie/transversal"
BRANCH = "release-build"
WIKI_URL = f"https://github.com/{REPO}.wiki.git"
REPO_ROOT = Path(__file__).resolve().parent.parent
MANUAL_DIR = REPO_ROOT / "docs" / "Manual"
DOCS_DIR = REPO_ROOT / "docs"

# The manual that reads first, and a one-line description for each page.
INDEX = [
    ("Architect's Manual", "Start here: what an Architect is, the vocabulary, the toolbox, and where to go for each job."),
    ("Getting Started", "Join a session, claim a character, and arrive at your first location."),
    ("User Manual", "The index: how to play and run the game, plus the die-rating and outcome tables."),
    ("Location Authoring", "Make a place playable and then rich: backgrounds, stat blocks, occupants, zones, portals, challenges."),
    ("Faction Authoring", "Build an organisation: its roster, its want, its agenda, and the weak link players can attack."),
    ("SFX Authoring", "Write a rule that bends the rules, and the effects it runs."),
    ("SFX Reference", "The lookup: every trigger, condition, source, path step and effect action."),
    ("Roll Table and Life Path Authoring", "Write lists of outcomes, and the chains a character walks for growth."),
]

CALLOUT = re.compile(r"^>\s*\[!(\w+)\]\s*(.*)$")
WIKILINK = re.compile(r"\[\[([^\]|#]*)(#[^\]|]*)?(?:\|([^\]]*))?\]\]")


def slug(text: str) -> str:
    """A GitHub-style heading anchor."""
    text = text.strip().lower()
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"\s+", "-", text)


def page_name(title: str) -> str:
    """A wiki page name: spaces become hyphens in the URL, the file keeps them."""
    return title.replace(" ", "-")


def note_index() -> dict[str, str]:
    """Every note in the vault, by title and by alias, to its repository path."""
    found: dict[str, str] = {}
    for path in DOCS_DIR.rglob("*.md"):
        found[path.stem] = path.relative_to(REPO_ROOT).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        front = re.match(r"^---\n(.*?)\n---", text, re.S)
        if not front:
            continue
        block = re.search(r"^aliases:\n((?:\s+-\s+.*\n)+)", front.group(1), re.M)
        if block:
            for alias in re.findall(r"^\s+-\s+[\"']?([^\"'\n]+?)[\"']?\s*$", block.group(1), re.M):
                found.setdefault(alias.strip(), path.relative_to(REPO_ROOT).as_posix())
    return found


def blob_url(repo_path: str) -> str:
    quoted = urllib.parse.quote(repo_path, safe="/")
    return f"https://github.com/{REPO}/blob/{BRANCH}/{quoted}"


def convert_links(text: str, pages: dict[str, str], notes: dict[str, str]) -> str:
    """`[[Target|Alias]]` -> a wiki page link, or a link into the repository."""

    def replace(match: re.Match[str]) -> str:
        target = (match.group(1) or "").strip()
        anchor = (match.group(2) or "").lstrip("#").strip()
        display = (match.group(3) or "").strip()

        # A link inside the page: [[#Some heading]]
        if not target:
            label = display or anchor
            return f"[{label}](#{slug(anchor)})"

        label = display or target
        if target in pages:
            href = pages[target]
            return f"[{label}]({href}#{slug(anchor)})" if anchor else f"[{label}]({href})"
        if target in notes:
            return f"[{label}]({blob_url(notes[target])})"
        return label  # nothing to point at: keep the words, drop the link

    return WIKILINK.sub(replace, text)


def convert_callouts(text: str) -> str:
    """`> [!warning] Title` + quoted body -> a bold lead-in and a plain body."""
    lines = text.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        match = CALLOUT.match(lines[i])
        if not match:
            out.append(lines[i])
            i += 1
            continue
        kind, title = match.group(1).capitalize(), match.group(2).strip()
        lead = f"{kind} — {title}" if title else kind
        body: list[str] = []
        i += 1
        while i < len(lines) and (lines[i].startswith(">") or lines[i].strip() == ""):
            if lines[i].strip() == "":
                # A blank line ends the callout unless the quote resumes.
                if i + 1 < len(lines) and lines[i + 1].startswith(">"):
                    body.append("")
                    i += 1
                    continue
                break
            body.append(re.sub(r"^>\s?", "", lines[i]))
            i += 1
        while body and body[-1] == "":
            body.pop()
        out.append(f"> **{lead}**")
        if body:
            out.append("")
            out.extend(body)
        out.append("")
    return "\n".join(out)


def strip_frontmatter(text: str) -> str:
    return re.sub(r"^---\n.*?\n---\n+", "", text, count=1, flags=re.S)


def unpublished(paths: set[str]) -> set[str]:
    """The paths git will not publish, asked of git rather than listed here.

    The coordination layer (`docs/sessions/`, `docs/Process/`, and the rest) is
    excluded from the public repository, so a link into it would 404. Reading
    the exclusion from git keeps this correct when that list changes.
    """
    if not paths:
        return set()
    done = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "check-ignore", "--stdin"],
        input="\n".join(sorted(paths)),
        text=True,
        capture_output=True,
    )
    return {line.strip() for line in done.stdout.splitlines() if line.strip()}


def build(out_dir: Path) -> list[Path]:
    notes = note_index()
    ignored = unpublished(set(notes.values()))
    notes = {title: path for title, path in notes.items() if path not in ignored}
    pages = {path.stem: page_name(path.stem) for path in MANUAL_DIR.glob("*.md")}
    written: list[Path] = []

    home = ["# Transversal — the manuals", ""]
    home.append(
        "How to play and run **Transversal**, and how to author content into it. "
        "These pages are generated from the project's documentation vault — open a page "
        "and it reads the same as the notes the project works from."
    )
    home.append("")
    for title, blurb in INDEX:
        home.append(f"- **[{title}]({page_name(title)})** — {blurb}")
    home.append("")
    home.append(f"Source of truth: [`docs/Manual/`](https://github.com/{REPO}/tree/{BRANCH}/docs/Manual) in the repository.")
    (out_dir / "Home.md").write_text("\n".join(home) + "\n", encoding="utf-8")
    written.append(out_dir / "Home.md")

    sidebar = ["**[Home](Home)**", ""]
    for title, _ in INDEX:
        sidebar.append(f"- [{title}]({page_name(title)})")
    (out_dir / "_Sidebar.md").write_text("\n".join(sidebar) + "\n", encoding="utf-8")
    written.append(out_dir / "_Sidebar.md")

    for path in sorted(MANUAL_DIR.glob("*.md")):
        text = strip_frontmatter(path.read_text(encoding="utf-8"))
        text = convert_callouts(text)
        text = convert_links(text, pages, notes)
        text = re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"
        target = out_dir / f"{path.stem}.md"
        target.write_text(text, encoding="utf-8")
        written.append(target)
    return written


def git(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    # Keep the caller's environment: `gh auth git-credential` needs HOME to
    # reach the stored token. Only the interactive prompt is suppressed.
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    return subprocess.run(
        ["git", "-c", "credential.helper=!gh auth git-credential", *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        env=env,
    )


def wiki_exists() -> bool:
    probe = git("ls-remote", WIKI_URL, "HEAD")
    return probe.returncode == 0 and bool(probe.stdout.strip())


def push(pages: list[Path], generated: Path) -> int:
    if not wiki_exists():
        print(
            "The wiki repository does not exist yet — GitHub creates it only after a\n"
            "first page is saved in the browser. One click:\n\n"
            f"  1. open  https://github.com/{REPO}/wiki\n"
            "  2. press 'Create the first page', type anything, and Save\n\n"
            f"Then re-run:  python3 scripts/publish-wiki.py --push\n\n"
            f"(The pages are already generated in {generated} if you want to look first.)"
        )
        return 2

    with tempfile.TemporaryDirectory() as tmp:
        clone = Path(tmp) / "wiki"
        if git("clone", "--depth", "1", WIKI_URL, str(clone)).returncode != 0:
            print("Could not clone the wiki repository.", file=sys.stderr)
            return 1
        for existing in clone.glob("*.md"):
            existing.unlink()
        for page in pages:
            shutil.copy2(page, clone / page.name)
        git("add", "-A", cwd=clone)
        staged = git("diff", "--cached", "--quiet", cwd=clone)
        if staged.returncode == 0:
            print("The wiki is already up to date.")
            return 0
        message = "Publish the manuals from docs/Manual\n\nGenerated by scripts/publish-wiki.py."
        if git("-c", "user.name=Codewhale (DeepSeek-v4-PRO)",
               "-c", "user.email=codewhale@example.invalid",
               "commit", "-q", "-m", message, cwd=clone).returncode != 0:
            print("Could not commit the wiki pages.", file=sys.stderr)
            return 1
        if git("push", "origin", "HEAD", cwd=clone).returncode != 0:
            print("Could not push the wiki pages.", file=sys.stderr)
            return 1
    print(f"Published {len(pages)} pages to https://github.com/{REPO}/wiki")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=None, help="where to write the pages")
    parser.add_argument("--push", action="store_true", help="generate, then commit and push the wiki")
    args = parser.parse_args()

    generated = args.out or Path(tempfile.gettempdir()) / "transversal-wiki"
    generated.mkdir(parents=True, exist_ok=True)
    pages = build(generated)
    print(f"Generated {len(pages)} pages in {generated}")

    if args.push:
        return push(pages, generated)
    return 0


if __name__ == "__main__":
    sys.exit(main())
