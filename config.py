# ── Competitions ──────────────────────────────────────────────────────────────

# FBref leagues — VERSIONE CORRETTA

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

# ── LLM ───────────────────────────────────────────────────────────────────────

LLM_BACKENDS     = ["Ollama (locale)", "Claude API"]
DEFAULT_BACKEND  = "Ollama (locale)"
CLAUDE_MODEL     = "claude-sonnet-5-5"
CLAUDE_MAX_TOKENS = 16000  # room for adaptive thinking + narrative
CLAUDE_EFFORT    = "medium"
OLLAMA_MODEL     = "qwen3.5:9b"   # default (best grounded narratives in local tests); UI lists all installed
OLLAMA_BASE_URL  = "http://localhost:11434"
LLM_MAX_TOKENS   = 1200
LLM_TEMPERATURE  = 0.4

# ── Cache ─────────────────────────────────────────────────────────────────────

DATA_DIR         = "data"
CACHE_DAYS       = 3   # disk cache lifetime for StatsBomb loaders
