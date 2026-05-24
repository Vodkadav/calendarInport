"""Host venue lookup keyed by openfootball/worldcup.json `ground` strings.

openfootball uses city/metro names (not stadium names) in its `ground` field —
e.g. `"Mexico City"`, `"New York/New Jersey (East Rutherford)"`. This module
maps each ground string to a {stadium, city, country, tz} record.

`tz` is only used as a fallback for kickoff conversion. The primary path reads
the UTC offset embedded in openfootball's `time` field (e.g. `"13:00 UTC-6"`).

The 16 host cities are stable across the tournament — group stage to Final.
"""

VENUES: dict[str, dict] = {
    # USA — 11 host cities (each entry uses openfootball's exact `ground` string)
    "Atlanta": {
        "stadium": "Mercedes-Benz Stadium",
        "city": "Atlanta",
        "country": "United States",
        "tz": "America/New_York",
    },
    "Boston (Foxborough)": {
        "stadium": "Gillette Stadium",
        "city": "Foxborough",
        "country": "United States",
        "tz": "America/New_York",
    },
    "Dallas (Arlington)": {
        "stadium": "AT&T Stadium",
        "city": "Arlington",
        "country": "United States",
        "tz": "America/Chicago",
    },
    "Houston": {
        "stadium": "NRG Stadium",
        "city": "Houston",
        "country": "United States",
        "tz": "America/Chicago",
    },
    "Kansas City": {
        "stadium": "Arrowhead Stadium",
        "city": "Kansas City",
        "country": "United States",
        "tz": "America/Chicago",
    },
    "Los Angeles (Inglewood)": {
        "stadium": "SoFi Stadium",
        "city": "Inglewood",
        "country": "United States",
        "tz": "America/Los_Angeles",
    },
    "Miami (Miami Gardens)": {
        "stadium": "Hard Rock Stadium",
        "city": "Miami Gardens",
        "country": "United States",
        "tz": "America/New_York",
    },
    "New York/New Jersey (East Rutherford)": {
        "stadium": "MetLife Stadium",
        "city": "East Rutherford",
        "country": "United States",
        "tz": "America/New_York",
    },
    "Philadelphia": {
        "stadium": "Lincoln Financial Field",
        "city": "Philadelphia",
        "country": "United States",
        "tz": "America/New_York",
    },
    "San Francisco Bay Area (Santa Clara)": {
        "stadium": "Levi's Stadium",
        "city": "Santa Clara",
        "country": "United States",
        "tz": "America/Los_Angeles",
    },
    "Seattle": {
        "stadium": "Lumen Field",
        "city": "Seattle",
        "country": "United States",
        "tz": "America/Los_Angeles",
    },
    # Canada — 2 host cities
    "Toronto": {
        "stadium": "BMO Field",
        "city": "Toronto",
        "country": "Canada",
        "tz": "America/Toronto",
    },
    "Vancouver": {
        "stadium": "BC Place",
        "city": "Vancouver",
        "country": "Canada",
        "tz": "America/Vancouver",
    },
    # Mexico — 3 host cities
    "Mexico City": {
        "stadium": "Estadio Azteca",
        "city": "Mexico City",
        "country": "Mexico",
        "tz": "America/Mexico_City",
    },
    "Guadalajara (Zapopan)": {
        "stadium": "Estadio Akron",
        "city": "Zapopan",
        "country": "Mexico",
        "tz": "America/Mexico_City",
    },
    "Monterrey (Guadalupe)": {
        "stadium": "Estadio BBVA",
        "city": "Guadalupe",
        "country": "Mexico",
        "tz": "America/Monterrey",
    },
}


def lookup(ground: str | None) -> dict:
    """Return {stadium, city, country, tz} for an openfootball ground string.

    Unknown grounds return all-None fields and the caller logs a WARNING.
    """
    if ground and ground in VENUES:
        return VENUES[ground]
    return {"stadium": None, "city": None, "country": None, "tz": None}
