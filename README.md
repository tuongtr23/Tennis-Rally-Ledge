# Rally Ledger

Rally Ledger is a men's tennis tracking website. It combines tour information pages (events, draws, players, rankings, head-to-heads) with a match view that follows a match point by point, with a running score, match clock, statistics and a court view of each rally.

It is a personal learning project. The whole site is one static HTML page with its data files, so it runs on any static host, such as GitHub Pages or Cloudflare Pages, with no build step and no server.

## Pages

| Page | What it shows |
|---|---|
| Home | This week's event, the next event, the top 5, recent champions and a scores panel |
| Event | Any tour event from 2010 to now: schedule and results by day, players and seeds, and the draw rebuilt from results |
| Live | Point-by-point replays of charted matches, a simulated live demo event, and any match since 2010 as a simulated live match that ends at its real final score |
| Players | Profiles for the current top 100 and the leading title winners: bio, titles, season-by-season activity and a ranking history chart |
| Rankings | Top 100 in a sortable table with filters |
| H2H | Two players side by side, with their tour-level meetings since 2010 |
| Compare | Big-title totals for any group of players |
| Tournaments | The 2026 calendar by month, with search and a downloadable calendar PDF |
| Map | All 2026 events on a world map with dates, category and status |

Players and matches are chosen with a search bar and a suggestion list. Every page has light and dark modes and three design styles (IBM Carbon, GitHub Primer and Microsoft Fluent 2).

## The court view

On the Live page, each point is drawn on a canvas court that can be shown horizontally or vertically. Every shot travels from the hitter's contact point to its bounce and on to the opponent's contact point. The players run to reach each ball in time, drift back toward the middle between shots, and chase winners they cannot reach. The ball has a ground shadow, a short trail and a dashed line to where it will land; bounces outside the singles court are marked in red. For charted matches, the ball path comes from the recorded shot directions, so landing spots are approximate. The demo event's rallies are simulated.

## Simulated live matches

Any match in the archive with a normal completed score can be watched point by point with **Watch it live (simulated)**. The set scores and tiebreak scores are real. The order of games and points, the rallies and the running statistics are generated. When the match's serve statistics are recorded, the simulation follows them (first serves in, aces, double faults and points won on serve). The same match always plays out the same way. Retirements, walkovers and match tiebreaks such as the Laver Cup's 10-point deciders are not simulated.

## Data and credits

| Data | Source | Notes |
|---|---|---|
| Tour-level matches, 2010 to now | [Tennismylife (TML) ATP database](https://github.com/Tennismylife/TML-Database) | Scores, seeds, ranks, match times and serve statistics. Non-commercial use only |
| Point-by-point matches | [Match Charting Project](https://github.com/JeffSackmann/tennis_MatchChartingProject) by Jeff Sackmann and volunteers | CC BY-NC-SA 4.0. Only matches that volunteers charted, not full draws |
| Latest matches | Published results (ATP Tour, Tennis Majors, AP) | Entered by hand in `tools/manual_matches.json` until the database catches up; no serve statistics |
| 2026 calendar | Wikipedia, "2026 ATP Tour" | |
| Rankings | Tennis Majors and ESPN lists | A fixed copy that does not update by itself |

Points per event in player activity are estimated from the standard ATP points table for the round reached. The Harbor Indoor Open on the Live page is a simulated demo event and is labelled as one.

This site is not affiliated with the ATP. Because of the data licences, it must stay non-commercial and keep its credit lines.

## Run it locally

Open `site/index.html` in Chrome, Edge, Firefox or Safari. An internet connection is needed for the fonts and the map library. Phone file previews do not run JavaScript, so open the hosted site on a phone instead.

## Publish it

- **GitHub Pages:** `.github/workflows/pages.yml` publishes the `site` folder each time `main` changes. Set **Settings > Pages > Source** to **GitHub Actions**. Full steps are in `GITHUB_SETUP.md`.
- **Cloudflare Pages:** use `site` as the output directory with no build command. Steps are in `DEPLOY.md`.

## Project layout

```
site/
  index.html              the whole website: HTML, CSS and JavaScript
  data/y2010.js ...       one match file per season, loaded when first needed
  data/<event>.js         point-by-point charted matches, one file per event
  tour-calendar-2026.pdf  calendar download
  photos/                 optional player photos (see photos/README.txt)
tools/
  build_archive.py        builds the season files from the TML database
  build_charted.py        builds the point-by-point files from the Match Charting Project
  add_manual.py           merges hand-entered matches into the season files
  manual_matches.json     the hand-entered matches
  players.json            player list used by build_archive.py
tennis-worker/            Cloudflare Worker for a live feed (not yet connected to the site)
.github/workflows/        GitHub Pages publishing
```

## Update the data

```
python3 tools/build_archive.py <TML folder> site/data tools/players.json
python3 tools/add_manual.py tools/manual_matches.json site/data
python3 tools/build_charted.py <charting CSV folder> site/data 30
```

After `build_charted.py`, paste the contents of `site/data/index.json` into the `const CH=` line of `site/index.html`.

## Not built yet

- A live score feed. The Worker in `tennis-worker/` is written but not deployed or connected.
- Win-loss records, prize money and full head-to-head records before 2010.
- Sponsors and news sections on the home page.
