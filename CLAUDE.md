# Football Intelligence Hub — Project Context

## Purpose
Streamlit app for tactical football analysis. Given a team, competition, and
a user-selected set of matches, it produces: strengths/weaknesses report,
heatmaps, pressing maps, passing networks, player-role fit analysis, and LLM
narrative coaching insights.

The guiding question is always: "With what I have, what should I improve
and what should I change?" — Moneyball logic applied to tactical analysis,
without the transfer-scouting component.

---

## Analysis framework (three levels)

### Level 1 — What the team does (own patterns)
Aggregate stats over a selected match set: possession style, verticality,
defensive intensity, attacking threat, set piece effectiveness.
Source: FBref match-by-match + season stats.

### Level 2 — How the team reacts to context (conditional S&W)
Performance split by opponent type. Answers questions like:
"Does this team struggle against high-press sides?"
"Does it perform better with formation X than Y?"

**Opponent categorization principle:**
Every opponent "type" is defined by a numeric metric, divided into tertiles
(low / medium / high) across the competition. Tertile thresholds are computed
on the fly from the full league distribution — not hardcoded.

| Opponent type        | Metric proxy (FotMob)                         | Direction |
|----------------------|-----------------------------------------------|-----------|
| High/low press       | PPDA stimato (see metrics.summarize)          | low = high press |
| Defensive block      | xG conceded per match                         | low = defensive/closed |
| Counter-attack speed | not available — no carries/transition data    | — |
| Possession-based     | Possession % avg                              | high = possession team |

**Implementation note (verified 2026-11-07):** FotMob gives per-match
possession, xG (open/set play), shots, big chances, passes split by own/opp
half, tackles, interceptions, fouls, duels, shot coordinates and formations —
but no event locations for defensive actions and no progressive carries.
PPDA is therefore an estimate: opponent passes in their own half ÷
(tackles + interceptions + fouls). The tertile pattern stays constant.

### Level 3 — Who matters and how much (player contribution)
- Key player identification (remove-one impact on team metrics)
- Position fit: player's stats vs. ideal profile for their role
- Position mismatch: player might perform better in a different role
- Weak link: player significantly below role benchmark

---

## Data sources

### Source status (checked 2026-11-07)
- FotMob: working → **primary source** for current seasons (2018/19 onward).
- FBref: behind a Cloudflare challenge; soccerdata + Opera hangs. Do not try
  to bypass it. Old cached CSVs in data/ (Serie A 24/25) still load.
- Understat: site offline ("We will come back soon"); its loaders fail.
- StatsBomb Open Data: working (historical competitions only).

### FotMob (primary)
Unofficial JSON endpoints used by fotmob.com itself; throttled
(`FOTMOB_REQUEST_DELAY`) and cached in data/fotmob/ (finished matches cached
forever). League ids in `config.FOTMOB_LEAGUES` (verified at runtime against
`details.name`). Loaders: `load_team_match_table`, `load_team_shots`,
`load_league_team_stats` in data_loader.py. Stat key → column mapping in
`FM_STAT_KEYS`; opponent values use the `opp_` prefix.

### FBref via soccerdata (currently blocked)
Aggregate and match-level stats for current seasons, all major leagues.

**Native leagues (verified from soccerdata docs):**
'Big 5 European Leagues Combined'
'ENG-Premier League'
'ESP-La Liga'
'FRA-Ligue 1'
'GER-Bundesliga'
'ITA-Serie A'
'INT-World Cup'
'INT-Women's World Cup'
'INT-European Championship'   # added in recent soccerdata versions
Champions League requires custom league_dict.json config — add later.
Usage: `sd.FBref('ITA-Serie A', '2425')`

### Understat (xG layer)
Shot-level data with x/y coordinates for top 5 leagues, current seasons.
Leagues: EPL, La_liga, Bundesliga, Serie_A, Ligue_1
Usage: direct requests to understat.com API (no auth required)

### StatsBomb Open Data (event-level layer)
Event-level data (every pass, press, shot with coordinates). Free but
historical only — no current seasons. Use when available for rich
visualizations (Voronoi, set piece analysis, passing networks).

**Do not hardcode competition IDs.** Load at runtime:
```python
from statsbombpy import sb
competitions = sb.competitions()  # returns full updated list as DataFrame
```
Notable competitions available: UEFA Euro 2020 (55/43), UEFA Euro 2024
(55/282), Women's Euro 2025 (53/315), Copa America 2024 (223/x).
Verify IDs at runtime, not from memory.

---

## Benchmarking
Compare team stats against:
- Own league average (same season)
- Other league averages (e.g. "can this Serie A team compete with PL sides?")
FBref supports this natively — pull multi-league stats and normalize per-90.

