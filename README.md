# FIFA 2026 World Cup — calendar import

A simple way to get every FIFA 2026 World Cup match into your phone calendar in Danish time, with the Danish broadcaster attached where it is known. It exists so you do not have to manually copy 104 fixtures off TV 2's schedule page or keep checking who is playing in the quarter-finals. The calendar auto-updates as the knockout bracket fills in — when "Winner Group A" becomes a real team name, your calendar updates itself within a day.

**Open the picker:** <https://vodkadav.github.io/calendarInport/>

---

## How to use it

Open the picker, tick the teams you care about (or pick "Whole tournament"), then choose one of the two flows below.

### Subscribe (recommended)

Subscribing means your calendar app polls our public file on its own schedule. When the knockout bracket fills in or a broadcaster is announced, you get the update for free — no re-import. Subscribed calendars also stay on **your** account only — they do not propagate to anyone you share a calendar with (see *Will this show on my partner's calendar?* below).

**Step-by-step — adding matches for your selected teams:**

1. Open <https://vodkadav.github.io/calendarInport/>.
2. Tick the teams you care about (or use **Subscribe to all 104 matches** for the whole tournament as a single calendar).
3. Click **Subscribe (webcal://) for selected teams**. You get **one link per selected team** — pick three teams, get three links. Each link becomes its own subscribed calendar in your calendar app's sidebar; you can show/hide them individually with the visibility checkbox, or toggle them all together.
4. Subscribe to each link in your calendar app (per-platform steps below).
5. The new calendars appear in your sidebar. Each has its own colour and visibility checkbox. You can toggle them on/off without unsubscribing.

If you want a **single calendar entry** in your sidebar rather than one per team, use **Subscribe to all 104 matches** instead — it's a single webcal:// URL that covers every match.

**On iPhone / iOS:**
1. Open the picker in Safari. Tick teams (or pick the whole-tournament button).
2. Tap each `webcal://` link you generated. iOS asks "Subscribe to Calendar?" — confirm.
3. Repeat per team if you picked more than one.

**On Android with Google Calendar:**
1. Open the picker on your phone or desktop. Tick teams.
2. Click **Subscribe (webcal://) for selected teams** and copy each URL it shows.
3. Replace the `webcal://` scheme with `https://` for Google.
4. On desktop Google Calendar: click the gear icon → **Settings** → **Add calendar** → **From URL** → paste the URL → **Add calendar**. Repeat per team.
5. The calendars appear on your phone within a few minutes (your Google account syncs them down).

**Important:** the published calendar auto-refreshes every few hours on our side, so when (for example) "Winner Group A" gets replaced with a real team name after the group stage ends, your subscribed calendar updates automatically. You do nothing.

### Download

Download mode gives you a one-shot `.ics` file. Good if you want a snapshot now and do not care about automatic updates.

1. Open <https://vodkadav.github.io/calendarInport/>.
2. Tick the teams you want, or "Whole tournament".
3. Click **Download .ics for selected teams**. Your browser saves a single `.ics` file.
4. Double-click the file. Your default calendar app imports the events.

**Caveat 1:** the file does **not** auto-update. If your selection includes knockout matches, the events will be stuck showing placeholder names like "Winner Group A vs Runner-up Group B" forever. If you want the bracket to resolve as the tournament progresses, use **Subscribe** instead.

**Caveat 2:** the events are imported into whichever calendar you point Google or Apple at — usually your **primary** calendar. If that primary calendar is shared with someone (family-sharing, a shared couples' calendar, anything similar), the matches appear there too. Subscribe avoids that — see the next section.

## Will this show on my partner's calendar?

Short answer: **not if you Subscribe.** Here's what each mode does to a calendar account you share with someone else (family-sharing, a manually-shared primary calendar, a couples' calendar):

- **Subscribe** adds the matches as a **new, separate calendar** that lives only on your account. It appears as its own entry in your calendar app's sidebar with its own colour and visibility checkbox. You can toggle it on/off without unsubscribing. Your partner does not see it — subscribed calendars in Google Calendar and iOS Calendar are per-user and not shared automatically. You would have to deliberately share that calendar with them for it to appear on their side.
- **Download** adds the matches as events **inside whichever calendar you import them into** — usually your primary. If that primary calendar is shared with your partner, the imported events propagate and appear visible on their side too.

If your goal is "matches on my phone, nothing on my partner's phone", use **Subscribe**.

## What you get

- All **104 matches** — group stage (72) plus knockout stage (32).
- Times in **Danish time** (Europe/Copenhagen), with the timezone correctly declared so events shift if you travel.
- Match titles in **English** — for example `Germany vs Denmark`.
- **Venue and city** in the LOCATION field, so adding the match to your calendar gives you the venue at a glance.
- **Danish broadcaster** in the DESCRIPTION field where known (TV 2, DR, TV 2 Sport). Coverage improves as TV 2 publishes their full schedule closer to the tournament — early on, knockout matches will not have a broadcaster yet.
- Each event is a **2-hour block** starting at kickoff.

## Knockout stage

The knockout bracket only resolves as the group stage progresses. Until then, knockout events still appear in your calendar — with placeholder team names.

**Before each round resolves**, you will see titles like:

- `Winner Group A vs Runner-up Group B` (round of 16)
- `Winner of match 49 vs Winner of match 50` (quarter-finals onward)
- `Third place A/B/C/D/F` (placement-based slots)

The date, kickoff time, venue, and city are correct from day one. Only the team names are placeholders.

**After each match**, the relevant placeholder is replaced with the real team names within about 24 hours — the next time the daily refresh runs.

**This is why we recommend Subscribe over Download:** a downloaded `.ics` would freeze your calendar at "Winner Group A" forever, because there is nothing polling for updates.

## Privacy

- **No signup, no email, no account.**
- **No tracking, no analytics, no cookies.**
- The picker is a static HTML page. Selecting teams happens entirely inside your browser; nothing is sent anywhere.
- Subscribing publishes nothing about you — your calendar app (Google, Apple, etc.) polls a public URL on its own schedule. We do not see who is subscribed.
- The full source — including the GitHub Actions workflow that builds the calendar files — is in this repository.

---

## For maintainers

### Architecture

```
                      ┌──────── GitHub Actions cron (daily) ────────┐
                      │                                              │
                      ▼                                              │
   openfootball/worldcup.json  ─┐                                    │
   (raw GitHub, CC0)            │                                    │
                                ├──> refresh.py ──> data/merged.json │
   TV2 sendeplan (scrape)       │       (merge by date+team pair,    │
   (HTML, fair-use personal)   ─┘        DA↔EN name map applied)     │
                                                │                    │
                                                ▼                    │
                              data/merged.json  +  ics/{team}.ics    │
                              ics/all.ics                            │
                                                │                    │
                                                ▼                    │
                              git commit + push to gh-pages branch ──┘
                                                │
                                                ▼
                                  GitHub Pages serves them at
                                  https://vodkadav.github.io/calendarInport/

   ┌──────────────────────────────────────────────────────────────────┐
   │  Friend opens calendar.html (single file, sent / hosted)         │
   │    on load: fetch data/merged.json                               │
   │    show team-picker (grouped by group A-L)                       │
   │    on submit:                                                    │
   │      (a) download merged .ics built in-browser (one-shot)        │
   │      (b) OR copy webcal:// URL(s) for subscription (auto-update) │
   └──────────────────────────────────────────────────────────────────┘
```

Two scripts (`refresh.py`, `generate.py`) plus one static HTML page (`web/calendar.html`). The GitHub Actions cron runs daily, regenerates everything, and force-pushes the result to the `gh-pages` branch. There is no backend service, no database, and no per-user state — the picker is a single file that fetches a public JSON and builds calendar links in the browser.

### Local development

- Python **3.11+**.
- Install dependencies: `pip install -r requirements.txt`
- Refresh the merged dataset: `python scripts/refresh.py` → writes `data/merged.json`.
- Regenerate calendars: `python scripts/generate.py` → writes `ics/*.ics` and `data/teams.json`.
- Preview the picker locally: `python -m http.server 8765` then open <http://localhost:8765/web/calendar.html>.

Opening `web/calendar.html` directly via `file://` does not work in Chrome — the browser blocks the `fetch()` of `data/merged.json` under its file-URL CORS policy. The `python -m http.server` workaround is the simplest fix; any other static server works too.

### How the daily refresh works

- The GitHub Actions cron fires at **05:00 UTC daily** (`.github/workflows/refresh.yml`).
- The workflow runs `pytest` first as a hard gate — if any test fails, nothing is deployed.
- On green: it runs `scripts/refresh.py`, then `scripts/generate.py`, then force-pushes the contents of `_site/` (the picker HTML plus the regenerated JSON and `.ics` files) to the `gh-pages` branch.
- GitHub Pages serves the `gh-pages` branch root at <https://vodkadav.github.io/calendarInport/>.
- Subscribed calendars on friends' devices poll that URL every few hours. They pick up the new data without anyone doing anything.

### Fixing a Danish team-name mismatch

When `refresh.py` logs a line like:

```
WARNING: no Danish→English mapping for "Bosnien-Hercegovina"
```

it means the TV 2 page used a Danish spelling we have not seen before, and that team's matches did not merge with TV 2's broadcaster data. To fix:

1. Open `scripts/team_names.py`.
2. Add the Danish spelling exactly as printed in the warning, mapped to the English spelling that `openfootball/worldcup.json` uses. Example: `"Bosnien-Hercegovina": "Bosnia and Herzegovina"`.
3. Run `python -m pytest tests/test_refresh.py` to confirm nothing else broke.
4. Run `python scripts/refresh.py` locally and verify the warning is gone.
5. Commit and push to `main`. The next daily refresh picks up the new mapping.

### Tests

- Full suite: `python -m pytest -q`
- The suite covers openfootball parsing, the TV 2 scrape, merge logic, RFC 5545 ICS compliance, the byte-for-byte VTIMEZONE match between `scripts/generate.py` and `web/calendar.html`, the GitHub Actions workflow structure, picker-HTML invariants, the `teams.json` schema, and this README.
- No merge with failing tests. The cron workflow gates on green pytest before it deploys.

### Deploy

- Pushing to `main` triggers nothing by itself.
- The cron workflow runs nightly and rebuilds the `gh-pages` branch. You can also trigger it manually from the GitHub Actions tab via **Run workflow**.
- `gh-pages` is **force-pushed every run** — never commit anything to it manually, your work will be wiped on the next refresh.

## Credits & data sources

- **Fixtures:** [openfootball/worldcup.json](https://github.com/openfootball/worldcup.json) — CC0, community-maintained. Used as the source of truth for match dates, kickoff times, venues, and the knockout-bracket structure (including the `W101`-style tokens that resolve as the tournament progresses).
- **Danish broadcaster info:** scraped from TV 2's `sport.tv2.dk/fodbold/vm/sendeplan` page. Personal, non-redistributive use under Danish ophavsretsloven §11b (text-and-data-mining exception for non-commercial purposes). This repository publishes derived event records — channel name only — not the original page content. No data dumps are republished. **If you fork this project and run it at scale or for any commercial purpose, contact TV 2 first.**
- **Pattern inspiration:** [baires/fifa-cal-2026](https://github.com/baires/fifa-cal-2026) — CC0. Source of the daily-cron + per-team-ICS subscription architecture.

## License

MIT — see [`LICENSE`](LICENSE). Note the TV 2 caveat above: the **code** in this repository is MIT-licensed, but the **broadcaster data** it scrapes belongs to TV 2 and is republished here under personal fair-use only.
