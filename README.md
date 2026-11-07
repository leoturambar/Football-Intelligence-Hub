# Football Intelligence Hub

Tactical football analysis platform powered by data and LLM narrative.
Given a team, competition and time range, the app generates strengths & weaknesses reports,
positional heatmaps, pressing maps, passing networks, and player-role fit analysis —
with an LLM coach that turns numbers into concrete decisions.

## Features

- **Squadra** — key metrics, shot maps, league ranks, strengths & weaknesses, performance by
  opponent type (pressing, possession, attack, defence tertiles), subset filters and comparisons
- **Avversario** — next-opponent report: profile, where they create/concede, record vs teams like yours
- **Giocatore** — roles from lineups, role fit vs league peers, weak links, with/without impact
- **Confronti** — players of a role (overlaid radar, leaderboard), team vs team, league vs league
- **Partita** — both teams' shots, xG race, stats, top-rated players
- **Report** — self-contained HTML export of team, opponent and match reports (print to PDF)
- **Narrative** — local LLM writes only from code-computed facts; every number is checked

## Data sources

| Source | Coverage | Used for | Status (Nov 2026) |
|--------|----------|----------|-------------------|
| FotMob | Top 5 leagues, 2018/19 → current season | Match stats, xG, shot maps, formations, league rankings | Primary |
| FBref | All major leagues | — | Blocked by Cloudflare; loader removed |
| Understat | Top 5 leagues | — | Site offline; loader removed |
| StatsBomb Open Data | Historical competitions (Euro 2020, etc.) | Event-level viz | Working |

FotMob data comes from the unofficial JSON endpoints its website uses; requests are
throttled and cached in `data/fotmob/`. Personal / educational use only.

## Stack

Python · Streamlit · Pandas · mplsoccer · statsbombpy · Ollama · Anthropic API (optional)

## Setup

```bash
git clone https://github.com/leoturambar/football-intelligence-hub.git
cd football-intelligence-hub

conda create -n football python=3.11
conda activate football
pip install -r requirements.txt

streamlit run app.py
```

**Anthropic API key** — set once as a system environment variable on Windows:
```bash
setx ANTHROPIC_API_KEY "sk-ant-..."
```
Reopen the terminal after running `setx`.

**Ollama** — install from https://ollama.com, then:
```bash
ollama pull qwen3.5:9b      # default narrative model
ollama pull qwen2.5:14b     # optional alternative
```

## Tests

```bash
python -m pytest -q tests          # offline, uses saved FotMob fixtures
python smoke_test.py               # live check of all 5 leagues
```

## Launch from desktop (Windows)

Double-click `launch.bat`.

## Project structure

```
football-intelligence-hub/
├── app.py
├── config.py
├── data_loader.py
├── metrics.py
├── viz.py
├── analysis.py
├── facts.py
├── report.py
├── smoke_test.py
├── tests/
├── llm.py
├── data/
├── CLAUDE.md
├── README.md
├── requirements.txt
├── launch.bat
└── LICENSE
```