"""Tests for README.md — friend quickstart + maintainer notes (slice 2.8).

These tests are written BEFORE the README rewrite — TDD red first.

Contract:
  - Single canonical README at repo root.
  - Two audiences in one file: friends (top), maintainers (bottom).
  - English-only (i18n waived for this project).
  - Self-contained: no external images / badges.
  - No emojis anywhere (same codepoint scan as slice 2.5).
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README_PATH = ROOT / "README.md"

REQUIRED_H1 = "# FIFA 2026 World Cup — calendar import"

REQUIRED_H2_ORDER = [
    "## How to use it",
    "## What you get",
    "## Knockout stage",
    "## Privacy",
    "## For maintainers",
    "## Credits & data sources",
    "## License",
]

PICKER_URL = "https://vodkadav.github.io/calendarInport/"


def _read() -> str:
    return README_PATH.read_text(encoding="utf-8")


def _lines() -> list[str]:
    return _read().splitlines()


def _section_text(body: str, heading: str, level: int = 2) -> str:
    """Return the text between `heading` and the next heading of same-or-shallower depth."""
    prefix = "#" * level + " "
    lines = body.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.strip() == heading.strip():
            start = i + 1
            break
    if start is None:
        return ""
    end = len(lines)
    for j in range(start, len(lines)):
        stripped = lines[j].lstrip("#")
        depth = len(lines[j]) - len(stripped)
        if 1 <= depth <= level and lines[j].startswith(prefix[:depth] + " ") is False:
            if lines[j].startswith("#") and depth <= level and lines[j] != heading:
                end = j
                break
        if lines[j].startswith("#") and lines[j] != heading:
            hd = len(lines[j]) - len(lines[j].lstrip("#"))
            if 1 <= hd <= level:
                end = j
                break
    return "\n".join(lines[start:end])


# ---------------------------------------------------------------------------
# 1. File exists and is non-empty
# ---------------------------------------------------------------------------


def test_readme_exists() -> None:
    assert README_PATH.exists(), f"{README_PATH} missing"
    body = _read()
    assert body.strip(), "README.md is empty"
    assert len(body) > 500, f"README.md suspiciously short ({len(body)} bytes)"


# ---------------------------------------------------------------------------
# 2. Required top-level headings present in order
# ---------------------------------------------------------------------------


def test_required_top_level_headings_present_in_order() -> None:
    body = _read()
    # H1 must be first non-blank line (allowing for it to appear early).
    assert REQUIRED_H1 in body, f"missing H1: {REQUIRED_H1!r}"

    expected = [REQUIRED_H1] + REQUIRED_H2_ORDER
    positions = []
    for heading in expected:
        idx = body.find(heading)
        assert idx >= 0, f"heading not found: {heading!r}"
        positions.append((heading, idx))
    sorted_positions = sorted(positions, key=lambda p: p[1])
    assert positions == sorted_positions, (
        "headings out of order; expected "
        f"{[h for h,_ in positions]}, actual "
        f"{[h for h,_ in sorted_positions]}"
    )


# ---------------------------------------------------------------------------
# 3. Picker URL is prominent (within first 40 lines)
# ---------------------------------------------------------------------------


def test_picker_url_prominent() -> None:
    head = "\n".join(_lines()[:40])
    assert PICKER_URL in head, (
        f"picker URL {PICKER_URL!r} not found in first 40 lines"
    )


# ---------------------------------------------------------------------------
# 4. Maintainers section exists
# ---------------------------------------------------------------------------


def test_for_maintainers_section_exists() -> None:
    body = _read()
    assert "## For maintainers" in body


# ---------------------------------------------------------------------------
# 5. Architecture diagram present inside maintainers section
# ---------------------------------------------------------------------------


def test_architecture_diagram_present() -> None:
    body = _read()
    arch_idx = body.find("### Architecture")
    assert arch_idx >= 0, "missing '### Architecture' subheading"
    # find the next H3 or H2 after Architecture
    after = body[arch_idx + len("### Architecture"):]
    next_h = re.search(r"^(##\s|###\s)", after, re.MULTILINE)
    section = after[: next_h.start()] if next_h else after
    # must contain a fenced code block
    fence_match = re.search(r"```[\s\S]*?```", section)
    assert fence_match, "Architecture section has no fenced code block"
    diagram = fence_match.group(0)
    assert "refresh.py" in diagram, "architecture diagram missing 'refresh.py'"
    assert "gh-pages" in diagram, "architecture diagram missing 'gh-pages'"


# ---------------------------------------------------------------------------
# 6. Privacy section mentions no tracking / no analytics
# ---------------------------------------------------------------------------


def test_privacy_section_mentions_no_tracking() -> None:
    body = _read()
    priv_idx = body.find("## Privacy")
    assert priv_idx >= 0
    after = body[priv_idx:]
    next_h2 = re.search(r"^##\s", after[len("## Privacy"):], re.MULTILINE)
    section = after[: next_h2.start() + len("## Privacy")] if next_h2 else after
    lower = section.lower()
    assert "tracking" in lower or "analytics" in lower, (
        "Privacy section must mention 'tracking' or 'analytics'"
    )


# ---------------------------------------------------------------------------
# 7. Credits links to openfootball and baires
# ---------------------------------------------------------------------------


def test_credits_links_to_openfootball_and_baires() -> None:
    body = _read()
    cred_idx = body.find("## Credits & data sources")
    assert cred_idx >= 0
    after = body[cred_idx:]
    next_h2 = re.search(r"^##\s", after[len("## Credits & data sources"):], re.MULTILINE)
    section = (
        after[: next_h2.start() + len("## Credits & data sources")]
        if next_h2
        else after
    )
    assert "openfootball/worldcup.json" in section, (
        "credits must link to openfootball/worldcup.json"
    )
    assert "baires/fifa-cal-2026" in section, (
        "credits must link to baires/fifa-cal-2026"
    )


# ---------------------------------------------------------------------------
# 8. License section names MIT
# ---------------------------------------------------------------------------


def test_license_is_mit() -> None:
    body = _read()
    lic_idx = body.find("## License")
    assert lic_idx >= 0
    section = body[lic_idx:]
    assert "MIT" in section, "License section must name MIT"


# ---------------------------------------------------------------------------
# 9. TV2 fair-use disclaimer present
# ---------------------------------------------------------------------------


def test_tv2_fair_use_disclaimer_present() -> None:
    body = _read()
    lower = body.lower()
    has_ophavsret = "ophavsretsloven" in lower
    has_fair_use = "fair use" in lower or "fair-use" in lower
    has_tv2 = "tv 2" in lower or "tv2" in lower
    assert has_ophavsret or (has_fair_use and has_tv2), (
        "README must document the TV 2 fair-use posture "
        "(either 'ophavsretsloven' or both 'fair use'+'TV 2')"
    )


# ---------------------------------------------------------------------------
# 10. Internal anchor links resolve
# ---------------------------------------------------------------------------


def _slugify(heading: str) -> str:
    """GitHub-flavored heading-to-anchor slug approximation."""
    s = heading.strip().lstrip("#").strip().lower()
    s = s.replace(" ", "-")
    s = re.sub(r"[^a-z0-9-]", "", s)
    return s


def test_no_broken_internal_anchor_links() -> None:
    body = _read()
    headings = re.findall(r"^#{1,6}\s+(.+?)\s*$", body, re.MULTILINE)
    slugs = {_slugify(h) for h in headings}

    # Find every [...](#anchor)
    for match in re.finditer(r"\[[^\]]+\]\(#([^)]+)\)", body):
        target = match.group(1).lower()
        assert target in slugs, (
            f"internal anchor #{target} has no matching heading; "
            f"available slugs: {sorted(slugs)}"
        )


# ---------------------------------------------------------------------------
# 11. No external image / badge URLs
# ---------------------------------------------------------------------------


def test_no_external_image_or_badge_urls() -> None:
    body = _read()
    # ![alt](http...) — markdown image with http(s) URL
    bad = re.findall(r"!\[[^\]]*\]\(https?://[^)]+\)", body)
    assert not bad, f"external image/badge URLs not allowed: {bad}"


# ---------------------------------------------------------------------------
# 12. No emoji (same scan as slice 2.5)
# ---------------------------------------------------------------------------


def test_no_emoji() -> None:
    text = _read()
    for ch in text:
        cp = ord(ch)
        if 0x1F300 <= cp <= 0x1FAFF:
            raise AssertionError(f"emoji U+{cp:04X} found in file")
        if 0x2600 <= cp <= 0x27BF:
            raise AssertionError(f"emoji/dingbat U+{cp:04X} found in file")


# ---------------------------------------------------------------------------
# 13. Subscribe section documents both Google and iPhone/iOS
# ---------------------------------------------------------------------------


def test_subscribe_section_documents_both_google_and_iphone() -> None:
    body = _read()
    sub_idx = body.find("### Subscribe")
    assert sub_idx >= 0, "missing '### Subscribe' subheading"
    after = body[sub_idx:]
    # cut at the next H3 or H2
    next_h = re.search(r"^(##\s|###\s)", after[len("### Subscribe"):], re.MULTILINE)
    section = after[: next_h.start() + len("### Subscribe")] if next_h else after
    lower = section.lower()
    assert "google" in lower, "Subscribe section must mention Google"
    assert "iphone" in lower or "ios" in lower, (
        "Subscribe section must mention iPhone or iOS"
    )


# ---------------------------------------------------------------------------
# Extra safety nets (beyond the 13 required)
# ---------------------------------------------------------------------------


def test_download_section_has_caveat_about_no_autoupdate() -> None:
    """Download mode must warn users it does NOT auto-update — otherwise the
    knockout-stage UX will silently break for them."""
    body = _read()
    dl_idx = body.find("### Download")
    assert dl_idx >= 0
    after = body[dl_idx:]
    next_h = re.search(r"^(##\s|###\s)", after[len("### Download"):], re.MULTILINE)
    section = after[: next_h.start() + len("### Download")] if next_h else after
    lower = section.lower()
    # must mention auto-update / subscribe in some warning capacity
    has_warning = (
        "auto-update" in lower
        or "auto update" in lower
        or "not update" in lower
        or "does not update" in lower
        or "freeze" in lower
        or "subscribe instead" in lower
    )
    assert has_warning, (
        "Download section must warn that the file does not auto-update"
    )


def test_length_within_budget() -> None:
    n = len(_lines())
    assert 120 <= n <= 350, f"README length {n} lines outside 120-350 budget"


def test_no_external_image_html_tag() -> None:
    """Also block raw <img src='http...'> just in case markdown sneaks one in
    via inline HTML."""
    body = _read()
    assert not re.search(r"<img\s+[^>]*src\s*=\s*['\"]https?://", body, re.IGNORECASE)
