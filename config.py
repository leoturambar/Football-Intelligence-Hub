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

# FotMob league IDs (primary source for current seasons since Nov 2026:
# FBref is behind a Cloudflare challenge, Understat is offline).
# Verified 2026-11-07 via /api/data/leagues?id=… → details.name.
FOTMOB_LEAGUES = {
    "Serie A":        55,
    "Premier League": 47,
    "La Liga":        87,
    "Bundesliga":     54,
    "Ligue 1":        53,
}
FOTMOB_REQUEST_DELAY = 0.6   # seconds between live FotMob requests
FOTMOB_LEAGUE_CACHE_HOURS = 12

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
    "Serie A":        "Serie A",
    "Premier League": "EPL",
    "Bundesliga":     "Bundesliga",
    "La Liga":        "La liga",
    "Ligue 1":        "Ligue 1",
}

# FBref and Understat use different names for some clubs.
# Keys are FBref names; values are the exact strings Understat expects in URLs.
UNDERSTAT_TEAM_NAMES = {
    "Inter":     "Inter",
    "Milan":     "AC Milan",
    "Roma":      "AS Roma",
    "Napoli":    "Napoli",
    "Juventus":  "Juventus",
}

# ── Role profiles ─────────────────────────────────────────────────────────────
# Player-role fit (analysis.py, Level 3). Keys are metric ids defined in
# analysis.PLAYER_METRICS (built from FotMob per-match player stats, per 90
# or %). Weight = how diagnostic the metric is for the role. Lower-is-better
# metrics (dribbled_past, dispossessed, fouls) are inverted before weighting.
# Roles are derived from FotMob lineup positions + formation (analysis.assign_roles);
# FotMob cannot separate e.g. regista from mediano, so roles are slightly coarser
# than the list in CLAUDE.md.

ROLE_PROFILES = {
    "Portiere": {
        "goals_prevented": 1.5, "save_pct": 1.0, "saves": 0.4,
        "long_ball_pct": 0.5, "pass_pct": 0.5,
    },
    "Difensore centrale": {
        "aerial_pct": 1.0, "aerials": 0.8, "clearances": 0.8, "interceptions": 0.8,
        "tackles": 0.6, "ground_pct": 0.7, "pass_pct": 0.6, "long_balls": 0.5,
        "dribbled_past": 0.6,
    },
    "Terzino": {
        "tackles": 0.8, "interceptions": 0.6, "recoveries": 0.6, "final_third": 0.8,
        "crosses": 0.7, "chances": 0.6, "ground_pct": 0.5, "dribbled_past": 0.6,
    },
    "Esterno a tutta fascia": {
        "crosses": 0.9, "chances": 0.8, "final_third": 0.8, "xa": 0.7,
        "box_touches": 0.6, "dribbles": 0.6, "tackles": 0.6, "recoveries": 0.5,
    },
    "Mediano": {
        "recoveries": 1.0, "tackles": 0.9, "interceptions": 0.9, "pass_pct": 0.8,
        "ground_pct": 0.7, "final_third": 0.5, "dispossessed": 0.6, "fouls": 0.3,
    },
    "Centrocampista centrale": {
        "final_third": 1.0, "pass_pct": 0.8, "chances": 0.8, "xa": 0.7,
        "recoveries": 0.7, "touches": 0.6, "tackles": 0.5, "dribbles": 0.4,
    },
    "Esterno di centrocampo": {
        "crosses": 0.8, "chances": 0.8, "dribbles": 0.8, "xa": 0.8,
        "recoveries": 0.5, "tackles": 0.5, "box_touches": 0.5,
    },
    "Trequartista": {
        "chances": 1.0, "xa": 1.0, "xg": 0.8, "box_touches": 0.8,
        "dribbles": 0.7, "final_third": 0.6, "dispossessed": 0.4,
    },
    "Ala": {
        "dribbles": 1.0, "xa": 0.9, "box_touches": 0.9, "xg": 0.8,
        "chances": 0.8, "crosses": 0.5, "dispossessed": 0.4,
    },
    "Punta": {
        "xg": 1.0, "box_touches": 0.9, "shots": 0.7, "xa": 0.6,
        "chances": 0.5, "dribbles": 0.5, "aerials": 0.4,
    },
    "Centravanti": {
        "xg": 1.0, "box_touches": 0.9, "shots": 0.8, "goals": 0.6,
        "aerials": 0.6, "aerial_pct": 0.4, "xa": 0.3,
    },
}

PLAYER_MIN_MINUTES = 300   # minimum league minutes to be scored / benchmarked
ROLE_MIN_POOL      = 8     # minimum players in a role to compute percentiles

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
CLAUDE_MODEL     = "claude-sonnet-5-5"
CLAUDE_MAX_TOKENS = 16000  # room for adaptive thinking + narrative
CLAUDE_EFFORT    = "medium"
OLLAMA_MODEL     = "qwen2.5:14b"
OLLAMA_URL       = "http://localhost:11434/api/generate"
LLM_MAX_TOKENS   = 900
LLM_TEMPERATURE  = 0.4

# ── FBref scraping config ─────────────────────────────────────────────────────

# comp_id + URL slug needed to build FBref league URLs.
# URL pattern: fbref.com/en/comps/{comp_id}/{season}/{stat_slug}/{season}-{league_slug}-Stats
FBREF_LEAGUE_URLS = {
    "ITA-Serie A":                     {"comp_id": 11,     "league_slug": "Serie-A"},
    "ENG-Premier League":              {"comp_id": 9,      "league_slug": "Premier-League"},
    "GER-Bundesliga":                  {"comp_id": 20,     "league_slug": "Bundesliga"},
    "ESP-La Liga":                     {"comp_id": 12,     "league_slug": "La-Liga"},
    "FRA-Ligue 1":                     {"comp_id": 13,     "league_slug": "Ligue-1"},
    "Big 5 European Leagues Combined": {"comp_id": "Big5", "league_slug": "Big-5-European-Leagues"},
}

# stat_type → URL path segment  (e.g. "standard" → ".../stats/...")
STAT_TYPE_SLUGS = {
    "standard":   "stats",
    "shooting":   "shooting",
    "passing":    "passing",
    "defense":    "defense",
    "possession": "possession",
    "misc":       "misc",
    "keeper":     "keepers",
}

# stat_type → HTML table-id key used by FBref
# Squad table id:  stats_squads_{key}_for
# Player table id: stats_{key}
STAT_TYPE_TABLE_KEYS = {
    "standard":   "standard",
    "shooting":   "shooting",
    "passing":    "passing",
    "defense":    "defense",
    "possession": "possession",
    "misc":       "misc",
    "keeper":     "keeper",
}

# ── Cache ─────────────────────────────────────────────────────────────────────

DATA_DIR         = "data"
CACHE_DAYS       = 3   # re-scrape FBref after N days

# ── Browser ───────────────────────────────────────────────────────────────────

BROWSER_PATH     = r"C:\Users\maver\AppData\Local\Programs\Opera\opera.exe"