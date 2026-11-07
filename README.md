# Football Intelligence Hub

Tactical football analysis platform powered by data and LLM narrative.
Given a team, competition and time range, the app generates strengths & weaknesses reports,
positional heatmaps, pressing maps, passing networks, and player-role fit analysis —
with an LLM coach that turns numbers into concrete decisions.

## Features

- Team analysis: S&W report, heatmaps, pressing intensity, passing structure
- Player-role fit: radar vs. ideal profile per position
- Role comparisons: overlay players across teams for the same position
- Match report: event-level viz when StatsBomb data is available (Voronoi, set pieces, transitions)
- Exportable reports: Italia post-mortem, scouting reports, match reports

## Data sources

| Source | Coverage | Used for | Status (Nov 2026) |
|--------|----------|----------|-------------------|
| FotMob | Top 5 leagues, 2018/19 → current season | Match stats, xG, shot maps, formations, league rankings | Primary |
| FBref | All major leagues | Aggregate stats | Blocked by Cloudflare — cached CSVs only |
| Understat | Top 5 leagues | xG | Site offline |
| StatsBomb Open Data | Historical competitions (Euro 2020, etc.) | Event-level viz | Working |

FotMob data comes from the unofficial JSON endpoints its website uses; requests are
throttled and cached in `data/fotmob/`. Personal / educational use only.

## Stack

Python · Streamlit · Pandas · Plotly · mplsoccer · soccerdata · Anthropic API · Ollama

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
ollama pull qwen2.5:14b
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
├── llm.py
├── data/
├── CLAUDE.md
├── README.md
├── requirements.txt
├── launch.bat
└── LICENSE
```