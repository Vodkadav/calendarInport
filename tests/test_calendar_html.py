"""Tests for web/calendar.html — single-file friend-facing picker (slice 2.5).

These tests are written BEFORE the HTML — TDD red first.

Contract:
  - Single self-contained file: inline CSS + inline JS, no external assets.
  - Vanilla ES2020, no framework.
  - English-only UI strings (waived rule, see plan doc).
  - No hardcoded deploy host (must derive from location at runtime).
  - VTIMEZONE block must byte-match scripts/generate.py's VTIMEZONE_BLOCK so the
    browser-side ICS concatenator stays in sync with the server-side generator.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
HTML_PATH = ROOT / "web" / "calendar.html"
GENERATE_PY = ROOT / "scripts" / "generate.py"


def _read_html() -> str:
    return HTML_PATH.read_text(encoding="utf-8")


def _soup() -> BeautifulSoup:
    return BeautifulSoup(_read_html(), "html.parser")


def _script_text(soup: BeautifulSoup) -> str:
    return "\n".join(s.get_text() for s in soup.find_all("script"))


# ---------------------------------------------------------------------------
# 1. HTML parses
# ---------------------------------------------------------------------------


def test_html_parses() -> None:
    assert HTML_PATH.exists(), f"{HTML_PATH} missing"
    soup = BeautifulSoup(_read_html(), "html.parser")
    assert soup.find("html") is not None
    assert soup.find("body") is not None
    assert soup.find("head") is not None


# ---------------------------------------------------------------------------
# 2. No external <script src>
# ---------------------------------------------------------------------------


def test_no_external_script_src() -> None:
    soup = _soup()
    for s in soup.find_all("script"):
        src = s.get("src")
        if src is None:
            continue
        # Any src attribute on script is a smell for a self-contained file —
        # we deliberately have none.
        raise AssertionError(f"script src not allowed: {src!r}")


# ---------------------------------------------------------------------------
# 3. No external stylesheets
# ---------------------------------------------------------------------------


def test_no_external_stylesheets() -> None:
    soup = _soup()
    for link in soup.find_all("link"):
        rel = link.get("rel") or []
        if "stylesheet" in rel:
            href = link.get("href", "")
            raise AssertionError(f"external stylesheet not allowed: {href!r}")


# ---------------------------------------------------------------------------
# 4. No external fetches in JS
# ---------------------------------------------------------------------------


def test_no_external_fetches_in_js() -> None:
    soup = _soup()
    js = _script_text(soup)
    # No literal fetch('http... or fetch("http...
    assert not re.search(r"fetch\(\s*['\"]http", js), \
        "fetch() with absolute http(s) URL is forbidden"
    # No hardcoded deploy hostname anywhere in the script.
    assert "vodkadav.github.io" not in js
    assert "https://github.com" not in js


# ---------------------------------------------------------------------------
# 5. References ./data/merged.json AND ./data/teams.json
# ---------------------------------------------------------------------------


def test_references_merged_json_and_teams_json() -> None:
    js = _script_text(_soup())
    assert "./data/merged.json" in js
    assert "./data/teams.json" in js


# ---------------------------------------------------------------------------
# 6. References ics/{slug}.ics pattern
# ---------------------------------------------------------------------------


def test_references_ics_pattern() -> None:
    js = _script_text(_soup())
    assert "ics/" in js
    # Accept either template literal `ics/${slug}.ics` or `'ics/' + slug + '.ics'`.
    pattern_a = re.search(r"ics/\$\{[a-zA-Z_][a-zA-Z0-9_.]*\}\.ics", js)
    pattern_b = re.search(r"ics/['\"]\s*\+", js) or re.search(r"['\"]ics/['\"]\s*\+", js)
    assert pattern_a or pattern_b, "no ics/{slug}.ics interpolation found"


# ---------------------------------------------------------------------------
# 7. No emoji codepoints
# ---------------------------------------------------------------------------


def test_no_emoji() -> None:
    text = _read_html()
    for ch in text:
        cp = ord(ch)
        if 0x1F300 <= cp <= 0x1FAFF:
            raise AssertionError(f"emoji U+{cp:04X} found in file")
        if 0x2600 <= cp <= 0x27BF:
            raise AssertionError(f"emoji/dingbat U+{cp:04X} found in file")


# ---------------------------------------------------------------------------
# 8. No hardcoded deploy host
# ---------------------------------------------------------------------------


def test_no_hardcoded_deploy_host() -> None:
    text = _read_html()
    assert "vodkadav.github.io" not in text


# ---------------------------------------------------------------------------
# 9. File size under 200 KB
# ---------------------------------------------------------------------------


def test_file_size_under_200kb() -> None:
    size = os.path.getsize(HTML_PATH)
    assert size < 200 * 1024, f"calendar.html is {size} bytes (limit 200 KB)"


# ---------------------------------------------------------------------------
# 10. Two action buttons present (Download/Subscribe), stable IDs
# ---------------------------------------------------------------------------


def test_two_action_buttons_present() -> None:
    soup = _soup()
    # Stable IDs we assert against.
    dl = soup.find(id="download-selected")
    sub = soup.find(id="subscribe-selected")
    assert dl is not None, "missing #download-selected"
    assert sub is not None, "missing #subscribe-selected"
    assert re.search(r"download", dl.get_text(), re.I)
    assert re.search(r"subscribe", sub.get_text(), re.I)


# ---------------------------------------------------------------------------
# 11. Whole-tournament section present
# ---------------------------------------------------------------------------


def test_whole_tournament_section_present() -> None:
    soup = _soup()
    # Stable IDs for the whole-tournament pair.
    dl_all = soup.find(id="download-all")
    sub_all = soup.find(id="subscribe-all")
    assert dl_all is not None, "missing #download-all"
    assert sub_all is not None, "missing #subscribe-all"
    text = soup.get_text()
    assert "Whole tournament" in text or "104 matches" in text


# ---------------------------------------------------------------------------
# 12. No inline event handlers
# ---------------------------------------------------------------------------


def test_no_inline_event_handlers() -> None:
    soup = _soup()
    forbidden = ("onclick", "onload", "onerror", "onsubmit", "onchange",
                 "oninput", "onkeydown", "onkeyup", "onmouseover")
    for tag in soup.find_all(True):
        for attr in forbidden:
            assert attr not in tag.attrs, \
                f"inline handler {attr} on <{tag.name}>"


# ---------------------------------------------------------------------------
# 13. Only https:// or relative URLs in href/src
# ---------------------------------------------------------------------------


def test_only_https_or_relative_urls() -> None:
    soup = _soup()
    allowed_schemes = ("https://", "webcal://", "mailto:")
    for tag in soup.find_all(True):
        for attr in ("href", "src"):
            url = tag.get(attr)
            if url is None:
                continue
            url = url.strip()
            if not url:
                continue
            if url.startswith("#") or url.startswith("./") or url.startswith("/"):
                continue
            if "://" not in url and ":" not in url.split("/", 1)[0]:
                continue  # bare relative path like "data/teams.json"
            if any(url.startswith(s) for s in allowed_schemes):
                continue
            raise AssertionError(f"disallowed URL on <{tag.name} {attr}>: {url!r}")


# ---------------------------------------------------------------------------
# 14. VTIMEZONE block matches generate.py byte-for-byte
# ---------------------------------------------------------------------------


def _vtimezone_from_generate_py() -> str:
    """Import the constant; bytes-identical to what generate.py emits."""
    import sys
    repo = str(ROOT)
    if repo not in sys.path:
        sys.path.insert(0, repo)
    from scripts.generate import VTIMEZONE_BLOCK
    return VTIMEZONE_BLOCK


def _vtimezone_from_calendar_html() -> str:
    """Extract the VTIMEZONE block as it will appear in concatenated ICS output.

    calendar.html stores the block as a series of double-quoted JS string
    literals concatenated with `+`. Each literal already ends in `\\r\\n`.
    We pull every string fragment between `BEGIN:VTIMEZONE` and `END:VTIMEZONE`
    (inclusive of both markers) and concatenate them; then evaluate the
    `\\r\\n` escape sequences to real CR/LF bytes.
    """
    text = _read_html()
    # Find the VTIMEZONE_BLOCK constant region in the script.
    m = re.search(
        r'VTIMEZONE_BLOCK\s*=\s*((?:\s*"(?:[^"\\]|\\.)*"\s*\+?)+);',
        text,
    )
    assert m is not None, "VTIMEZONE_BLOCK constant not found in calendar.html"
    decl = m.group(1)
    # Pull every double-quoted string body out of the concatenation.
    parts = re.findall(r'"((?:[^"\\]|\\.)*)"', decl)
    raw = "".join(parts)
    # Evaluate JS escape sequences relevant to us: \r \n \\ \"
    # Map \r -> CR, \n -> LF, \\ -> \, \" -> ".
    out = []
    i = 0
    while i < len(raw):
        c = raw[i]
        if c == "\\" and i + 1 < len(raw):
            nxt = raw[i + 1]
            if nxt == "r":
                out.append("\r")
            elif nxt == "n":
                out.append("\n")
            elif nxt == "\\":
                out.append("\\")
            elif nxt == '"':
                out.append('"')
            else:
                out.append(nxt)
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def test_vtimezone_block_matches_generate_py() -> None:
    expected = _vtimezone_from_generate_py()
    actual = _vtimezone_from_calendar_html()
    assert actual == expected, (
        "VTIMEZONE block drift between generate.py and calendar.html — "
        "they must be byte-identical (after newline normalisation)."
    )


# ---------------------------------------------------------------------------
# 15. (extra) One <style> block and one <script> block
# ---------------------------------------------------------------------------


def test_single_style_and_script_block() -> None:
    soup = _soup()
    styles = soup.find_all("style")
    scripts = [s for s in soup.find_all("script") if s.get_text().strip()]
    assert len(styles) == 1, f"expected exactly 1 <style>, got {len(styles)}"
    assert len(scripts) == 1, f"expected exactly 1 inline <script>, got {len(scripts)}"


# ---------------------------------------------------------------------------
# 16. (extra) Page declares <meta charset="utf-8">
# ---------------------------------------------------------------------------


def test_utf8_charset_declared() -> None:
    soup = _soup()
    meta = soup.find("meta", attrs={"charset": True})
    assert meta is not None, "no <meta charset> declared"
    assert meta["charset"].lower() == "utf-8"


# ---------------------------------------------------------------------------
# Slice 2.9 — primary/secondary button hierarchy + inline captions
# ---------------------------------------------------------------------------


def test_subscribe_button_is_primary_download_is_secondary() -> None:
    """Subscribe must be the visually primary action; Download must be styled
    secondary. The cue is the `secondary` class on the Download button.
    The Subscribe button must NOT carry the `secondary` class.
    """
    soup = _soup()
    sub = soup.find(id="subscribe-selected")
    dl = soup.find(id="download-selected")
    assert sub is not None and dl is not None
    sub_class = " ".join(sub.get("class") or [])
    dl_class = " ".join(dl.get("class") or [])
    assert "secondary" in dl_class, (
        f"#download-selected must use the 'secondary' class; got class={dl_class!r}"
    )
    assert "secondary" not in sub_class, (
        f"#subscribe-selected must be primary (no 'secondary' class); "
        f"got class={sub_class!r}"
    )


def test_subscribe_caption_present() -> None:
    """Inline caption under Subscribe explains the toggleable / account-only
    property. Asserts a stable substring of the locked copy."""
    text = _read_html()
    assert "stays on your account" in text.lower(), (
        "missing Subscribe caption substring 'stays on your account'"
    )
    assert (
        "toggle on/off" in text.lower()
        or "toggle on / off" in text.lower()
        or "toggleable" in text.lower()
    ), "missing Subscribe caption substring about toggling"


def test_download_caption_present() -> None:
    """Inline caption under Download warns about the shared-primary-calendar
    propagation risk and the lack of auto-update."""
    text = _read_html()
    lower = text.lower()
    assert "shared" in lower, "missing Download caption mention of 'shared'"
    assert (
        "does not auto-update" in lower
        or "does not update" in lower
        or "no auto-update" in lower
        or "not auto-update" in lower
    ), "missing Download caption warning about no auto-update"


def test_subscribe_caption_id_stable() -> None:
    """The inline captions must live in elements with stable IDs so future
    edits don't accidentally remove them. IDs: #subscribe-selected-caption
    and #download-selected-caption."""
    soup = _soup()
    assert soup.find(id="subscribe-selected-caption") is not None, (
        "missing #subscribe-selected-caption"
    )
    assert soup.find(id="download-selected-caption") is not None, (
        "missing #download-selected-caption"
    )


