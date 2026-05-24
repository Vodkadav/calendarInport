"""Danish ↔ English team name mapping for qualified WC 2026 nations.

The canonical direction is DA → EN, because the merge step reads TV2 (Danish)
and needs to look up the English spelling used by openfootball/worldcup.json.

If a Danish team name from the TV2 scrape is not present here, the merge step
will log a WARNING and leave channels_da empty for that match — the user can
add the missing mapping later.

English spellings below are kept in sync with openfootball's exact strings
(e.g. `Bosnia & Herzegovina` with `&`, `USA` not `United States`). Run
`python scripts/team_names.py --check` to sanity-check coverage vs. live data.
"""

# Keys are TV2's Danish team-name spellings; values are the English forms
# used by openfootball/worldcup.json. Self-mappings (key == value) are entries
# where TV2 and openfootball use the same string.
DA_TO_EN: dict[str, str] = {
    # Hosts
    "USA": "USA",
    "Canada": "Canada",
    "Mexico": "Mexico",
    # Europe
    "Tyskland": "Germany",
    "Danmark": "Denmark",
    "Spanien": "Spain",
    "Frankrig": "France",
    "England": "England",
    "Holland": "Netherlands",
    "Nederlandene": "Netherlands",
    "Portugal": "Portugal",
    "Belgien": "Belgium",
    "Schweiz": "Switzerland",
    "Østrig": "Austria",
    "Kroatien": "Croatia",
    "Italien": "Italy",
    "Polen": "Poland",
    "Norge": "Norway",
    "Sverige": "Sweden",
    "Skotland": "Scotland",
    "Wales": "Wales",
    "Tjekkiet": "Czech Republic",
    "Ungarn": "Hungary",
    "Tyrkiet": "Turkey",
    "Serbien": "Serbia",
    "Ukraine": "Ukraine",
    "Bosnien-Hercegovina": "Bosnia & Herzegovina",
    # South America
    "Brasilien": "Brazil",
    "Argentina": "Argentina",
    "Uruguay": "Uruguay",
    "Colombia": "Colombia",
    "Ecuador": "Ecuador",
    "Paraguay": "Paraguay",
    "Chile": "Chile",
    "Peru": "Peru",
    # CONCACAF / Caribbean
    "Costa Rica": "Costa Rica",
    "Panama": "Panama",
    "Jamaica": "Jamaica",
    "Honduras": "Honduras",
    "Haiti": "Haiti",
    "Curaçao": "Curaçao",
    "Curacao": "Curaçao",  # TV2 spells without the cedilla
    # Africa
    "Sydafrika": "South Africa",
    "Marokko": "Morocco",
    "Algeriet": "Algeria",
    "Tunesien": "Tunisia",
    "Egypten": "Egypt",
    "Nigeria": "Nigeria",
    "Senegal": "Senegal",
    "Ghana": "Ghana",
    "Cameroun": "Cameroon",
    "Elfenbenskysten": "Ivory Coast",
    "Mali": "Mali",
    "Kap Verde": "Cape Verde",
    "DR Congo": "DR Congo",
    # Asia / Oceania
    "Japan": "Japan",
    "Sydkorea": "South Korea",
    "Iran": "Iran",
    "Saudi-Arabien": "Saudi Arabia",
    "Australien": "Australia",
    "Qatar": "Qatar",
    "Forenede Arabiske Emirater": "United Arab Emirates",
    "Irak": "Iraq",
    "Usbekistan": "Uzbekistan",
    "Jordan": "Jordan",
    "New Zealand": "New Zealand",
}

# Inverse for callers that need EN→DA (e.g. mapping openfootball team into Danish
# for the merged record's team*_da fields).
EN_TO_DA: dict[str, str] = {en: da for da, en in DA_TO_EN.items()}


def en_to_da(name: str) -> str | None:
    """Return the Danish spelling for an English team name, or None if unknown."""
    return EN_TO_DA.get(name)


def da_to_en(name: str) -> str | None:
    """Return the English spelling for a Danish team name, or None if unknown."""
    return DA_TO_EN.get(name)
