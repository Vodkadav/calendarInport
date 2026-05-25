"""Generate RFC 5545 .ics calendars from data/merged.json.

Pipeline:
  1. read data/merged.json (produced by scripts/refresh.py)
  2. emit ics/all.ics — every match (104 VEVENTs)
  3. emit ics/{team-slug}.ics — one per qualified team (resolved appearances only)

Run:
  python scripts/generate.py

Design decisions (locked in plan doc — see ".claude/plans/20260523-fifa-2026-...md"):
  - UID:        match-{id}@worldcup2026.local  (stable across rebuilds + token resolutions)
  - DTSTART:    TZID=Europe/Copenhagen, no Z, no offset; YYYYMMDDTHHMMSS form
  - DTEND:      DTSTART + 2h
  - DTSTAMP:    build-time UTC
  - SEQUENCE:   days since 1970-01-01 (monotonic, stateless, same across a build)
  - SUMMARY:    resolved teams → "{team1} vs {team2}"; otherwise via render_token()
  - LOCATION:   "{venue}, {city}, {country}"
  - DESCRIPTION: 3 lines — Stage / Channels / Sources (RFC 5545-escaped)
  - VTIMEZONE:  literal canonical Europe/Copenhagen block (matched by tests)
  - Per-team:   only matches with team listed as resolved team1/team2 are included;
                unresolved knockouts appear only in all.ics.

Tests live in tests/test_generate.py — see them for the contract.
"""

from __future__ import annotations

import json
import logging
import re
import sys
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# Allow `python scripts/generate.py` to import the sibling modules.
_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR.parent) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR.parent))

from scripts.refresh import render_token  # noqa: E402

log = logging.getLogger("generate")


# ---------------------------------------------------------------------------
# Canonical VTIMEZONE block — proven against Google Calendar. Tests assert
# exact byte-for-byte match, so it lives as a literal string.
# ---------------------------------------------------------------------------

VTIMEZONE_BLOCK = (
    "BEGIN:VTIMEZONE\r\n"
    "TZID:Europe/Copenhagen\r\n"
    "BEGIN:STANDARD\r\n"
    "DTSTART:19701025T030000\r\n"
    "TZOFFSETFROM:+0200\r\n"
    "TZOFFSETTO:+0100\r\n"
    "TZNAME:CET\r\n"
    "RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU\r\n"
    "END:STANDARD\r\n"
    "BEGIN:DAYLIGHT\r\n"
    "DTSTART:19700329T020000\r\n"
    "TZOFFSETFROM:+0100\r\n"
    "TZOFFSETTO:+0200\r\n"
    "TZNAME:CEST\r\n"
    "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU\r\n"
    "END:DAYLIGHT\r\n"
    "END:VTIMEZONE\r\n"
)

PRODID = "-//Vodkadav//calendarInport//EN"
UID_DOMAIN = "worldcup2026.local"
EPOCH_DATE = datetime(1970, 1, 1, tzinfo=timezone.utc).date()


# ---------------------------------------------------------------------------
# Curated "Favourites" preset — single combined .ics for one-click subscribe.
# Stable across the tournament; knockout entries appear as their teams resolve.
# ---------------------------------------------------------------------------

FAVOURITES = [
    "Mexico", "England", "Canada", "USA", "Spain", "Germany",
    "France", "Brazil", "Belgium", "Argentina", "Portugal",
]
FAVOURITES_SLUG = "favourites"
FAVOURITES_CAL_NAME = "FIFA World Cup 2026 — Favourites"


# ---------------------------------------------------------------------------
# Slug
# ---------------------------------------------------------------------------

def slugify(name: str) -> str:
    """Lowercase, strip diacritics, replace any non-[a-z0-9] run with '-'."""
    nfkd = unicodedata.normalize("NFKD", name)
    no_marks = "".join(c for c in nfkd if not unicodedata.combining(c))
    lowered = no_marks.lower()
    collapsed = re.sub(r"[^a-z0-9]+", "-", lowered)
    return collapsed.strip("-")


# ---------------------------------------------------------------------------
# Field formatters
# ---------------------------------------------------------------------------

def _fmt_local_dt(iso_naive: str) -> str:
    """`2026-06-11T21:00:00` → `20260611T210000` (RFC 5545 local form)."""
    dt = datetime.fromisoformat(iso_naive)
    return dt.strftime("%Y%m%dT%H%M%S")


def _add_two_hours(iso_naive: str) -> str:
    dt = datetime.fromisoformat(iso_naive) + timedelta(hours=2)
    return dt.strftime("%Y%m%dT%H%M%S")