---

## Match metadata and dynamic analysis

Every match is stored with a full metadata record alongside stats:
- date, matchday, competition, season
- home / away
- opponent
- result (W/D/L), goals for/against
- formation (where available)
- coach_tag: manually annotated label applied from a given match onward
  (e.g. "Gasperini era", "post-Conte") — set once in the UI, stored in
  data/match_tags.json

The match selector in Tab Squadra exposes all metadata fields as
filters and grouping dimensions. Any subset of matches becomes an
analysis unit. This enables:
- Home vs. away splits
- First half of season vs. second half
- Pre/post coach change (via coach_tag)
- Last N matches (form analysis)
- By opponent type (see tertile categorization above)
- Any combination of the above

Comparisons ("before vs. after") work by running the same analysis
pipeline on two user-defined match subsets and displaying results
side by side. The pipeline is subset-agnostic — it always receives
a filtered DataFrame and returns metrics.

---

## Role profiles (player analysis)
Define role profiles AFTER first FBref scraping session, once real column
names are known. Do not invent metric names — use exact FBref column headers.

Roles to cover (minimum set):
Portiere, Difensore centrale, Terzino difensivo, Terzino offensivo,
Mediano, Regista, Mezzala, Trequartista, Ala, Seconda punta, Centravanti.

Each role = dict of {fbref_column: weight} where weight reflects importance
for that role. Higher weight = more diagnostic for fit scoring.

---

## Formation data caveat
FBref has formation per match but not always in clean parseable form.
StatsBomb has it reliably for covered competitions.
For unsupported competitions, formation analysis may be partial or require
manual annotation. Flag this in the UI when data is unavailable.

---

## Architecture
Flat repo — all .py modules in root. Subfolders only for data (cache).

| File | Role |
|------|------|
| app.py | Streamlit UI, tab routing |
| config.py | Constants: league slugs, viz palette, LLM settings, tertile logic |
| data_loader.py | FotMob + FBref + Understat + StatsBomb, with local CSV/JSON caching |
| metrics.py | Subset-agnostic team metrics, league context, S&W, LLM payload |
| viz.py | Pitch visualizations via mplsoccer: heatmaps, passing networks, Voronoi |
| analysis.py | S&W scoring, opponent categorization, player-role fit, benchmarking |
| llm.py | Dual backend: Anthropic API + Ollama local |

---

## LLM backend
Dual: Claude API (claude-sonnet-5-5) and Ollama local (qwen2.5:14b).
Toggle in UI sidebar. Default: Ollama.
All calls route through `llm.call_llm(prompt, backend, system)`.
LLM role: turn numeric outputs into narrative coaching language.
Example: not "PPDA=8.3" but "Milan's press intensity ranks in the bottom
third of Serie A — opponents move through midfield with minimal resistance."

---

## Dev environment
- Windows, Conda env: `football`
- Python 3.11
- ANTHROPIC_API_KEY set as system env var via `setx`
- Ollama running locally on port 11434 with qwen2.5:14b

## Coding conventions
- Read existing files before modifying
- Surgical edits only — never rewrite a full file unless explicitly asked
- All Streamlit state via `st.session_state`
- Heavy computations and scraping cached with `@st.cache_data`
- Scraped data saved to `data/` as CSV/JSON to avoid repeated requests
- Update README.md and requirements.txt when adding new dependencies
- Before hardcoding any reference value (IDs, slugs, column names, metrics):
  search for the authoritative source or verify at runtime from the API

---

## Build order
1. Tab Squadra (MVP)
   - Match selector (competition + season + match subset)
   - Level 1: aggregate stats, heatmaps, pressing map
   - Level 2: opponent-type splits (tertile categorization)
   - LLM narrative: S&W in coaching language
2. Tab Giocatore — role fit, mismatch detection, weak link
3. Tab Confronti — cross-team role comparisons, overlaid radars
4. Tab Partita — event-level match report (StatsBomb where available)
5. Tab Report — exportable deliverables (Italia post-mortem, scouting report,
   match report, formation comparison)

### Status (2026-11-07)
- Tab Squadra: Level 1 + Level 2 done on FotMob data (filters, comparisons,
  league ranks, opponent-type splits in analysis.py, sample-size warnings).
- Tab Avversario (added): next-opponent report — profile tiers, shot zones,
  league S&W, record vs teams with our profile, LLM pre-match brief.
- Local LLM (qwen2.5:14b) misreads payload numbers (e.g. wrong formation);
  treat its narrative as a draft. Claude backend untested (no API credit).

---

## GitHub
Repo: leoturambar/Football-Intelligence-Hub