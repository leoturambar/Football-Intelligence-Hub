# ── Competitions ──────────────────────────────────────────────────────────────

# FBref leagues — VERSIONE CORRETTA
FBREF_LEAGUES = {
    "Serie A":              "ITA-Serie A",
    "Premier League":       "ENG-Premier League",
    "Bundesliga":           "GER-Bundesliga",
    "La Liga":              "ESP-La Liga",
    "Ligue 1":              "FRA-Ligue 1",
    "Big 5 (combinato)":   "Big 5 European Leagues Combined",
    # Champions League: richiede config custom, si aggiunge dopo
}

# StatsBomb — NON hardcodare gli ID, si caricano a runtime
# In data_loader.py useremo: sb.competitions() per ottenere la lista aggiornata
# Qui teniamo solo label human-readable come riferimento
STATSBOMB_NOTABLE = [
    "UEFA Euro 2020",
    "UEFA Euro 2024",
    "FIFA World Cup 2022",
    "UEFA Champions League",
    "Copa America",
]

# Role profiles — da completare in Claude Code dopo il primo scraping FBref
# I 7 ruoli attuali sono un punto di partenza, ma mancano:
# Portiere, Difensore centrale, Regista — da aggiungere quando si conoscono le colonne reali

# Understat league slugs
UNDERSTAT_LEAGUES = {
    "Serie A":        "Serie_A",
    "Premier League": "EPL",
    "Bundesliga":     "Bundesliga",
    "La Liga":        "La_liga",
    "Ligue 1":        "Ligue_1",
}

# ── Role profiles ─────────────────────────────────────────────────────────────
# Metric weights for player-role fit scoring (higher weight = more important for role)
# All metrics are per-90 from FBref

ROLE_PROFILES = {
    "Terzino offensivo": {
        "progressive_carries_per90":  1.2,
        "crosses_per90":              1.5,
        "progressive_passes_per90":   1.0,
        "tackles_per90":              0.8,
        "interceptions_per90":        0.6,
    },
    "Terzino difensivo": {
        "tackles_per90":              1.5,
        "interceptions_per90":        1.5,
        "clearances_per90":           1.2,
        "progressive_carries_per90":  0.5,
        "crosses_per90":              0.4,
    },
    "Mediano": {
        "progressive_passes_per90":   1.5,
        "tackles_per90":              1.2,
        "interceptions_per90":        1.0,
        "progressive_carries_per90":  0.8,
        "key_passes_per90":           0.8,
    },
    "Mezzala": {
        "progressive_carries_per90":  1.4,
        "key_passes_per90":           1.3,
        "progressive_passes_per90":   1.2,
        "tackles_per90":              0.8,
        "shots_per90":                0.9,
    },
    "Trequartista": {
        "key_passes_per90":           2.0,
        "shot_creating_actions_per90":1.8,
        "progressive_carries_per90":  1.3,
        "xA_per90":                   1.5,
        "tackles_per90":              0.3,
    },
    "Ala": {
        "progressive_carries_per90":  1.6,
        "key_passes_per90":           1.2,
        "xA_per90":                   1.3,
        "shots_per90":                1.0,
        "dribbles_completed_per90":   1.4,
    },
    "Centravanti": {
        "goals_per90":                2.0,
        "xG_per90":                   1.8,
        "shots_on_target_per90":      1.5,
        "aerial_duels_won_pct":       1.2,
        "progressive_carries_per90":  0.6,
    },
}

# ── Visualization ─────────────────────────────────────────────────────────────

PITCH_COLOR    = "#1a1a2e"
LINE_COLOR     = "#4a4a6a"
HOME_COLOR     = "#5B9BF5"
AWAY_COLOR     = "#F55B5B"
NEUTRAL_COLOR  = "#F5C85B"
ACCENT_COLOR   = "#A8E6CF"
HEATMAP_CMAP   = "YlOrRd"
RADAR_COLOR    = "#5B9BF5"
RADAR_BG       = "#1a1a2e"

# ── LLM ───────────────────────────────────────────────────────────────────────

LLM_BACKENDS     = ["Ollama (locale)", "Claude API"]
DEFAULT_BACKEND  = "Ollama (locale)"
CLAUDE_MODEL     = "claude-sonnet-4-20250514"
OLLAMA_MODEL     = "qwen2.5:14b"
OLLAMA_URL       = "http://localhost:11434/api/generate"
LLM_MAX_TOKENS   = 900
LLM_TEMPERATURE  = 0.4

# ── Cache ─────────────────────────────────────────────────────────────────────

DATA_DIR         = "data"
CACHE_DAYS       = 3   # re-scrape FBref after N days