def _escape_text(s: str) -> str:
    """RFC 5545 TEXT escaping: backslash, comma, semicolon, newline."""
    return (
        s.replace("\\", "\\\\")
         .replace("\n", "\\n")
         .replace(",", "\\,")
         .replace(";", "\\;")
    )


def _summary(match: dict[str, Any]) -> str:
    t1 = match.get("team1")
    t2 = match.get("team2")
    left = t1 if t1 else render_token(match.get("team1_token") or "")
    right = t2 if t2 else render_token(match.get("team2_token") or "")
    return f"{left} vs {right}"


def _location(match: dict[str, Any]) -> str:
    return f"{match['venue']}, {match['city']}, {match['country']}"


def _description(match: dict[str, Any]) -> str:
    stage_line = f"Stage: {match['round_label']}"
    if match.get("group"):
        # Use ASCII em-dash variant from plan doc: " — " (U+2014 surrounded by spaces).
        stage_line += f" — Group {match['group']}"
    channels = match.get("channels_da") or []
    channels_line = "Channels (DK): " + (", ".join(channels) if channels else "TBD")
    sources_line = "Sources: openfootball/worldcup.json + TV2 sendeplan"
    return "\n".join((stage_line, channels_line, sources_line))


# ---------------------------------------------------------------------------
# Line folding
# ---------------------------------------------------------------------------

def _fold_line(line: str) -> str:
    """RFC 5545 folding: split at 75 octets, continuation lines start with a single space.

    Folds on UTF-8 byte boundaries — never inside a multibyte character.
    """
    data = line.encode("utf-8")
    if len(data) <= 75:
        return line
    chunks: list[bytes] = []
    i = 0
    limit = 75
    while i < len(data):
        end = min(i + limit, len(data))
        # Back off if we'd split inside a UTF-8 continuation byte.
        while end < len(data) and (data[end] & 0xC0) == 0x80:
            end -= 1
        chunks.append(data[i:end])
        i = end
        limit = 74  # continuation lines: leading space consumes one octet
    return "\r\n ".join(c.decode("utf-8") for c in chunks)


def _emit(lines: list[str], key: str, value: str, *, escape: bool = True) -> None:
    rendered = _escape_text(value) if escape else value
    lines.append(_fold_line(f"{key}:{rendered}"))


def _emit_raw(lines: list[str], property_line: str) -> None:
    lines.append(_fold_line(property_line))


# ---------------------------------------------------------------------------
# VEVENT
# ---------------------------------------------------------------------------

def build_event(match: dict[str, Any], build_dtstamp: str, sequence: int) -> list[str]:
    """Return the unfolded list of property lines for a single VEVENT."""
    lines: list[str] = ["BEGIN:VEVENT"]
    _emit(lines, "UID", f"match-{match['id']}@{UID_DOMAIN}", escape=False)
    _emit(lines, "DTSTAMP", build_dtstamp, escape=False)
    lines.append(f"SEQUENCE:{sequence}")
    _emit_raw(lines, f"DTSTART;TZID=Europe/Copenhagen:{_fmt_local_dt(match['kickoff_local'])}")
    _emit_raw(lines, f"DTEND;TZID=Europe/Copenhagen:{_add_two_hours(match['kickoff_local'])}")
    _emit(lines, "SUMMARY", _summary(match))
    _emit(lines, "LOCATION", _location(match))
    _emit(lines, "DESCRIPTION", _description(match))
    lines.append("END:VEVENT")
    return lines


# ---------------------------------------------------------------------------
# VCALENDAR
# ---------------------------------------------------------------------------

def build_calendar(
    matches: list[dict[str, Any]],
    cal_name: str,
    build_dtstamp: str,
    sequence: int,
) -> str:
    """Build a complete VCALENDAR string (CRLF line endings, folded per RFC 5545)."""
    out: list[str] = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]
    # X-WR-CALNAME is TEXT — escape per RFC 5545.
    out.append(_fold_line(f"X-WR-CALNAME:{_escape_text(cal_name)}"))
    out.append("X-WR-TIMEZONE:Europe/Copenhagen")

    # Serialize the VTIMEZONE literal verbatim — tests assert exact match.
    body = "\r\n".join(out) + "\r\n" + VTIMEZONE_BLOCK

    event_chunks: list[str] = []
    for match in matches:
        event_chunks.append("\r\n".join(build_event(match, build_dtstamp, sequence)))

    if event_chunks:
        body += "\r\n".join(event_chunks) + "\r\n"
    body += "END:VCALENDAR\r\n"
    return body


