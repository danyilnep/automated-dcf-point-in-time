"""Checks of analysis/check_docs.py on a small synthetic repository."""

from analysis.check_docs import check, slug

PLACEHOLDER = "REPLACE" + "_ME"


def test_heading_anchors_follow_github():
    assert slug("The cap probe's log") == "the-cap-probes-log"
    assert slug("1. Inverted, overlapping trading bands") == "1-inverted-overlapping-trading-bands"
    assert slug("Why `market_cap` [lags](x.md)") == "why-market_cap-lags"


def test_links_images_anchors_and_placeholders(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "code.py").write_text("a = 1\nb = 2\n", encoding="utf-8")
    (tmp_path / "docs" / "guide.md").write_text(
        "# Guide\n\n## The cap probe's log\n\nText.\n", encoding="utf-8")
    (tmp_path / "README.md").write_text(
        "\n".join([
            "[ok](docs/guide.md#the-cap-probes-log) [lines](code.py#L1-L2) [web](https://x.org)",
            "<!-- ![not yet](docs/missing.png) -->",
            "```markdown",
            "![inside a code block](docs/also-missing.png)",
            "```",
            "`[inline](nowhere.md)`",
            "[bad anchor](docs/guide.md#nope)",
            "![broken](docs/missing.png)",
            "[too far](code.py#L9)",
            "[wrong case](DOCS/guide.md)",
            f"Draft {PLACEHOLDER} left here.",
        ]),
        encoding="utf-8")
    problems, counts = check(tmp_path)
    assert problems == [
        "README.md:11: placeholder token",
        "README.md:7: docs/guide.md#nope: no heading #nope",
        "README.md:8: docs/missing.png: no such file or folder (paths are case-sensitive on GitHub)",
        "README.md:9: code.py#L9: lines #L9 beyond 2",
        "README.md:10: DOCS/guide.md: no such file or folder (paths are case-sensitive on GitHub)",
    ]
    assert counts["markdown"] == 2
