"""Fetch and merge FIFA 2026 fixtures + Danish broadcaster info.

Pipeline:
  1. fetch openfootball/worldcup.json (104-match templated fixture skeleton, CC0)
  2. scrape sport.tv2.dk/fodbold/vm/sendeplan (Danish broadcaster + Danish kickoff)
  3. merge into data/merged.json

Run:
  python scripts/refresh.py             # live fetch + write data/merged.json
  python scripts/refresh.py --dry-run   # use tests/fixtures instead (no network)

openfootball schema (verified live 2026-05-23):
  {name, matches:[{round, num?, date, time, team1, team2, group?, ground}, ...]}
  - time: "HH:MM UTC±N" (UTC offset embedded; venue tz used only as fallback)
  - ground: city/metro string (not stadium name); see scripts/venues.py
  - group: "Group A".."Group L" on group-stage matches; absent on knockout
  - num: present for most matches; absent for some knockout slots — id is
    derived chronologically post-sort to remain stable across rebuilds.

Tests live in tests/test_refresh.py — see them for the contract.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover — Python < 3.9
    from backports.zoneinfo import ZoneInfo  # type: ignore[no-redef]

# Allow `python scripts/refresh.py` to import the sibling modules.
_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR.parent) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR.parent))

from scripts.team_names import DA_TO_EN, da_to_en, en_to_da  # noqa: E402
from scripts.venues import lookup as venue_lookup  # noqa: E402

log = logging.getLogger("refresh")

OPENFOOTBALL_URL = (
    "https://raw.githubusercontent.com/openfootball/worldcup.json/master/2026/worldcup.json"
)
TV2_URL = "https://sport.tv2.dk/fodbold/vm/sendeplan"

COPENHAGEN = ZoneInfo("Europe/Copenhagen")

# openfootball templated-team token grammar (verified live 2026-05-23):
#   W101, L102        → match-result placeholders (Winner/Loser of match N)
#   1A, 2C            → group-position placeholders (Winner/Runner-up of Group X)
#   3A/B/C/D/F        → composite third-place placeholder
TOKEN_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^[WL]\d{1,3}$"),
    re.compile(r"^[12][A-L]$"),
    re.compile(r"^3[A-L](?:/[A-L])*$"),
]

TIME_WITH_OFFSET_RE = re.compile(r"^(\d{1,2}:\d{2})(?:\s+UTC([+-]?\d+))?$")


# ---------------------------------------------------------------------------
# Stage inference
# ---------------------------------------------------------------------------

def stage_from_round(round_name: str) -> str:
    """Map an openfootball round string to: group | r32 | r16 | qf | sf | 3rd | final."""
    n = round_name.lower()
    if "matchday" in n or n.startswith("group"):
        return "group"
    if "round of 32" in n or "r32" in n:
        return "r32"
    if "round of 16" in n or "r16" in n:
        return "r16"
    if "quarter" in n:
        return "qf"
    if "semi" in n:
        return "sf"
    if "third" in n or "3rd" in n:
        return "3rd"
    if "final" in n:
        return "final"
    return "group"  # safe default


# ---------------------------------------------------------------------------
# Token detection + rendering
# ---------------------------------------------------------------------------

def _is_token(name: str | None) -> bool:
    if not name:
        return False
    return any(p.match(name) for p in TOKEN_PATTERNS)


def render_token(token: str) -> str:
    """Render a placeholder token into a readable phrase.

    Examples:
        "W101"        → "Winner of match 101"
        "L102"        → "Loser of match 102"
        "1A"          → "Winner Group A"
        "2C"          → "Runner-up Group C"
        "3A/B/C/D/F"  → "Third place A/B/C/D/F"
    Unknown shapes round-trip unchanged.
    """
    m = re.match(r"^([WL])(\d{1,3})$", token)
    if m:
        side = "Winner" if m.group(1) == "W" else "Loser"
        return f"{side} of match {m.group(2)}"
    m = re.match(r"^([12])([A-L])$", token)
    if m:
        side = "Winner" if m.group(1) == "1" else "Runner-up"
        return f"{side} Group {m.group(2)}"
    m = re.match(r"^3([A-L](?:/[A-L])*)$", token)
    if m:
        return f"Third place {m.group(1)}"
    return token


# ---------------------------------------------------------------------------
# Kickoff conversion
# ---------------------------------------------------------------------------

def _convert_kickoff(
    date_str: str, time_str: str, fallback_tz_name: str | None
) -> tuple[str, str]:
    """Return (kickoff_local_copenhagen_naive_iso, kickoff_utc_iso_z).

    openfootball's `time` field carries an embedded UTC offset (e.g. `13:00 UTC-6`).
    The offset is the primary source of truth. If the offset is absent we fall
    back to the venue's IANA tz; if that's also missing we treat the time as UTC
    and emit a WARNING.
    """
    m = TIME_WITH_OFFSET_RE.match(time_str.strip())
    if not m:
        raise ValueError(f"unparseable openfootball time string: {time_str!r}")
    hhmm = m.group(1)
    offset_str = m.group(2)

    naive = datetime.fromisoformat(f"{date_str}T{hhmm}:00")
    if offset_str is not None:
        source_tz: timezone | ZoneInfo = timezone(timedelta(hours=int(offset_str)))
    elif fallback_tz_name:
        log.warning("no UTC offset on time %r; falling back to venue tz %s",
                    time_str, fallback_tz_name)
        source_tz = ZoneInfo(fallback_tz_name)
    else:
        log.warning("no offset and no fallback tz; treating %r as UTC", time_str)
        source_tz = timezone.utc

    at_venue = naive.replace(tzinfo=source_tz)
    utc = at_venue.astimezone(timezone.utc)
    cph = at_venue.astimezone(COPENHAGEN)
    return (
        cph.replace(tzinfo=None).isoformat(timespec="seconds"),
        utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


# ---------------------------------------------------------------------------
# Single-record translation
# ---------------------------------------------------------------------------

def openfootball_to_match(of_match: dict[str, Any], round_name: str) -> dict[str, Any]:
    """Translate one openfootball match record into the merged-schema record.

    The `id` field is left as 0 here; final ids are assigned chronologically by
    build_merged() once all records are collected and sorted.
    """
    stage = stage_from_round(round_name)
    ground = of_match.get("ground")
    vinfo = venue_lookup(ground)
    if ground and vinfo["stadium"] is None:
        log.warning("unmapped ground %r — venue fields will be null", ground)

    raw_t1 = of_match.get("team1")
    raw_t2 = of_match.get("team2")
    t1_is_token = _is_token(raw_t1)
    t2_is_token = _is_token(raw_t2)

    team1 = None if t1_is_token else raw_t1
    team2 = None if t2_is_token else raw_t2
    token1 = raw_t1 if t1_is_token else None
    token2 = raw_t2 if t2_is_token else None

    team1_da = en_to_da(team1) if team1 else None
    team2_da = en_to_da(team2) if team2 else None

    kickoff_local, kickoff_utc = _convert_kickoff(
        of_match["date"], of_match["time"], vinfo["tz"]
    )

    group = of_match.get("group")
    if group and group.startswith("Group "):
        group = group[len("Group "):]
    if stage != "group":
        group = None

    record: dict[str, Any] = {
        "id": 0,  # assigned post-sort by build_merged
        "stage": stage,
        "round_label": round_name,
        "group": group,
        "date": of_match["date"],
        "kickoff_local": kickoff_local,
        "kickoff_utc": kickoff_utc,
        "team1": team1,
        "team2": team2,
        "team1_token": token1,
        "team2_token": token2,
        "team1_da": team1_da,
        "team2_da": team2_da,
        "venue": vinfo["stadium"],
        "city": vinfo["city"],
        "country": vinfo["country"],
        "ground_raw": ground,
        "channels_da": [],
    }
    return record


# ---------------------------------------------------------------------------
# TV2 sendeplan HTML scrape
# ---------------------------------------------------------------------------

# Map TV2 logo filename / alt-text fragments to a canonical Danish channel label.
_CHANNEL_MARKERS: list[tuple[str, str]] = [
    ("tv2_sport_x", "TV 2 Sport X"),
    ("tv2-sport-x", "TV 2 Sport X"),
    ("tv2_sport", "TV 2 Sport"),
    ("tv2-sport", "TV 2 Sport"),
    ("tv2", "TV 2"),
    ("dr1", "DR1"),
    ("dr2", "DR2"),
    ("dr_k", "DR K"),
    ("dr_ramasjang", "DR Ramasjang"),
]


def _classify_logo(src: str, alt: str) -> str | None:
    # Match the filename + alt text only, not the full URL — the TV2 CDN host
    # ("coreui.tv2a.dk") itself contains "tv2" and would misclassify DR logos.
    filename = src.rsplit("/", 1)[-1].lower() if src else ""
    haystack = f"{filename} {alt.lower()}"
    for marker, label in _CHANNEL_MARKERS:
        if marker in haystack:
            return label
    return None


def parse_tv2_html(html: str) -> list[dict[str, Any]]:
    """Parse TV2 sendeplan HTML into broadcaster entries.

    Each entry:
        {date: YYYY-MM-DD, kickoff_local: ISO no tz, team1_da, team2_da, channels_da: list}
    """
    from bs4 import BeautifulSoup  # local import keeps module import light

    soup = BeautifulSoup(html, "html.parser")
    entries: list[dict[str, Any]] = []

    for art in soup.select("article"):
        time_el = art.find("time")
        if not time_el or not time_el.get("datetime"):
            continue
        dt_attr = time_el["datetime"]
        # TV2 uses two shapes inconsistently: naive Copenhagen-local
        # ("2026-06-11T21:00") and explicit UTC ("2026-06-13T22:00:00.000Z").
        # Normalise the `Z` suffix for fromisoformat (Python 3.10-) then
        # convert any tz-aware value into Copenhagen-local before reading the
        # calendar date — otherwise late-evening US matches read as the prior
        # UTC day instead of the day they air in Denmark.
        if dt_attr.endswith("Z"):
            dt_attr = dt_attr[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(dt_attr)
        except ValueError:
            continue
        if dt.tzinfo is not None:
            dt = dt.astimezone(COPENHAGEN).replace(tzinfo=None)
        date_str = dt.date().isoformat()
        kickoff_local = dt.replace(second=0).isoformat(timespec="seconds")

        heading_el = art.find(["h1", "h2", "h3", "h4", "heading"])
        if not heading_el:
            continue
        heading = heading_el.get_text(strip=True)
        # Require whitespace around the dash so internal-hyphen team names
        # (e.g. "Saudi-Arabien", "Bosnien-Hercegovina") parse correctly.
        m = re.search(r"FIFA\s+VM\s*:\s*(.+?)\s+-\s+(.+)", heading)
        if not m:
            continue
        team1_da = m.group(1).strip()
        team2_da = m.group(2).strip()
        team2_da = re.sub(r",\s*Gruppe\s+\w+\s*$", "", team2_da).strip()

        channels: list[str] = []
        seen: set[str] = set()
        for img in art.find_all("img"):
            label = _classify_logo(img.get("src", ""), img.get("alt", ""))
            if label and label not in seen:
                channels.append(label)
                seen.add(label)

        entries.append({
            "date": date_str,
            "kickoff_local": kickoff_local,
            "team1_da": team1_da,
            "team2_da": team2_da,
            "channels_da": channels,
        })
    return entries


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------

def _norm_pair(a: str | None, b: str | None) -> frozenset[str]:
    return frozenset(x for x in (a, b) if x)


def _assign_chronological_ids(matches: list[dict[str, Any]]) -> None:
    """Sort matches by (date, kickoff_utc, ground_raw) and assign 1..N ids."""
    matches.sort(key=lambda m: (m["date"], m["kickoff_utc"], m["ground_raw"] or ""))
    for idx, m in enumerate(matches, 1):
        m["id"] = idx


def build_merged(
    of_json: dict[str, Any],
    tv2_html: str,
    *,
    generated_at: str,
    fetched_at: str,
) -> dict[str, Any]:
    """Build the full merged document from raw openfootball JSON + TV2 HTML."""
    matches: list[dict[str, Any]] = []
    for m in of_json.get("matches", []):
        round_name = m.get("round", "")
        matches.append(openfootball_to_match(m, round_name))

    _assign_chronological_ids(matches)

    tv2_entries = parse_tv2_html(tv2_html)

    # Index TV2 entries by (date, normalised DA-team-pair) AND by EN-team-pair.
    by_da_pair: dict[tuple[str, frozenset[str]], dict[str, Any]] = {}
    by_en_pair: dict[tuple[str, frozenset[str]], dict[str, Any]] = {}
    unmapped: list[str] = []
    for e in tv2_entries:
        da_pair = _norm_pair(e["team1_da"], e["team2_da"])
        by_da_pair[(e["date"], da_pair)] = e
        en1 = da_to_en(e["team1_da"])
        en2 = da_to_en(e["team2_da"])
        if en1 and en2:
            by_en_pair[(e["date"], _norm_pair(en1, en2))] = e
        else:
            for name, mapped in ((e["team1_da"], en1), (e["team2_da"], en2)):
                if mapped is None and name not in unmapped:
                    unmapped.append(name)

    for n in unmapped:
        log.warning("TV2 team name not in DA_TO_EN map; channels_da will be empty: %s", n)

    for rec in matches:
        if rec["team1"] is None or rec["team2"] is None:
            continue  # knockout placeholder — no TV2 entry to merge yet
        # TV2 publishes Copenhagen-local dates; openfootball's `date` is
        # venue-local. Use kickoff_local (already in Europe/Copenhagen) so
        # late-evening US/Mexico games — which kick off the next day in
        # Copenhagen — match the TV2 article filed on that calendar date.
        cph_date = rec["kickoff_local"][:10]
        key_en = (cph_date, _norm_pair(rec["team1"], rec["team2"]))
        key_da = (cph_date, _norm_pair(rec["team1_da"], rec["team2_da"]))
        hit = by_en_pair.get(key_en) or by_da_pair.get(key_da)
        if hit:
            rec["channels_da"] = list(hit["channels_da"])
            if rec["team1"] and not rec["team1_da"]:
                rec["team1_da"] = hit["team1_da"]
            if rec["team2"] and not rec["team2_da"]:
                rec["team2_da"] = hit["team2_da"]

    return {
        "generated_at": generated_at,
        "tournament": "FIFA World Cup 2026",
        "sources": {
            "fixtures": OPENFOOTBALL_URL,
            "channels": TV2_URL,
            "fetched_at": fetched_at,
        },
        "matches": matches,
    }


# ---------------------------------------------------------------------------
# Fetchers
# ---------------------------------------------------------------------------

def fetch_openfootball() -> dict[str, Any]:
    import requests
    resp = requests.get(OPENFOOTBALL_URL, timeout=30)
    resp.raise_for_status()
    return resp.json()


def fetch_tv2() -> str:
    import requests
    resp = requests.get(TV2_URL, timeout=30, headers={
        "User-Agent": "calendarInport/0.1 (+https://github.com/Vodkadav/calendarInport)",
    })
    resp.raise_for_status()
    # TV2 omits charset in Content-Type; bytes are UTF-8 but requests defaults
    # to ISO-8859-1 per HTTP spec. Force UTF-8 so Danish characters round-trip.
    resp.encoding = "utf-8"
    return resp.text


# ---------------------------------------------------------------------------
# Entrypoints
# ---------------------------------------------------------------------------

def _now_iso_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _configure_stdout_utf8() -> None:
    # Windows console default (cp1252) garbles Danish characters like Ø, Æ, Å
    # in log output. Force UTF-8 where the stream supports reconfiguration.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass


def run_live(out_path: Path) -> int:
    of_json = fetch_openfootball()
    tv2_html = fetch_tv2()
    merged = build_merged(of_json, tv2_html,
                          generated_at=_now_iso_utc(), fetched_at=_now_iso_utc())
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    log.info("wrote %s (%d matches)", out_path, len(merged["matches"]))
    return 0


def run_dry(out_path: Path) -> int:
    fixtures = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
    of_json = json.loads((fixtures / "openfootball_sample.json").read_text(encoding="utf-8"))
    tv2_html = (fixtures / "tv2_sample.html").read_text(encoding="utf-8")
    merged = build_merged(of_json, tv2_html,
                          generated_at=_now_iso_utc(), fetched_at=_now_iso_utc())
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    log.info("dry-run wrote %s (%d matches)", out_path, len(merged["matches"]))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build data/merged.json from openfootball + TV2.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Use tests/fixtures/ instead of hitting the network.")
    parser.add_argument("--out", type=Path,
                        default=Path(__file__).resolve().parent.parent / "data" / "merged.json")
    args = parser.parse_args(argv)

    _configure_stdout_utf8()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if args.dry_run:
        return run_dry(args.out)
    return run_live(args.out)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