# ---------------------------------------------------------------------------
# Per-team selection
# ---------------------------------------------------------------------------

def collect_team_names(matches: list[dict[str, Any]]) -> list[str]:
    """Distinct English team names that appear as a resolved team1 or team2."""
    seen: list[str] = []
    for m in matches:
        for key in ("team1", "team2"):
            t = m.get(key)
            if t and t not in seen:
                seen.append(t)
    return seen


def build_per_team_calendars(
    matches: list[dict[str, Any]],
    build_dtstamp: str,
    sequence: int,
) -> dict[str, str]:
    """Return {slug: ics_string} for every team appearing as resolved team1/team2."""
    teams = collect_team_names(matches)
    out: dict[str, str] = {}
    for team in teams:
        team_matches = [m for m in matches if m.get("team1") == team or m.get("team2") == team]
        slug = slugify(team)
        cal_name = f"FIFA World Cup 2026 — {team}"
        out[slug] = build_calendar(team_matches, cal_name, build_dtstamp, sequence)
    return out


def build_favourites_calendar(
    matches: list[dict[str, Any]],
    build_dtstamp: str,
    sequence: int,
) -> str:
    """Build a single VCALENDAR for the FAVOURITES preset.

    Includes a match iff *resolved* team1 or team2 is in FAVOURITES. Unresolved
    knockouts (team1/team2 None) are excluded — they enter the calendar on the
    next daily refresh once a favourite team is resolved into one of the slots.
    """
    favourites = set(FAVOURITES)
    selected = [
        m for m in matches
        if m.get("team1") in favourites or m.get("team2") in favourites
    ]
    return build_calendar(selected, FAVOURITES_CAL_NAME, build_dtstamp, sequence)


def build_teams_index(matches: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Return [{name, slug, group}] sorted by name for every team that gets a per-team .ics.

    `group` is derived from the team's first group-stage appearance in `matches`.
    Teams that never appear in a group-stage match (shouldn't happen for the 48
    qualifiers, but handle defensively) are skipped from the index.
    """
    teams = collect_team_names(matches)
    group_by_team: dict[str, str] = {}
    for m in matches:
        if m.get("stage") != "group":
            continue
        g = m.get("group")
        if not g:
            continue
        for key in ("team1", "team2"):
            t = m.get(key)
            if t and t not in group_by_team:
                group_by_team[t] = g
    records = [
        {"name": t, "slug": slugify(t), "group": group_by_team[t]}
        for t in teams
        if t in group_by_team
    ]
    records.sort(key=lambda r: r["name"])
    return records


# ---------------------------------------------------------------------------
# Sequence + dtstamp helpers
# ---------------------------------------------------------------------------

def compute_sequence(now: datetime | None = None) -> int:
    """Days since 1970-01-01 UTC. Monotonic, stateless."""
    if now is None:
        now = datetime.now(timezone.utc)
    return (now.date() - EPOCH_DATE).days


def _now_dtstamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _configure_stdout_utf8() -> None:
    # Windows console default (cp1252) garbles Danish characters in log output.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    _configure_stdout_utf8()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    repo_root = Path(__file__).resolve().parent.parent
    merged_path = repo_root / "data" / "merged.json"
    data_dir = repo_root / "data"
    ics_dir = repo_root / "ics"
    ics_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)

    merged = json.loads(merged_path.read_text(encoding="utf-8"))
    matches = merged["matches"]

    build_dtstamp = _now_dtstamp()
    sequence = compute_sequence()

    all_ics = build_calendar(matches, "FIFA World Cup 2026", build_dtstamp, sequence)
    (ics_dir / "all.ics").write_bytes(all_ics.encode("utf-8"))
    log.info("wrote ics/all.ics (%d matches)", len(matches))

    per_team = build_per_team_calendars(matches, build_dtstamp, sequence)
    for slug, ics in per_team.items():
        (ics_dir / f"{slug}.ics").write_bytes(ics.encode("utf-8"))
    log.info("wrote %d per-team .ics files", len(per_team))

    favourites_ics = build_favourites_calendar(matches, build_dtstamp, sequence)
    (ics_dir / f"{FAVOURITES_SLUG}.ics").write_bytes(favourites_ics.encode("utf-8"))
    log.info("wrote ics/%s.ics (favourites preset)", FAVOURITES_SLUG)

    teams_index = build_teams_index(matches)
    (data_dir / "teams.json").write_text(
        json.dumps(teams_index, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    log.info("wrote data/teams.json (%d teams)", len(teams_index))

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
