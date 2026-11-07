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
Source: FotMob match-by-match stats + season rankings.

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
- Understat: site offline ("We will come back soon").
- FBref and Understat loaders were removed from data_loader.py (in git history
  up to commit 891864b) — re-add only if a source becomes usable again.
- StatsBomb Open Data: working (historical competitions only).

### FotMob (primary)
Unofficial JSON endpoints used by fotmob.com itself; throttled
(`FOTMOB_REQUEST_DELAY`) and cached in data/fotmob/ (finished matches cached
forever). League ids in `config.FOTMOB_LEAGUES` (verified at runtime against
`details.name`). Loaders: `load_team_match_table`, `load_team_shots`,
`load_league_team_stats` in data_loader.py. Stat key → column mapping in
`FM_STAT_KEYS`; opponent values use the `opp_` prefix.

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
Done (Tab Confronti → Campionati): league averages for the 5 leagues and each
team's equivalent position in every league (metrics.equivalent_positions).
Raw numbers, NOT adjusted for league strength — the UI says so.

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
Role profiles live in config.ROLE_PROFILES and use metric ids from
analysis.PLAYER_METRICS, built from real FotMob player stat keys (verified
2026-11-07). Do not invent metric names.

Roles to cover (minimum set):
Portiere, Difensore centrale, Terzino difensivo, Terzino offensivo,
Mediano, Regista, Mezzala, Trequartista, Ala, Seconda punta, Centravanti.

Each role = dict of {fbref_column: weight} where weight reflects importance
for that role. Higher weight = more diagnostic for fit scoring.

---

## Formation data caveat
FotMob gives a formation for every lineup (used for roles).
StatsBomb has it reliably for covered historical competitions.
For unsupported competitions, formation analysis may be partial or require
manual annotation. Flag this in the UI when data is unavailable.

---

## Architecture
Flat repo — all .py modules in root. Subfolders only for data (cache) and tests.

| File | Role |
|------|------|
| app.py | Entry point: page config, sidebar selection → ui_common.Ctx, tab routing |
| ui_common.py | Shared UI: Ctx, errors, narrative block, league/player data gates, reference season |
| tab_*.py | One module per tab (squadra, avversario, giocatore, confronti, partita, report), each `render(ctx)` |
| config.py | Constants: league slugs, viz palette, LLM settings, tertile logic |
| data_loader.py | FotMob (primary) + StatsBomb Open Data, with local CSV/JSON caching |
| metrics.py | Subset-agnostic team metrics, league context, S&W, LLM payload |
| viz.py | Shot maps, xG race, role percentile bars, percentile radar |
| analysis.py | Opponent tiers (Level 2), roles, role fit, on/off impact (Level 3) |
| facts.py | Deterministic fact sheets + validator for the LLM narrative |
| report.py | Self-contained HTML reports (team, opponent, match) for Tab Report |
| smoke_test.py | Live end-to-end check of the FotMob pipeline per league/season |
| tests/ | Offline pytest suite on saved FotMob fixtures (tests/fixtures/fotmob) |
| llm.py | Fact-grounded narrative: Ollama local (default) + Claude API backup |

---

## LLM backend
Dual: Ollama local (default qwen3.5:9b, any installed model selectable) and
Claude API (claude-sonnet-5-5) as a paid backup only.
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
- Ollama running locally on port 11434 with qwen3.5:9b (default) and qwen2.5:14b

## Testing
- `python -m pytest -q` — offline, ~15 s (52 tests incl. Streamlit AppTest UI
  tests that run app.py on the fixtures). Run before every commit.
- `python smoke_test.py [--players] [--league "Serie A"] [--season 2025/2026]`
  — live check against FotMob; run when FotMob may have changed or before
  trusting a new league/season. Verified 2026-11-07: all 5 leagues (current
  season) + Serie A 2025/26 OK; Level 3 checked on Serie A and Premier League.
- When FotMob changes its schema: refresh tests/fixtures/fotmob from
  data/fotmob/ (same 3 Inter matches) and bump data_loader._FM_MATCH_VERSION.

## Coding conventions
- Read existing files before modifying
- Surgical edits only — never rewrite a full file unless explicitly asked
- All Streamlit state via `st.session_state`
- Heavy computations and scraping cached with `@st.cache_data`
- Scraped data saved to `data/` as CSV/JSON to avoid repeated requests
- Update README.md and requirements.txt when adding new dependencies
- Own goals are not shots: FotMob lists them in the shotmap under the conceding
  team's id; loaders skip them and match facts list them separately.
- Widget keys must not contain '/' (seasons are "2026/2027"): replace it.
- Use width="stretch", not the removed use_container_width.
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
- Tab Giocatore: Level 3 done — roles from FotMob formation + positionId
  (analysis.assign_roles), role fit = weighted league percentile vs same-role
  players (config.ROLE_PROFILES, PLAYER_MIN_MINUTES), alternative-role
  similarity (different role family only), weak links (< 30), on/off impact.
  Needs every finished league match cached (download button, ~1–4 min once).
- Tab Confronti: players of one role (up to 4, overlaid percentile radar,
  per-90 values, league leaderboard by role fit) and team vs team (metrics
  side by side with winner, opponent-type tiers).
- Competitions: 8 domestic leagues (big 5 + Serie B, Eredivisie, Liga Portugal)
  and 3 European cups (league phase only) — all pass smoke_test.py. Cross-league
  comparison uses domestic leagues only (config.FOTMOB_DOMESTIC).
- Role fit can add the previous season as reference pool (checkbox in
  Giocatore/Confronti; analysis.role_pool(..., ref)).
- Tab Report: HTML export (team / opponent / match) with embedded charts,
  verified LLM text (optional) and the fact sheet; PDF via browser print.
- Tab Partita: match report from FotMob (both teams' shots on one pitch,
  xG race, stats, top-rated players, big chances, LLM match story).
- Narrative is fact-grounded (facts.py): code writes Italian facts with exact
  numbers (F1, F2…), the LLM only rewrites them citing ids, and facts.validate
  rejects any number not in the facts (one automatic fix retry, then a
  warning in the UI). It cannot catch misinterpretations (right number,
  wrong meaning) — the facts are always shown next to the text.
- Local models: default qwen3.5:9b (best in local tests: 3/3 verified first
  try, more citations, ~6–14 s), qwen2.5:14b selectable. Claude API is a
  paid backup only — the user does not want to spend tokens for now.

---

## GitHub
Repo: leoturambar/Football-Intelligence-Hub