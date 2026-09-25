"""Check the repository's Markdown: relative links and images resolve, and no placeholder is left.

    python analysis/check_docs.py

For every .md file outside .git, virtual environments and caches:

- HTML comments are removed before anything is checked, so a commented-out image line (the
  screenshot slots in README.md) is skipped. Fenced code blocks and inline code are skipped too.
- Every Markdown link or image target, reference definition, and src or href of an HTML tag
  that is not an absolute URL must name a file or folder inside the repository, with the exact
  letter case (GitHub's paths are case-sensitive, Windows' are not).
- A #fragment pointing into a Markdown file must match one of its headings as GitHub turns
  them into anchors. A #L12 or #L12-L20 fragment pointing into any other file must lie within
  its line count.

Every text file (Markdown, code, configuration, data) is also searched for the placeholder
prefix used while drafting: the word REPLACE in capitals directly followed by an underscore.

Exits with status 1 and lists every problem, or prints a one-line summary.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from urllib.parse import unquote

REPO = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", ".venv", "venv", "env", "__pycache__", ".pytest_cache", ".ruff_cache",
             "node_modules"}
TEXT_SUFFIXES = {".md", ".py", ".yml", ".yaml", ".toml", ".txt", ".json", ".cfg", ".ini",
                 ".csv", ".html", ".log", ".gitattributes", ".gitignore"}
TEXT_NAMES = {"LICENSE", ".gitattributes", ".gitignore"}
PLACEHOLDER = re.compile("REPLACE" + "_")  # built here so this file does not match itself

FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
INLINE_CODE = re.compile(r"(`+)(?:(?!\1).)+?\1")
INLINE_TARGET = re.compile(r"\]\(\s*(<[^>]*>|[^)\s]+)(?:\s+\"[^\"]*\")?\s*\)")
REFERENCE = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*(<[^>]*>|\S+)")
HTML_ATTR = re.compile(r"<[a-zA-Z][^>]*?\b(?:src|href)\s*=\s*[\"']([^\"']+)[\"']")
HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
LINE_FRAGMENT = re.compile(r"^L(\d+)(?:-L(\d+))?$")
SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")


def walk(root: Path):
    """Every file under root, skipping SKIP_DIRS, in a stable order."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(filenames):
            yield Path(dirpath) / name


def blank_code_blocks(text: str) -> str:
    """Replace the lines of fenced code blocks with empty lines (line numbers are kept)."""
    out, fence = [], None
    for line in text.split("\n"):
        match = FENCE.match(line)
        if fence is None and match:
            fence = match.group(1)[0] * 3
            out.append("")
        elif fence is not None:
            if line.strip().startswith(fence):
                fence = None
            out.append("")
        else:
            out.append(line)
    return "\n".join(out)


def strip_markup(text: str) -> str:
    """The text with code blocks, HTML comments and inline code removed, same line count."""
    text = blank_code_blocks(text)
    text = COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), text)
    return INLINE_CODE.sub("", text)


def slug(heading: str) -> str:
    """GitHub's anchor for a heading: links reduced to their text, inline code and HTML tags
    unwrapped, lower case, punctuation other than hyphens and underscores removed, spaces to
    hyphens."""
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", heading)
    text = re.sub(r"<[^>]+>", "", text).replace("`", "")
    text = re.sub(r"[^\w\- ]", "", text.strip().lower())
    return text.replace(" ", "-")


def anchors(text: str) -> set[str]:
    """Every heading anchor in a Markdown text, with GitHub's -1, -2 suffixes for repeats."""
    seen: dict[str, int] = {}
    result = set()
    for line in blank_code_blocks(COMMENT.sub("", text)).split("\n"):
        match = HEADING.match(line)
        if not match:
            continue
        base = slug(match.group(2))
        count = seen.get(base, 0)
        result.add(base if count == 0 else f"{base}-{count}")
        seen[base] = count + 1
    return result


def exact_case_exists(root: Path, rel_parts: list[str]) -> bool:
    """True when every part of the path exists with exactly this spelling."""
    current = root
    for part in rel_parts:
        if not current.is_dir() or part not in os.listdir(current):
            return False
        current = current / part
    return True


def targets(text: str) -> list[tuple[int, str]]:
    """(line number, target) for every link, image, reference and HTML src or href."""
    found = []
    for number, line in enumerate(strip_markup(text).split("\n"), start=1):
        for pattern in (INLINE_TARGET, HTML_ATTR):
            found += [(number, m.group(1)) for m in pattern.finditer(line)]
        match = REFERENCE.match(line)
        if match:
            found.append((number, match.group(1)))
    return [(n, t[1:-1] if t.startswith("<") and t.endswith(">") else t) for n, t in found]


def check_target(root: Path, source: Path, target: str, cache: dict[Path, str]) -> str | None:
    """None when the target resolves, else the reason it does not."""
    if SCHEME.match(target) or target.startswith("//"):
        return None
    path_part, _, fragment = target.partition("#")
    path_part = unquote(path_part.split("?", 1)[0])
    if path_part:
        base = root if path_part.startswith("/") else source.parent
        resolved = Path(os.path.normpath(base / path_part.lstrip("/")))
    else:
        resolved = source
    try:
        rel = resolved.relative_to(root)
    except ValueError:
        return "points outside the repository"
    if not exact_case_exists(root, list(rel.parts)):
        return "no such file or folder (paths are case-sensitive on GitHub)"
    if not fragment:
        return None
    if resolved.is_dir():
        return "a #fragment on a folder"
    if resolved not in cache:
        cache[resolved] = resolved.read_text(encoding="utf-8", errors="replace")
    content = cache[resolved]
    if resolved.suffix.lower() == ".md":
        return None if unquote(fragment).lower() in anchors(content) else f"no heading #{fragment}"
    lines = LINE_FRAGMENT.match(fragment)
    if lines:
        last = int(lines.group(2) or lines.group(1))
        count = len(content.splitlines())
        return None if 1 <= int(lines.group(1)) <= last <= count else f"lines #{fragment} beyond {count}"
    return f"cannot check #{fragment} in a non-Markdown file"


def is_text(path: Path) -> bool:
    return path.suffix.lower() in TEXT_SUFFIXES or path.name in TEXT_NAMES


def check(root: Path) -> tuple[list[str], dict[str, int]]:
    """All problems under root, and counts of what was checked."""
    problems: list[str] = []
    counts = {"markdown": 0, "targets": 0, "text": 0}
    cache: dict[Path, str] = {}
    for path in walk(root):
        rel = path.relative_to(root).as_posix()
        if not is_text(path):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        counts["text"] += 1
        for number, line in enumerate(text.split("\n"), start=1):
            if PLACEHOLDER.search(line):
                problems.append(f"{rel}:{number}: placeholder token")
        if path.suffix.lower() != ".md":
            continue
        counts["markdown"] += 1
        cache[path] = text
        for number, target in targets(text):
            counts["targets"] += 1
            reason = check_target(root, path, target, cache)
            if reason:
                problems.append(f"{rel}:{number}: {target}: {reason}")
    return problems, counts


def main() -> int:
    problems, counts = check(REPO)
    if problems:
        print("Documentation problems:")
        for problem in problems:
            print(f"  {problem}")
        return 1
    print(f"OK: {counts['targets']} links and images in {counts['markdown']} Markdown files "
          f"resolve; no placeholder token in {counts['text']} text files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
