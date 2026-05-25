"""Tests for scripts/generate.py — TDD first.

All tests are hermetic. Tests load `data/merged.json` (a stable build artifact
of refresh.py) only where they assert against full-build counts; everything
else uses inline match fixtures.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from icalendar import Calendar

from scripts import generate

ROOT = Path(__file__).resolve().parent.parent
MERGED_JSON = ROOT / "data" / "merged.json"

CANONICAL_VTIMEZONE = (
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

BUILD_DTSTAMP = "20260524T120000Z"
SEQ = 20596  # arbitrary; tests fix it for determinism


# ---------------------------------------------------------------------------
# Helpers — minimal valid match records mirroring data/merged.json schema
# ---------------------------------------------------------------------------


def _match(**overrides):
    base = {
        "id": 1,
        "stage": "group",
        "round_label": "Matchday 1",
        "group": "A",
        "date": "2026-06-11",
        "kickoff_local": "2026-06-11T21:00:00",
        "kickoff_utc": "2026-06-11T19:00:00Z",
        "team1": "Mexico",
        "team2": "South Africa",
        "team1_token": None,
        "team2_token": None,
        "team1_da": "Mexico",
        "team2_da": "Sydafrika",
        "venue": "Estadio Azteca",
        "city": "Mexico City",
        "country": "Mexico",
        "ground_raw": "Mexico City",
        "channels_da": ["TV 2"],
    }
    base.update(overrides)
    return base


def _r32_unresolved(**overrides):
    return _match(
        id=73,
        stage="r32",
        round_label="Round of 32",
        group=None,
        date="2026-06-28",
        kickoff_local="2026-06-28T21:00:00",
        kickoff_utc="2026-06-28T19:00:00Z",
        team1=None,
        team2=None,
        team1_token="2A",
        team2_token="2B",
        team1_da=None,
        team2_da=None,
        venue="SoFi Stadium",
        city="Inglewood",
        country="United States",
        ground_raw="Los Angeles (Inglewood)",
        channels_da=[],
        **overrides,
    )


def _final_unresolved(**overrides):
    base = dict(
        id=104,
        stage="final",
        round_label="Final",
        group=None,
        date="2026-07-19",
        kickoff_local="2026-07-19T21:00:00",
        kickoff_utc="2026-07-19T19:00:00Z",
        team1=None,
        team2=None,
        team1_token="W101",
        team2_token="W102",
        team1_da=None,
        team2_da=None,
        venue="MetLife Stadium",
        city="East Rutherford",
        country="United States",
        ground_raw="New York/New Jersey (East Rutherford)",
        channels_da=[],
    )
    base.update(overrides)
    return _match(**base)


def _third_unresolved(**overrides):
    return _match(
        id=103,
        stage="3rd",
        round_label="Match for third place",
        group=None,
        date="2026-07-18",
        kickoff_local="2026-07-18T23:00:00",
        kickoff_utc="2026-07-18T21:00:00Z",
        team1=None,
        team2=None,
        team1_token="L101",
        team2_token="L102",
        team1_da=None,
        team2_da=None,
        venue="Hard Rock Stadium",
        city="Miami Gardens",
        country="United States",
        ground_raw="Miami (Miami Gardens)",
        channels_da=[],
        **overrides,
    )


def _build_all(matches):
    return generate.build_calendar(
        matches, cal_name="FIFA World Cup 2026",
        build_dtstamp=BUILD_DTSTAMP, sequence=SEQ,
    )


# ---------------------------------------------------------------------------
# 1. VTIMEZONE
# ---------------------------------------------------------------------------


def test_vtimezone_block_present_in_all_ics() -> None:
    out = _build_all([_match()])
    assert CANONICAL_VTIMEZONE in out


# ---------------------------------------------------------------------------
# 2. all.ics from full merged.json contains 104 VEVENTs
# ---------------------------------------------------------------------------


def test_all_ics_contains_104_vevents() -> None:
    matches = json.loads(MERGED_JSON.read_text(encoding="utf-8"))["matches"]
    out = _build_all(matches)
    cal = Calendar.from_ical(out)
    vevents = [c for c in cal.subcomponents if c.name == "VEVENT"]
    assert len(vevents) == 104


# ---------------------------------------------------------------------------
# 3. UID format invariant
# ---------------------------------------------------------------------------


def test_uid_is_match_id_at_worldcup_local() -> None:
    matches = json.loads(MERGED_JSON.read_text(encoding="utf-8"))["matches"]
    out = _build_all(matches)
    cal = Calendar.from_ical(out)
    for v in cal.subcomponents:
        if v.name != "VEVENT":
            continue
        uid = str(v["UID"])
        assert uid.endswith("@worldcup2026.local")
        assert uid.startswith("match-")
        n = int(uid[len("match-"):-len("@worldcup2026.local")])
        assert 1 <= n <= 104


# ---------------------------------------------------------------------------
# 4. UID stable across rebuilds
# ---------------------------------------------------------------------------


def test_uid_stable_across_rebuilds() -> None:
    matches = [_match(), _r32_unresolved()]
    a = _build_all(matches)
    b = _build_all(matches)
    uids_a = sorted(str(v["UID"]) for v in Calendar.from_ical(a).subcomponents if v.name == "VEVENT")
    uids_b = sorted(str(v["UID"]) for v in Calendar.from_ical(b).subcomponents if v.name == "VEVENT")
    assert uids_a == uids_b
    assert uids_a == ["match-1@worldcup2026.local", "match-73@worldcup2026.local"]


# ---------------------------------------------------------------------------
# 5. SUMMARY for resolved match
# ---------------------------------------------------------------------------


def test_summary_resolved_match_uses_team_names() -> None:
    out = _build_all([_match()])
    cal = Calendar.from_ical(out)
    v = next(c for c in cal.subcomponents if c.name == "VEVENT")
    assert str(v["SUMMARY"]) == "Mexico vs South Africa"


# ---------------------------------------------------------------------------
# 6. SUMMARY for unresolved match uses render_token
# ---------------------------------------------------------------------------


def test_summary_unresolved_match_uses_render_token() -> None:
    out = _build_all([_r32_unresolved(), _final_unresolved()])
    cal = Calendar.from_ical(out)
    summaries = {int(str(v["UID"])[len("match-"):-len("@worldcup2026.local")]): str(v["SUMMARY"])
                 for v in cal.subcomponents if v.name == "VEVENT"}
    assert summaries[73] == "Runner-up Group A vs Runner-up Group B"
    assert summaries[104] == "Winner of match 101 vs Winner of match 102"


# ---------------------------------------------------------------------------
# 7. LOCATION
# ---------------------------------------------------------------------------


def test_location_combines_venue_city_country() -> None:
    out = _build_all([_match()])
    cal = Calendar.from_ical(out)
    v = next(c for c in cal.subcomponents if c.name == "VEVENT")
    assert str(v["LOCATION"]) == "Estadio Azteca, Mexico City, Mexico"


# ---------------------------------------------------------------------------
# 8. DESCRIPTION includes channels when present
# ---------------------------------------------------------------------------


def test_description_includes_channels_when_present() -> None:
    out = _build_all([_match()])
    cal = Calendar.from_ical(out)
    v = next(c for c in cal.subcomponents if c.name == "VEVENT")
    desc = str(v["DESCRIPTION"])
    assert "Stage: Matchday 1 — Group A" in desc
    assert "Channels (DK): TV 2" in desc
    assert "Sources: openfootball/worldcup.json + TV2 sendeplan" in desc


# ---------------------------------------------------------------------------
# 9. DESCRIPTION says TBD when no channels
# ---------------------------------------------------------------------------


def test_description_says_tbd_when_no_channels() -> None:
    out = _build_all([_r32_unresolved()])
    cal = Calendar.from_ical(out)
    v = next(c for c in cal.subcomponents if c.name == "VEVENT")
    desc = str(v["DESCRIPTION"])
    assert "Channels (DK): TBD" in desc
    # knockout match has no group → no " — Group X" suffix
    assert desc.startswith("Stage: Round of 32\n")


# ---------------------------------------------------------------------------
# 10. Per-team .ics only has resolved appearances
# ---------------------------------------------------------------------------


def test_per_team_ics_only_resolved_appearances() -> None:
    matches = [
        _match(),                     # Mexico vs SA, id 1, resolved
        _r32_unresolved(),            # id 73, token 2A — would be Mexico IF they finished 2nd
        _final_unresolved(),
    ]
    files = generate.build_per_team_calendars(
        matches, build_dtstamp=BUILD_DTSTAMP, sequence=SEQ,
    )
    assert "mexico" in files
    cal = Calendar.from_ical(files["mexico"])
    ids = {int(str(v["UID"])[len("match-"):-len("@worldcup2026.local")])
           for v in cal.subcomponents if v.name == "VEVENT"}
    assert 1 in ids
    assert 73 not in ids
    assert 104 not in ids


# ---------------------------------------------------------------------------
# 11. Per-team final only when resolved into it
# ---------------------------------------------------------------------------


def test_per_team_ics_final_only_when_resolved_into_it() -> None:
    matches = [
        _match(),  # Mexico vs SA in group
        _final_unresolved(team1="Mexico", team2="Argentina",
                          team1_token=None, team2_token=None,
                          team1_da="Mexico", team2_da="Argentina"),
    ]
    files = generate.build_per_team_calendars(
        matches, build_dtstamp=BUILD_DTSTAMP, sequence=SEQ,
    )
    mex_ids = {int(str(v["UID"])[len("match-"):-len("@worldcup2026.local")])
               for v in Calendar.from_ical(files["mexico"]).subcomponents
               if v.name == "VEVENT"}
    arg_ids = {int(str(v["UID"])[len("match-"):-len("@worldcup2026.local")])
               for v in Calendar.from_ical(files["argentina"]).subcomponents
               if v.name == "VEVENT"}
    sa_ids = {int(str(v["UID"])[len("match-"):-len("@worldcup2026.local")])
              for v in Calendar.from_ical(files["south-africa"]).subcomponents
              if v.name == "VEVENT"}
    assert 104 in mex_ids
    assert 104 in arg_ids
    assert 104 not in sa_ids


# ---------------------------------------------------------------------------
# 12. all.ics always includes match 103 and 104
# ---------------------------------------------------------------------------


def test_all_ics_always_includes_match_103_and_104() -> None:
    matches = json.loads(MERGED_JSON.read_text(encoding="utf-8"))["matches"]
    out = _build_all(matches)
    cal = Calendar.from_ical(out)
    ids = {int(str(v["UID"])[len("match-"):-len("@worldcup2026.local")])
           for v in cal.subcomponents if v.name == "VEVENT"}
    assert 103 in ids
    assert 104 in ids


# ---------------------------------------------------------------------------
# 13. Line folding at 75 octets
# ---------------------------------------------------------------------------


def test_line_folding_at_75_octets() -> None:
    long_desc_match = _match(channels_da=["TV 2", "DR1", "DR2", "TV 2 Sport",
                                          "TV 2 Sport X", "DR K", "DR Ramasjang"])
    out = _build_all([long_desc_match])
    # All physical lines must be <= 75 octets (excluding CRLF).
    for line in out.split("\r\n"):
        assert len(line.encode("utf-8")) <= 75, f"line too long: {line!r}"
    # Unfolding (CRLF + space → '') round-trips: result must still parse.
    unfolded = out.replace("\r\n ", "")
    cal = Calendar.from_ical(unfolded)
    v = next(c for c in cal.subcomponents if c.name == "VEVENT")
    desc = str(v["DESCRIPTION"])
    assert "TV 2 Sport X" in desc
    assert "DR Ramasjang" in desc


# ---------------------------------------------------------------------------
# 14. DTSTART uses TZID=Europe/Copenhagen — no Z, no offset
# ---------------------------------------------------------------------------


def test_dtstart_uses_tzid_europe_copenhagen() -> None:
    out = _build_all([_match()])
    # Isolate the VEVENT block — VTIMEZONE has its own DTSTART without TZID.
    unfolded = out.replace("\r\n ", "")
    vevent_block = unfolded.split("BEGIN:VEVENT", 1)[1].split("END:VEVENT", 1)[0]
    dtstart_lines = [ln for ln in vevent_block.split("\r\n") if ln.startswith("DTSTART")]
    assert dtstart_lines, "no DTSTART line emitted inside VEVENT"
    line = dtstart_lines[0]
    assert "TZID=Europe/Copenhagen" in line
    assert "Z" not in line.split(":", 1)[1]
    value = line.split(":", 1)[1]
    # YYYYMMDDTHHMMSS — no separators
    assert value == "20260611T210000"


# ---------------------------------------------------------------------------
# 15. Slug handles diacritics & punctuation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name,expected", [
    ("USA", "usa"),
    ("South Africa", "south-africa"),
    ("Côte d'Ivoire", "cote-d-ivoire"),
    ("Bosnia & Herzegovina", "bosnia-herzegovina"),
    ("Curaçao", "curacao"),
])
def test_slug_handles_diacritics_and_punctuation(name: str, expected: str) -> None:
    assert generate.slugify(name) == expected


# ---------------------------------------------------------------------------
# 16. SEQUENCE = days since 1970-01-01 — same for all events in a build
# ---------------------------------------------------------------------------


def test_sequence_is_days_since_epoch() -> None:
    matches = json.loads(MERGED_JSON.read_text(encoding="utf-8"))["matches"]
    out = _build_all(matches)
    cal = Calendar.from_ical(out)
    seqs = {int(v["SEQUENCE"]) for v in cal.subcomponents if v.name == "VEVENT"}
    assert seqs == {SEQ}

    # Independently verify compute_sequence() == days since epoch as of today.
    expected = (datetime.now(timezone.utc).date() - datetime(1970, 1, 1, tzinfo=timezone.utc).date()).days
    assert generate.compute_sequence() == expected


# ---------------------------------------------------------------------------
# Extra coverage tests
# ---------------------------------------------------------------------------


def test_dtend_is_two_hours_after_dtstart() -> None:
    out = _build_all([_match()])
    unfolded = out.replace("\r\n ", "")
    vevent_block = unfolded.split("BEGIN:VEVENT", 1)[1].split("END:VEVENT", 1)[0]
    dtend_lines = [ln for ln in vevent_block.split("\r\n") if ln.startswith("DTEND")]
    assert dtend_lines, "no DTEND line emitted"
    assert "TZID=Europe/Copenhagen" in dtend_lines[0]
    assert dtend_lines[0].split(":", 1)[1] == "20260611T230000"


def test_vcalendar_header_fields_present() -> None:
    out = _build_all([_match()])
    assert "BEGIN:VCALENDAR\r\n" in out
    assert "VERSION:2.0\r\n" in out
    assert "PRODID:-//Vodkadav//calendarInport//EN\r\n" in out
    assert "CALSCALE:GREGORIAN\r\n" in out
    assert "METHOD:PUBLISH\r\n" in out
    assert "X-WR-CALNAME:FIFA World Cup 2026\r\n" in out
    assert "X-WR-TIMEZONE:Europe/Copenhagen\r\n" in out


def test_per_team_calendar_name_has_team_suffix() -> None:
    files = generate.build_per_team_calendars(
        [_match()], build_dtstamp=BUILD_DTSTAMP, sequence=SEQ,
    )
    assert "X-WR-CALNAME:FIFA World Cup 2026 — Mexico\r\n" in files["mexico"]


def test_crlf_line_endings() -> None:
    out = _build_all([_match()])
    # No bare \n that isn't part of \r\n.
    assert "\n" in out
    # Splitting by CRLF should yield no line containing a bare \n.
    for chunk in out.split("\r\n"):
        assert "\n" not in chunk


# ---------------------------------------------------------------------------
# teams.json side-emit (slice 2.5 — picker source-of-truth)
# ---------------------------------------------------------------------------


def test_teams_json_emitted_with_all_qualified_teams(tmp_path, monkeypatch) -> None:
    """`scripts/generate.py main()` writes data/teams.json with one record per
    per-team .ics file."""
    # Stage a temporary repo layout that mirrors the real one.
    (tmp_path / "data").mkdir()
    (tmp_path / "ics").mkdir()
    # Copy real merged.json so the team/group derivation is realistic.
    real_merged = json.loads(MERGED_JSON.read_text(encoding="utf-8"))
    (tmp_path / "data" / "merged.json").write_text(
        json.dumps(real_merged), encoding="utf-8"
    )

    # Patch generate's resolved repo root.
    monkeypatch.setattr(
        generate, "__file__",
        str(tmp_path / "scripts" / "generate.py"),
    )
    (tmp_path / "scripts").mkdir()
    rc = generate.main([])
    assert rc == 0

    teams_path = tmp_path / "data" / "teams.json"
    assert teams_path.exists(), "data/teams.json was not emitted"
    teams = json.loads(teams_path.read_text(encoding="utf-8"))
    assert isinstance(teams, list)

    ics_files = list((tmp_path / "ics").glob("*.ics"))
    # Subtract synthetic files (all.ics, favourites.ics preset) from the per-team count.
    synthetic = {"all.ics", "favourites.ics"}
    per_team_count = len([p for p in ics_files if p.name not in synthetic])
    assert len(teams) == per_team_count
    assert per_team_count > 0


def test_teams_json_records_have_name_slug_group(tmp_path, monkeypatch) -> None:
    """Every record is {name, slug, group} with non-empty strings; slug matches
    slugify(name); group is single uppercase letter A–L; list is sorted by name."""
    (tmp_path / "data").mkdir()
    (tmp_path / "ics").mkdir()
    (tmp_path / "scripts").mkdir()
    real_merged = json.loads(MERGED_JSON.read_text(encoding="utf-8"))
    (tmp_path / "data" / "merged.json").write_text(
        json.dumps(real_merged), encoding="utf-8"
    )
    monkeypatch.setattr(
        generate, "__file__",
        str(tmp_path / "scripts" / "generate.py"),
    )
    rc = generate.main([])
    assert rc == 0

    teams = json.loads((tmp_path / "data" / "teams.json").read_text(encoding="utf-8"))
    valid_groups = set("ABCDEFGHIJKL")
    names = [r["name"] for r in teams]
    assert names == sorted(names), "teams.json must be sorted by name ascending"
    for rec in teams:
        assert set(rec.keys()) == {"name", "slug", "group"}, rec
        for k in ("name", "slug", "group"):
            assert isinstance(rec[k], str) and rec[k], (k, rec)
        assert generate.slugify(rec["name"]) == rec["slug"], rec
        assert rec["group"] in valid_groups, rec
        assert len(rec["group"]) == 1


# ---------------------------------------------------------------------------
# Favourites preset (curated one-click combined subscription)
# ---------------------------------------------------------------------------


def test_favourites_constant_is_the_11_specified_teams() -> None:
    """Lock the curated list. Changing it requires touching this assertion
    deliberately so an accidental edit can't silently drift the user-facing
    promise."""
    assert generate.FAVOURITES == [
        "Mexico", "England", "Canada", "USA", "Spain", "Germany",
        "France", "Brazil", "Belgium", "Argentina", "Portugal",
    ]


def test_favourites_calendar_filters_to_favourites_only() -> None:
    favourite = _match()  # Mexico vs South Africa — Mexico in FAVOURITES
    irrelevant = _match(
        id=2, team1="South Korea", team2="Czech Republic",
        team1_da="Sydkorea", team2_da="Tjekkiet",
    )
    out = generate.build_favourites_calendar(
        [favourite, irrelevant], BUILD_DTSTAMP, SEQ,
    )
    cal = Calendar.from_ical(out)
    vevents = [c for c in cal.subcomponents if c.name == "VEVENT"]
    assert len(vevents) == 1, (
        f"expected 1 VEVENT (Mexico's only); got {len(vevents)}"
    )
    assert str(vevents[0]["SUMMARY"]) == "Mexico vs South Africa"


def test_favourites_calendar_dedups_match_with_two_favourites() -> None:
    """If two favourites meet (e.g. Mexico vs France), the event appears
    exactly once."""
    match = _match(team1="Mexico", team2="France", team2_da="Frankrig")
    out = generate.build_favourites_calendar([match], BUILD_DTSTAMP, SEQ)
    cal = Calendar.from_ical(out)
    vevents = [c for c in cal.subcomponents if c.name == "VEVENT"]
    assert len(vevents) == 1


def test_favourites_calendar_excludes_unresolved_knockouts() -> None:
    """Knockout matches whose team1/team2 are None (still tokens) must be
    excluded. They join the calendar only once a favourite has been
    resolved into a slot — which the next daily refresh handles."""
    out = generate.build_favourites_calendar(
        [_r32_unresolved(), _final_unresolved()],
        BUILD_DTSTAMP, SEQ,
    )
    cal = Calendar.from_ical(out)
    vevents = [c for c in cal.subcomponents if c.name == "VEVENT"]
    assert vevents == []


def test_favourites_calendar_x_wr_calname() -> None:
    out = generate.build_favourites_calendar([_match()], BUILD_DTSTAMP, SEQ)
    cal = Calendar.from_ical(out)
    assert str(cal["X-WR-CALNAME"]) == "FIFA World Cup 2026 — Favourites"


def test_favourites_calendar_uses_canonical_vtimezone() -> None:
    """Same VTIMEZONE block as all.ics + per-team .ics — must not drift."""
    out = generate.build_favourites_calendar([_match()], BUILD_DTSTAMP, SEQ)
    assert CANONICAL_VTIMEZONE in out


def test_main_emits_favourites_ics(tmp_path, monkeypatch) -> None:
    """`generate.main()` writes ics/favourites.ics with ≥33 VEVENTs (11
    favourites × 3 group-stage matches; all 11 are in different groups,
    so no intra-favourite group-stage clash to dedup)."""
    (tmp_path / "data").mkdir()
    (tmp_path / "ics").mkdir()
    (tmp_path / "scripts").mkdir()
    real_merged = json.loads(MERGED_JSON.read_text(encoding="utf-8"))
    (tmp_path / "data" / "merged.json").write_text(
        json.dumps(real_merged), encoding="utf-8",
    )
    monkeypatch.setattr(
        generate, "__file__",
        str(tmp_path / "scripts" / "generate.py"),
    )
    rc = generate.main([])
    assert rc == 0

    fav_path = tmp_path / "ics" / "favourites.ics"
    assert fav_path.exists(), "ics/favourites.ics was not emitted by main()"
    cal = Calendar.from_ical(fav_path.read_text(encoding="utf-8"))
    vevents = [c for c in cal.subcomponents if c.name == "VEVENT"]
    assert len(vevents) >= 33, (
        f"expected ≥33 VEVENTs (11 × 3 group matches); got {len(vevents)}"
    )
    # Every VEVENT in the file must mention at least one favourite team in
    # its SUMMARY (resolved matches only — unresolved knockouts excluded).
    for v in vevents:
        summary = str(v["SUMMARY"])
        assert any(team in summary for team in generate.FAVOURITES), (
            f"VEVENT SUMMARY {summary!r} has no favourite team"
        )