# ---------------------------------------------------------------------------
# Favourites preset card (curated one-click combined subscription)
# ---------------------------------------------------------------------------


FAVOURITE_TEAM_NAMES = [
    "Mexico", "England", "Canada", "USA", "Spain", "Germany",
    "France", "Brazil", "Belgium", "Argentina", "Portugal",
]


def test_favourites_card_has_stable_action_ids() -> None:
    """The Favourites card exposes #subscribe-favourites and
    #download-favourites — stable IDs so JS + future tests can reach
    them without DOM-traversal fragility."""
    soup = _soup()
    assert soup.find(id="subscribe-favourites") is not None, (
        "missing #subscribe-favourites"
    )
    assert soup.find(id="download-favourites") is not None, (
        "missing #download-favourites"
    )


def test_favourites_card_lists_all_11_team_names() -> None:
    """The card's visible text must include every team in the preset so
    a friend can verify the contents before subscribing."""
    text = _read_html()
    for team in FAVOURITE_TEAM_NAMES:
        assert team in text, (
            f"Favourites card missing team name: {team!r}"
        )


def test_favourites_card_references_favourites_ics() -> None:
    """The subscribe + download paths must point at ics/favourites.ics
    (either as a literal href or as a JS interpolation argument)."""
    text = _read_html()
    assert "favourites.ics" in text, (
        "calendar.html does not reference 'favourites.ics' anywhere"
    )
