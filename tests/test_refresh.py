"""Tests for scripts/refresh.py — TDD first.

All tests are hermetic: no network is touched. Fixtures live in tests/fixtures/.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import refresh
from scripts.team_names import da_to_en, en_to_da

FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# 1. openfootball record → merged-schema match
# ---------------------------------------------------------------------------


def test_openfootball_group_match_parsed_into_schema() -> None:
    of_match = {
        "round": "Matchday 1",
        "num": 1,
        "date": "2026-06-11",
        "time": "13:00 UTC-6",
        "team1": "Mexico",
        "team2": "South Africa",
        "group": "Group A",
        "ground": "Mexico City",
    }

    record = refresh.openfootball_to_match(of_match, round_name="Matchday 1")

    assert record["stage"] == "group"
    assert record["round_label"] == "Matchday 1"
    assert record["group"] == "A"  # "Group " prefix stripped
    assert record["date"] == "2026-06-11"
    assert record["team1"] == "Mexico"
    assert record["team2"] == "South Africa"
    assert record["team1_token"] is None
    assert record["team2_token"] is None
    assert record["team1_da"] == "Mexico"
    assert record["team2_da"] == "Sydafrika"
    assert record["venue"] == "Estadio Azteca"
    assert record["city"] == "Mexico City"
    assert record["country"] == "Mexico"
    assert record["ground_raw"] == "Mexico City"
    assert record["channels_da"] == []
    # id is left as 0 here; assigned chronologically by build_merged
    assert record["id"] == 0


def test_group_field_strips_group_prefix_only_on_group_stage() -> None:
    rec = refresh.openfootball_to_match(
        {"round": "Round of 32", "date": "2026-06-28", "time": "12:00 UTC-7",
         "team1": "2A", "team2": "2B", "ground": "Los Angeles (Inglewood)"},
        round_name="Round of 32",
    )
    assert rec["group"] is None  # nulled out for non-group stages


# ---------------------------------------------------------------------------
# 2. knockout placeholders → team*_token, real team fields null
# ---------------------------------------------------------------------------


def test_knockout_group_position_token_routed_to_token_field() -> None:
    # Real openfootball R32 example: team1="2A" (runner-up Group A).
    of_match = {
        "round": "Round of 32",
        "num": 73,
        "date": "2026-06-28",
        "time": "12:00 UTC-7",
        "team1": "2A",
        "team2": "2B",
        "ground": "Los Angeles (Inglewood)",
    }
    record = refresh.openfootball_to_match(of_match, round_name="Round of 32")
    assert record["team1"] is None
    assert record["team2"] is None
    assert record["team1_token"] == "2A"
    assert record["team2_token"] == "2B"
    assert record["team1_da"] is None
    assert record["team2_da"] is None
    assert record["stage"] == "r32"


def test_knockout_match_result_token_routed() -> None:
    # Real openfootball Final example: team1="W101", team2="W102".
    of_match = {
        "round": "Final",
        "date": "2026-07-19",
        "time": "15:00 UTC-4",
        "team1": "W101",
        "team2": "W102",
        "ground": "New York/New Jersey (East Rutherford)",
    }
    record = refresh.openfootball_to_match(of_match, round_name="Final")
    assert record["team1_token"] == "W101"
    assert record["team2_token"] == "W102"
    assert record["stage"] == "final"


def test_knockout_composite_third_place_token_routed() -> None:
    # Real openfootball R32: team2="3A/B/C/D/F" (one of those groups' 3rd place).
    of_match = {
        "round": "Round of 32",
        "date": "2026-06-29",
        "time": "16:30 UTC-4",
        "team1": "1E",
        "team2": "3A/B/C/D/F",
        "ground": "Boston (Foxborough)",
    }
    record = refresh.openfootball_to_match(of_match, round_name="Round of 32")
    assert record["team1_token"] == "1E"
    assert record["team2_token"] == "3A/B/C/D/F"


def test_stage_inferred_from_round_name() -> None:
    cases = [
        ("Matchday 1", "group"),
        ("Matchday 3", "group"),
        ("Round of 32", "r32"),
        ("Round of 16", "r16"),
        ("Quarter-final", "qf"),
        ("Quarter-finals", "qf"),
        ("Semi-final", "sf"),
        ("Semi-finals", "sf"),
        ("Match for third place", "3rd"),
        ("Final", "final"),
    ]
    for name, expected in cases:
        assert refresh.stage_from_round(name) == expected, name


# ---------------------------------------------------------------------------
# 3. Token grammar + rendering
# ---------------------------------------------------------------------------


def test_token_grammar_matches_real_openfootball_shapes() -> None:
    assert refresh._is_token("W101")
    assert refresh._is_token("L102")
    assert refresh._is_token("1A")
    assert refresh._is_token("2L")
    assert refresh._is_token("3A/B/C/D/F")
    assert refresh._is_token("3A")  # single-group third-place fallback
    # Real team names must NOT match
    assert not refresh._is_token("Mexico")
    assert not refresh._is_token("South Africa")
    assert not refresh._is_token("USA")
    assert not refresh._is_token("Bosnia & Herzegovina")
    assert not refresh._is_token("")
    assert not refresh._is_token(None)


def test_render_token_match_result() -> None:
    assert refresh.render_token("W101") == "Winner of match 101"
    assert refresh.render_token("L99") == "Loser of match 99"


def test_render_token_group_position() -> None:
    assert refresh.render_token("1A") == "Winner Group A"
    assert refresh.render_token("2L") == "Runner-up Group L"


def test_render_token_composite_third_place() -> None:
    assert refresh.render_token("3A/B/C/D/F") == "Third place A/B/C/D/F"
    assert refresh.render_token("3A") == "Third place A"


def test_render_token_unknown_passes_through() -> None:
    assert refresh.render_token("???") == "???"


# ---------------------------------------------------------------------------
# 4. Kickoff conversion — offset-in-time + venue-tz fallback
# ---------------------------------------------------------------------------


def test_kickoff_uses_embedded_utc_offset_eastern() -> None:
    # ET in June = UTC-4. 13:00 ET → 17:00 UTC.
    rec = refresh.openfootball_to_match(
        {"round": "Matchday 1", "date": "2026-06-12", "time": "13:00 UTC-4",
         "team1": "USA", "team2": "Brazil", "group": "Group B",
         "ground": "New York/New Jersey (East Rutherford)"},
        round_name="Matchday 1",
    )
    assert rec["kickoff_utc"] == "2026-06-12T17:00:00Z"


def test_kickoff_uses_embedded_utc_offset_pacific() -> None:
    # PT in June = UTC-7. 13:00 PT → 20:00 UTC.
    rec = refresh.openfootball_to_match(
        {"round": "Matchday 1", "date": "2026-06-12", "time": "13:00 UTC-7",
         "team1": "Canada", "team2": "Germany", "group": "Group C",
         "ground": "Los Angeles (Inglewood)"},
        round_name="Matchday 1",
    )
    assert rec["kickoff_utc"] == "2026-06-12T20:00:00Z"


def test_kickoff_uses_embedded_utc_offset_mexico() -> None:
    # Mexico City = UTC-6. 20:00 local → 02:00 UTC next day.
    rec = refresh.openfootball_to_match(
        {"round": "Matchday 1", "date": "2026-06-11", "time": "20:00 UTC-6",
         "team1": "Mexico", "team2": "South Africa", "group": "Group A",
         "ground": "Mexico City"},
        round_name="Matchday 1",
    )
    assert rec["kickoff_utc"] == "2026-06-12T02:00:00Z"


def test_kickoff_local_is_copenhagen_time() -> None:
    # 20:00 Mexico City (UTC-6) → 02:00 UTC → 04:00 Copenhagen (CEST = UTC+2).
    rec = refresh.openfootball_to_match(
        {"round": "Matchday 1", "date": "2026-06-11", "time": "20:00 UTC-6",
         "team1": "Mexico", "team2": "South Africa", "group": "Group A",
         "ground": "Mexico City"},
        round_name="Matchday 1",
    )
    assert rec["kickoff_local"] == "2026-06-12T04:00:00"


def test_kickoff_falls_back_to_venue_tz_when_no_offset() -> None:
    # If openfootball ever drops the offset, the venue tz must take over.
    local, utc = refresh._convert_kickoff("2026-06-11", "20:00", "America/Mexico_City")
    assert utc == "2026-06-12T02:00:00Z"
    assert local == "2026-06-12T04:00:00"


def test_kickoff_raises_on_unparseable_time() -> None:
    with pytest.raises(ValueError):
        refresh._convert_kickoff("2026-06-11", "garbage", "America/Mexico_City")


# ---------------------------------------------------------------------------
# 5. TV2 sendeplan HTML article → channel + Danish team pair
# ---------------------------------------------------------------------------


def test_parse_tv2_article_with_utc_datetime_converts_to_copenhagen() -> None:
    """Regression: TV2's time/@datetime is sometimes UTC ('...Z'), sometimes naive
    Copenhagen-local. A UTC datetime of 22:00 on June 13 is 00:00 Copenhagen on
    June 14, so the article's logical date is June 14 (TV2's own listing).
    """
    html = """
    <html><body><article>
      <time datetime="2026-06-13T22:00:00.000Z"></time>
      <h2>FIFA VM: Brasilien - Marokko</h2>
      <img src="/logos/tv2.png" alt="TV 2">
    </article></body></html>
    """
    entries = refresh.parse_tv2_html(html)
    assert len(entries) == 1
    e = entries[0]
    assert e["date"] == "2026-06-14"
    assert e["kickoff_local"] == "2026-06-14T00:00:00"


def test_parse_tv2_articles_extracts_teams_and_channel() -> None:
    html = (FIXTURES / "tv2_sample.html").read_text(encoding="utf-8")

    entries = refresh.parse_tv2_html(html)

    assert len(entries) == 3
    first = entries[0]
    assert first["date"] == "2026-06-11"
    assert first["kickoff_local"] == "2026-06-11T21:00:00"
    assert first["team1_da"] == "Mexico"
    assert first["team2_da"] == "Sydafrika"
    assert first["channels_da"] == ["TV 2"]

    second = entries[1]
    assert second["team1_da"] == "USA"
    assert second["team2_da"] == "Brasilien"
    assert "DR1" in second["channels_da"]
    assert "TV 2 Sport" in second["channels_da"]


# ---------------------------------------------------------------------------
# 6. merge by (date, normalised team pair) → venue + channels_da both present
# ---------------------------------------------------------------------------


def test_merge_uses_copenhagen_local_date_not_venue_date() -> None:
    """Regression: TV2 publishes Copenhagen-local dates; openfootball publishes
    venue-local dates. Late-evening US/Mexico games kick off the *next day* in
    Copenhagen, so a merge keyed on openfootball's raw `date` field misses
    every match that crosses Copenhagen midnight.
    """
    # 20:00 Mexico City (UTC-6) on June 11 = 04:00 Copenhagen on June 12.
    of_json = {
        "name": "Test",
        "matches": [{
            "round": "Matchday 1",
            "date": "2026-06-11",
            "time": "20:00 UTC-6",
            "team1": "South Korea",
            "team2": "Czech Republic",
            "group": "Group A",
            "ground": "Mexico City",
        }],
    }
    # TV2 article datetime is in Danish local time → it would file this
    # match under June 12.
    tv2_html = """
    <html><body><article>
      <time datetime="2026-06-12T04:00"></time>
      <h2>FIFA VM: Sydkorea - Tjekkiet</h2>
      <img src="/logos/tv2.png" alt="TV 2">
    </article></body></html>
    """
    merged = refresh.build_merged(of_json, tv2_html, generated_at="x", fetched_at="x")
    assert len(merged["matches"]) == 1
    assert merged["matches"][0]["channels_da"] == ["TV 2"], \
        "TV2 entry on Copenhagen-local date must merge with venue-local-date openfootball record"


def test_merge_combines_openfootball_and_tv2() -> None:
    of_json = json.loads((FIXTURES / "openfootball_sample.json").read_text(encoding="utf-8"))
    tv2_html = (FIXTURES / "tv2_sample.html").read_text(encoding="utf-8")

    merged = refresh.build_merged(
        of_json, tv2_html,
        generated_at="2026-05-23T00:00:00Z", fetched_at="2026-05-23T00:00:00Z",
    )

    matches = merged["matches"]
    # Chronological order: Mexico-SA (06-11) is id 1, USA-Brazil (06-12 17:00 UTC) is id 2.
    opener = matches[0]
    assert opener["id"] == 1
    assert opener["team1"] == "Mexico"
    assert opener["venue"] == "Estadio Azteca"
    assert opener["city"] == "Mexico City"
    assert opener["channels_da"] == ["TV 2"]

    usa_brz = matches[1]
    assert usa_brz["id"] == 2
    assert usa_brz["team1"] == "USA"
    assert usa_brz["team2"] == "Brazil"
    assert usa_brz["venue"] == "MetLife Stadium"
    assert "DR1" in usa_brz["channels_da"]


# ---------------------------------------------------------------------------
# 7. team-name normalization
# ---------------------------------------------------------------------------


def test_da_to_en_and_back_for_germany() -> None:
    assert da_to_en("Tyskland") == "Germany"
    assert en_to_da("Germany") == "Tyskland"


def test_da_to_en_for_south_africa_and_netherlands_alias() -> None:
    assert da_to_en("Sydafrika") == "South Africa"
    assert da_to_en("Holland") == "Netherlands"
    assert da_to_en("Nederlandene") == "Netherlands"


def test_da_to_en_for_usa_uses_openfootball_spelling() -> None:
    # openfootball uses "USA", not "United States" — keep mappings in lockstep.
    assert da_to_en("USA") == "USA"
    assert en_to_da("USA") == "USA"


def test_da_to_en_for_bosnia_uses_ampersand_spelling() -> None:
    # openfootball uses "Bosnia & Herzegovina" with an ampersand.
    assert da_to_en("Bosnien-Hercegovina") == "Bosnia & Herzegovina"


def test_da_to_en_for_uzbekistan_uses_danish_s_key() -> None:
    # Danish spelling is "Usbekistan" (s), openfootball uses "Uzbekistan" (z).
    assert da_to_en("Usbekistan") == "Uzbekistan"


def test_unknown_team_name_returns_none() -> None:
    assert da_to_en("Atlantis") is None


# ---------------------------------------------------------------------------
# 8. idempotency — same inputs yield same merged.json (ignoring timestamps)
# ---------------------------------------------------------------------------


def test_build_merged_is_idempotent_excluding_timestamps() -> None:
    of_json = json.loads((FIXTURES / "openfootball_sample.json").read_text(encoding="utf-8"))
    tv2_html = (FIXTURES / "tv2_sample.html").read_text(encoding="utf-8")

    a = refresh.build_merged(of_json, tv2_html, generated_at="x", fetched_at="x")
    b = refresh.build_merged(of_json, tv2_html, generated_at="y", fetched_at="y")

    a_copy = {**a}
    b_copy = {**b}
    a_copy["generated_at"] = b_copy["generated_at"] = "_"
    a_copy["sources"] = {**a_copy["sources"], "fetched_at": "_"}
    b_copy["sources"] = {**b_copy["sources"], "fetched_at": "_"}

    assert a_copy == b_copy
    ids = [m["id"] for m in a["matches"]]
    assert ids == sorted(ids)
    assert ids == list(range(1, len(ids) + 1))  # contiguous 1..N


# ---------------------------------------------------------------------------
# 9. Chronological id assignment (no `num` reliance)
# ---------------------------------------------------------------------------


def test_ids_assigned_chronologically_across_full_fixture() -> None:
    of_json = json.loads((FIXTURES / "openfootball_sample.json").read_text(encoding="utf-8"))
    tv2_html = (FIXTURES / "tv2_sample.html").read_text(encoding="utf-8")
    merged = refresh.build_merged(of_json, tv2_html, generated_at="x", fetched_at="x")

    by_id = {m["id"]: m for m in merged["matches"]}
    # Final (the last match by date) gets the highest id.
    last = max(by_id)
    assert by_id[last]["stage"] == "final"
    # 3rd place comes just before Final.
    assert by_id[last - 1]["stage"] == "3rd"
    # First match in chronological order is Mexico vs South Africa.
    assert by_id[1]["team1"] == "Mexico"


# ---------------------------------------------------------------------------
# 10. Dry-run / main entrypoint writes merged.json
# ---------------------------------------------------------------------------


def test_dry_run_writes_merged_json(tmp_path: Path) -> None:
    out = tmp_path / "merged.json"
    rc = refresh.run_dry(out_path=out)
    assert rc == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["tournament"] == "FIFA World Cup 2026"
    assert payload["matches"], "expected at least one match"
    for m in payload["matches"]:
        assert set(m.keys()) >= {
            "id", "stage", "round_label", "group", "date",
            "kickoff_local", "kickoff_utc", "team1", "team2",
            "team1_token", "team2_token", "team1_da", "team2_da",
            "venue", "city", "country", "ground_raw", "channels_da",
        }
