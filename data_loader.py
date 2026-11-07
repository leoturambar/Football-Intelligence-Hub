"""
data_loader.py — FBref (via soccerdata) + Understat (direct requests)
                + StatsBomb Open Data (via statsbombpy).

Two-layer caching for all loaders:
  1. Disk CSV — persists across restarts; invalidated after CACHE_DAYS.
               Keyed per league+season to minimise requests.
  2. st.cache_data — in-memory within a Streamlit session; same TTL.

soccerdata is flaky with Opera — it may crash on first attempt per URL but
succeeds on retry because soccerdata's own disk cache is populated on the
failed attempt. Every sd.FBref call is wrapped in a one-retry helper.

Supported FBref stat_types: standard, keeper, shooting, playing_time, misc.
(passing, defense, possession dropped from FBref in January 2026.)

Understat loaders use the internal REST API (no HTML scraping).
  GET /getLeagueData/{slug}/{year}  — season stats for all teams
  GET /getTeamData/{team}/{year}    — match history for one team
Season format "2425" is converted to "2024" (Understat uses start year).
Requests are made via a shared requests.Session with a User-Agent header.

StatsBomb loaders use statsbombpy (no auth, open data only).
Competition/season IDs must be looked up at runtime via load_sb_competitions().
Note: sb.events() coordinate columns are stored as strings in CSV; the
st.cache_data layer retains the original list types within a session.
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta

import requests
import pandas as pd
import streamlit as st
import soccerdata as sd
from statsbombpy import sb

from config import (
    BROWSER_PATH,
    CACHE_DAYS,
    DATA_DIR,
    FOTMOB_LEAGUE_CACHE_HOURS,
    FOTMOB_REQUEST_DELAY,
    UNDERSTAT_LEAGUES,
    UNDERSTAT_TEAM_NAMES,
)

os.makedirs(DATA_DIR, exist_ok=True)


# ── soccerdata helpers ────────────────────────────────────────────────────────

def _make_fbref(league: str, season: str) -> sd.FBref:
    return sd.FBref(leagues=league, seasons=season, path_to_browser=BROWSER_PATH)


def _call_with_retry(fn, *args, **kwargs):
    """Call fn(*args, **kwargs), retrying once on any exception."""
    try:
        return fn(*args, **kwargs)
    except Exception:
        return fn(*args, **kwargs)


# ── column helpers ────────────────────────────────────────────────────────────

def _flatten_cols(df: pd.DataFrame) -> pd.DataFrame:
    """Collapse MultiIndex headers to 'Group_Stat' strings, skipping Unnamed levels."""
    if isinstance(df.columns, pd.MultiIndex):
        new_cols = []
        for col in df.columns:
            parts = [
                str(c).strip()
                for c in col
                if str(c).strip() and not str(c).startswith("Unnamed")
            ]
            new_cols.append("_".join(parts) if parts else str(col[-1]).strip())
        df.columns = new_cols
    return df


def _print_cols(df: pd.DataFrame, label: str) -> None:
    bar = "=" * 62
    print(f"\n{bar}\n  Columns  [{label}]\n{bar}")
    for col in df.columns:
        print(f"    {col}")
    print(f"\n  → {len(df.columns)} columns | {len(df)} rows\n{bar}\n")
    sys.stdout.flush()


# ── caching helpers ───────────────────────────────────────────────────────────

def _cache_path(prefix: str, league: str, season: str, extra: str = "") -> str:
    slug = f"{league}_{season}".replace(" ", "_").replace("-", "_")
    suffix = f"_{extra}" if extra else ""
    return os.path.join(DATA_DIR, f"{prefix}_{slug}{suffix}.csv")


def _is_stale(path: str, days: int = CACHE_DAYS) -> bool:
    if not os.path.exists(path):
        return True
    age = datetime.now() - datetime.fromtimestamp(os.path.getmtime(path))
    return age > timedelta(days=days)


# ── team filtering ────────────────────────────────────────────────────────────

def _filter_team(df: pd.DataFrame, team: str) -> pd.DataFrame:
    """
    Filter rows matching *team*.
    Schedule tables use Home/Away columns; stats tables use Squad/Team.
    """
    t = team.strip().lower()

    if "Home" in df.columns and "Away" in df.columns:
        mask = (
            df["Home"].astype(str).str.strip().str.lower() == t
        ) | (
            df["Away"].astype(str).str.strip().str.lower() == t
        )
        return df[mask].reset_index(drop=True)

    for col in ("Squad", "squad", "Team", "team"):
        if col in df.columns:
            mask = df[col].astype(str).str.strip().str.lower() == t
            return df[mask].reset_index(drop=True)

    return df


# ── public API ────────────────────────────────────────────────────────────────

@st.cache_data(ttl=CACHE_DAYS * 86_400, show_spinner="Caricamento statistiche squadre…")
def load_team_season_stats(
    league: str, season: str, stat_type: str = "standard"
) -> pd.DataFrame:
    """
    Season-aggregate stats for all teams in the league.

    Args:
        league:    soccerdata FBref league slug, e.g. "ITA-Serie A"
        season:    Season code, e.g. "2425"
        stat_type: standard | keeper | shooting | playing_time | misc
    """
    path = _cache_path("team_season", league, season, stat_type)
    if not _is_stale(path):
        return pd.read_csv(path)

    fbref = _make_fbref(league, season)
    df = _call_with_retry(fbref.read_team_season_stats, stat_type=stat_type)
    df = _flatten_cols(df.reset_index())
    df.to_csv(path, index=False)
    _print_cols(df, f"team_season | {league} {season} | {stat_type}")
    return df


@st.cache_data(ttl=CACHE_DAYS * 86_400, show_spinner="Caricamento partite squadra…")
def load_team_match_stats(league: str, season: str, team: str) -> pd.DataFrame:
    """
    Fixtures and results for *team*, from the FBref season schedule.

    Full league schedule cached on disk; team filtering is in-memory.

    Args:
        league:  soccerdata FBref league slug, e.g. "ITA-Serie A"
        season:  Season code, e.g. "2425"
        team:    Team name as FBref uses it, e.g. "Inter"
    """
    path = _cache_path("schedule", league, season)
    if _is_stale(path):
        fbref = _make_fbref(league, season)
        df = _call_with_retry(fbref.read_schedule)
        df = _flatten_cols(df.reset_index())
        df = df.dropna(how="all").reset_index(drop=True)
        df.to_csv(path, index=False)
        _print_cols(df, f"schedule | {league} {season}")
    else:
        df = pd.read_csv(path)

    return _filter_team(df, team)


@st.cache_data(ttl=CACHE_DAYS * 86_400, show_spinner="Caricamento statistiche giocatori…")
def load_player_season_stats(
    league: str, season: str, team: str, stat_type: str = "standard"
) -> pd.DataFrame:
    """
    Season-aggregate player stats for *team*.

    Full league player data cached on disk; team filtering is in-memory.

    Args:
        league:    soccerdata FBref league slug, e.g. "ITA-Serie A"
        season:    Season code, e.g. "2425"
        team:      Team name as FBref uses it, e.g. "Inter"
        stat_type: standard | keeper | shooting | playing_time | misc
    """
    path = _cache_path("player_season", league, season, stat_type)
    if _is_stale(path):
        fbref = _make_fbref(league, season)
        df = _call_with_retry(fbref.read_player_season_stats, stat_type=stat_type)
        df = _flatten_cols(df.reset_index())
        df.to_csv(path, index=False)
        _print_cols(df, f"player_season | {league} {season} | {stat_type}")
    else:
        df = pd.read_csv(path)

    return _filter_team(df, team)


# ── Understat helpers ─────────────────────────────────────────────────────────

_US_BASE = "https://understat.com"
_US_SESSION = requests.Session()
_US_SESSION.headers["User-Agent"] = "Mozilla/5.0"


def _understat_season(season: str) -> str:
    """'2425' → '2024' (Understat uses start year of the season)."""
    return f"20{season[:2]}"


def _us_league(league: str) -> str:
    """Map league name to Understat slug. Accepts plain names ('Serie A') or
    FBref-style prefixed names ('ITA-Serie A') — strips the country prefix on miss."""
    if league in UNDERSTAT_LEAGUES:
        return UNDERSTAT_LEAGUES[league]
    stripped = league.split("-", 1)[-1].strip()
    if stripped in UNDERSTAT_LEAGUES:
        return UNDERSTAT_LEAGUES[stripped]
    raise ValueError(
        f"League '{league}' not in UNDERSTAT_LEAGUES. "
        f"Valid values: {list(UNDERSTAT_LEAGUES)}"
    )


def _us_team(team: str) -> str:
    """Map FBref team name to Understat team name where they differ."""
    return UNDERSTAT_TEAM_NAMES.get(team, team)


# ── Understat public API ──────────────────────────────────────────────────────

@st.cache_data(ttl=CACHE_DAYS * 86_400, show_spinner="Caricamento dati Understat squadre…")
def load_understat_league_data(league: str, season: str) -> pd.DataFrame:
    """
    Season-aggregate xG stats for all teams via getLeagueData REST endpoint.

    One row per team. ppda is stored as a float (att/def) when the API returns
    it as a nested object.

    Args:
        league:  FBref slug or plain name, e.g. "ITA-Serie A" or "Serie A"
        season:  Season code, e.g. "2425" → mapped to "2024" for Understat
    """
    path = _cache_path("understat_league", league, season)
    if not _is_stale(path):
        return pd.read_csv(path)

    league_slug = _us_league(league)
    us_season = _understat_season(season)
    resp = _US_SESSION.get(
        f"{_US_BASE}/getLeagueData/{league_slug}/{us_season}", timeout=20
    )
    resp.raise_for_status()
    raw = resp.json()

    teams = raw if isinstance(raw, list) else list(raw.values())
    rows = []
    for t in teams:
        ppda = t.get("ppda")
        if isinstance(ppda, dict):
            att, def_ = ppda.get("att"), ppda.get("def")
            ppda_val = att / def_ if def_ else None
        else:
            ppda_val = ppda
        rows.append({
            "team":   t.get("title", t.get("team", "")),
            "games":  t.get("games"),
            "wins":   t.get("wins"),
            "draws":  t.get("draws"),
            "loses":  t.get("loses"),
            "scored": t.get("scored"),
            "missed": t.get("missed"),
            "pts":    t.get("pts"),
            "xG":     t.get("xG"),
            "xGA":    t.get("xGA"),
            "npxG":   t.get("npxG"),
            "npxGA":  t.get("npxGA"),
            "ppda":   ppda_val,
            "deep":   t.get("deep"),
            "xpts":   t.get("xpts"),
        })

    df = pd.DataFrame(rows)
    df.to_csv(path, index=False)
    _print_cols(df, f"understat_league | {league} {season}")
    return df


@st.cache_data(ttl=CACHE_DAYS * 86_400, show_spinner="Caricamento partite Understat…")
def load_understat_team_matches(league: str, season: str, team: str) -> pd.DataFrame:
    """
    Match-by-match results for *team* via getTeamData REST endpoint.

    Args:
        league:  FBref slug or plain name, e.g. "ITA-Serie A" or "Serie A"
        season:  Season code, e.g. "2425"
        team:    Team name as FBref uses it; mapped to Understat name automatically
    """
    team = _us_team(team)
    path = _cache_path("understat_team_matches", league, season, team.replace(" ", "_"))
    if not _is_stale(path):
        return pd.read_csv(path)

    us_season = _understat_season(season)
    resp = _US_SESSION.get(
        f"{_US_BASE}/getTeamData/{team}/{us_season}", timeout=20
    )
    resp.raise_for_status()
    raw = resp.json()

    history = raw.get("history", raw) if isinstance(raw, dict) else raw
    if not isinstance(history, list):
        history = list(history.values())

    rows = []
    for m in history:
        h_side = m.get("h", {})
        a_side = m.get("a", {})
        rows.append({
            "date":   m.get("date"),
            "home":   h_side.get("title") if isinstance(h_side, dict) else m.get("home"),
            "away":   a_side.get("title") if isinstance(a_side, dict) else m.get("away"),
            "scored": m.get("scored"),
        })

    df = pd.DataFrame(rows)
    df.to_csv(path, index=False)
    _print_cols(df, f"understat_team_matches | {league} {season} | {team}")
    return df


# ── StatsBomb Open Data ───────────────────────────────────────────────────────

_SB_COMPETITIONS_PATH = os.path.join(DATA_DIR, "sb_competitions.csv")


def _sb_path(prefix: str, *ids) -> str:
    return os.path.join(DATA_DIR, f"sb_{prefix}_{'_'.join(str(i) for i in ids)}.csv")


@st.cache_data(ttl=CACHE_DAYS * 2 * 86_400, show_spinner="Caricamento competizioni StatsBomb…")
def load_sb_competitions() -> pd.DataFrame:
    """
    Full list of StatsBomb Open Data competitions and seasons.

    IDs here are the ground truth — always use this to look up
    competition_id and season_id before calling other sb_ loaders.
    Refreshed every CACHE_DAYS*2 days (weekly by default).
    """
    path = _SB_COMPETITIONS_PATH
    if not _is_stale(path, days=CACHE_DAYS * 2):
        return pd.read_csv(path)

    df = sb.competitions()
    df.to_csv(path, index=False)
    _print_cols(df, "sb_competitions")
    return df


@st.cache_data(ttl=CACHE_DAYS * 86_400, show_spinner="Caricamento partite StatsBomb…")
def load_sb_matches(competition_id: int, season_id: int) -> pd.DataFrame:
    """
    All matches for a StatsBomb competition/season pair.

    Args:
        competition_id:  From load_sb_competitions()["competition_id"]
        season_id:       From load_sb_competitions()["season_id"]
    """
    path = _sb_path("matches", competition_id, season_id)
    if not _is_stale(path):
        return pd.read_csv(path)

    df = sb.matches(competition_id=competition_id, season_id=season_id)
    df.to_csv(path, index=False)
    _print_cols(df, f"sb_matches | comp={competition_id} season={season_id}")
    return df


@st.cache_data(ttl=CACHE_DAYS * 86_400, show_spinner="Caricamento eventi StatsBomb…")
def load_sb_events(match_id: int) -> pd.DataFrame:
    """
    Event-level data for a single match: every pass, shot, press with x/y coords.

    Args:
        match_id:  From load_sb_matches()["match_id"]
    """
    path = _sb_path("events", match_id)
    if not _is_stale(path):
        return pd.read_csv(path)

    df = sb.events(match_id=match_id)
    df.to_csv(path, index=False)
    _print_cols(df, f"sb_events | match={match_id}")
    return df


@st.cache_data(ttl=CACHE_DAYS * 86_400, show_spinner="Caricamento formazioni StatsBomb…")
def load_sb_lineups(match_id: int) -> pd.DataFrame:
    """
    Starting lineups for both teams in a match, as a single flat DataFrame.

    statsbombpy returns a dict keyed by team name; this flattens it and
    adds a 'team' column so both sides are in one DataFrame.

    Args:
        match_id:  From load_sb_matches()["match_id"]
    """
    path = _sb_path("lineups", match_id)
    if not _is_stale(path):
        return pd.read_csv(path)

    lineups = sb.lineups(match_id=match_id)
    dfs = []
    for team_name, team_df in lineups.items():
        team_df = team_df.copy()
        team_df["team"] = team_name
        dfs.append(team_df)
    df = pd.concat(dfs, ignore_index=True)
    df.to_csv(path, index=False)
    _print_cols(df, f"sb_lineups | match={match_id}")
    return df


# ── FotMob (primary source for current seasons) ───────────────────────────────
#
# Unofficial JSON endpoints used by fotmob.com itself — personal/educational use,
# requests are throttled (FOTMOB_REQUEST_DELAY) and cached on disk:
#   GET /api/data/leagues?id={league_id}&season={YYYY/YYYY}  fixtures, table, stat links
#   GET /api/data/matchDetails?matchId={id}                  per-match stats, shots, lineups
#   GET data.fotmob.com/stats/{…}.json                       season team rankings
# Finished matches never change, so their (slimmed) JSON is cached forever.

_FM_BASE = "https://www.fotmob.com/api/data"
_FM_DIR = os.path.join(DATA_DIR, "fotmob")
_FM_MATCH_VERSION = 2  # bump when the slimmed match schema changes
os.makedirs(_FM_DIR, exist_ok=True)
_FM_SESSION = requests.Session()
_FM_SESSION.headers["User-Agent"] = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)

# FotMob stat keys → stable column names used by metrics.py
FM_STAT_KEYS = {
    "BallPossesion":              "possession",
    "expected_goals":             "xg",
    "expected_goals_open_play":   "xg_open_play",
    "expected_goals_set_play":    "xg_set_play",
    "expected_goals_non_penalty": "npxg",
    "expected_goals_on_target":   "xgot",
    "total_shots":                "shots",
    "ShotsOnTarget":              "shots_on_target",
    "shots_inside_box":           "shots_inside_box",
    "big_chance":                 "big_chances",
    "big_chance_missed_title":    "big_chances_missed",
    "touches_opp_box":            "touches_opp_box",
    "passes":                     "passes",
    "accurate_passes":            "passes_accurate",
    "own_half_passes":            "passes_own_half",
    "opposition_half_passes":     "passes_opp_half",
    "long_balls_accurate":        "long_balls_accurate",
    "accurate_crosses":           "crosses_accurate",
    "corners":                    "corners",
    "matchstats.headers.tackles": "tackles",
    "interceptions":              "interceptions",
    "shot_blocks":                "blocks",
    "clearances":                 "clearances",
    "keeper_saves":               "saves",
    "duel_won":                   "duels_won",
    "aerials_won":                "aerials_won",
    "dribbles_succeeded":         "dribbles_succeeded",
    "fouls":                      "fouls",
    "yellow_cards":               "yellow_cards",
    "red_cards":                  "red_cards",
}

# Season team rankings fetched for league context (FotMob stat list names)
FM_LEAGUE_STATS = {
    "possession_percentage_team":   "possession",
    "expected_goals_team":          "xg_total",
    "expected_goals_conceded_team": "xga_total",
    "goals_team_match":             "goals_pm",
    "goals_conceded_team_match":    "goals_conceded_pm",
    "ontarget_scoring_att_team":    "shots_on_target_pm",
    "big_chance_team":              "big_chances_total",
    "accurate_pass_team":           "passes_accurate_pm",
    "touches_in_opp_box_team":      "touches_opp_box_total",
    "interception_team":            "interceptions_pm",
    "total_tackle_team":            "tackles_pm",
    "poss_won_att_3rd_team":        "poss_won_att_3rd_pm",
    "clean_sheet_team":             "clean_sheets",
}


def _fm_get(url: str, params: dict | None = None):
    time.sleep(FOTMOB_REQUEST_DELAY)
    resp = _FM_SESSION.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _fm_read(path: str):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _fm_write(path: str, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def _season_slug(season: str | None) -> str:
    return (season or "current").replace("/", "-")


@st.cache_data(ttl=FOTMOB_LEAGUE_CACHE_HOURS * 3600, show_spinner="Caricamento campionato (FotMob)…")
def load_fotmob_league(league_id: int, season: str | None = None) -> dict:
    """
    Raw league payload: fixtures, table, season stat links.

    Args:
        league_id: FotMob league id (see config.FOTMOB_LEAGUES)
        season:    "2026/2027" style, or None for the current season
    """
    path = os.path.join(_FM_DIR, f"league_{league_id}_{_season_slug(season)}.json")
    if not _is_stale(path, days=FOTMOB_LEAGUE_CACHE_HOURS / 24):
        return _fm_read(path)
    params = {"id": league_id}
    if season:
        params["season"] = season
    data = _fm_get(f"{_FM_BASE}/leagues", params)
    slim = {k: data.get(k) for k in ("details", "allAvailableSeasons", "table", "fixtures", "stats")}
    _fm_write(path, slim)
    return slim


def fotmob_seasons(league_id: int) -> list[str]:
    return load_fotmob_league(league_id, None).get("allAvailableSeasons", [])


def fotmob_fixtures(league_id: int, season: str | None) -> pd.DataFrame:
    """One row per league match (played or not)."""
    league = load_fotmob_league(league_id, season)
    rows = []
    for m in league["fixtures"]["allMatches"]:
        stt = m.get("status", {})
        hg = ag = None
        score = stt.get("scoreStr")
        finished = bool(stt.get("finished")) and not stt.get("cancelled")
        if finished and score and "-" in score:
            hg, ag = (int(x) for x in score.split("-"))
        rows.append({
            "match_id":   int(m["id"]),
            "round":      int(m["round"]) if str(m.get("round", "")).isdigit() else m.get("round"),
            "utc_time":   stt.get("utcTime"),
            "home":       m["home"]["name"],
            "away":       m["away"]["name"],
            "finished":   finished and hg is not None,
            "home_goals": hg,
            "away_goals": ag,
        })
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["utc_time"], utc=True, format="ISO8601").dt.tz_convert("Europe/Rome").dt.date
    return df


def fotmob_teams(league_id: int, season: str | None) -> list[str]:
    fx = fotmob_fixtures(league_id, season)
    return sorted(set(fx["home"]) | set(fx["away"]))


def load_fotmob_match(match_id: int) -> dict:
    """Slimmed match details (general, header, stats, shots, lineup)."""
    path = os.path.join(_FM_DIR, f"match_{match_id}.json")
    if os.path.exists(path):
        cached = _fm_read(path)
        if cached.get("version") == _FM_MATCH_VERSION:
            return cached
    raw = _fm_get(f"{_FM_BASE}/matchDetails", {"matchId": match_id})
    content = raw.get("content", {}) or {}
    lineup = content.get("lineup") or {}

    def _side(t):
        t = t or {}
        return {
            "name": t.get("name"),
            "id": t.get("id"),
            "formation": t.get("formation"),
            "coach": (t.get("coach") or {}).get("name"),
            # positionId encodes line (id // 10) and lateral slot (id % 10)
            "starters": [
                {"id": p.get("id"), "positionId": p.get("positionId")}
                for p in t.get("starters", []) or []
            ],
        }

    players = []
    for p in (content.get("playerStats") or {}).values():
        flat = {}
        for grp in p.get("stats") or []:
            for s in (grp.get("stats") or {}).values():
                key, stat = s.get("key"), s.get("stat") or {}
                if not key or key in flat or stat.get("value") is None:
                    continue
                flat[key] = stat.get("value")
                if stat.get("total") is not None:
                    flat[f"{key}_att"] = stat.get("total")
        if flat:
            players.append({
                "id": p.get("id"), "name": p.get("name"), "teamId": p.get("teamId"),
                "teamName": p.get("teamName"), "isGoalkeeper": p.get("isGoalkeeper"),
                "usualPosition": p.get("usualPosition"), "stats": flat,
            })

    slim = {
        "version": _FM_MATCH_VERSION,
        "general": raw.get("general"),
        "header": {"teams": (raw.get("header") or {}).get("teams")},
        "stats": content.get("stats"),
        "shots": (content.get("shotmap") or {}).get("shots", []),
        "lineup": {"home": _side(lineup.get("homeTeam")), "away": _side(lineup.get("awayTeam"))},
        "players": players,
    }
    if (raw.get("general") or {}).get("finished"):
        _fm_write(path, slim)
    return slim


def _fm_flat_stats(match: dict) -> dict[str, tuple]:
    """{column_name: (home_value, away_value)} from the 'All' period."""
    out: dict[str, tuple] = {}
    periods = ((match.get("stats") or {}).get("Periods") or {}).get("All") or {}
    for grp in periods.get("stats", []):
        for s in grp.get("stats", []):
            col = FM_STAT_KEYS.get(s.get("key"))
            raw = s.get("rawStats") or []
            if not col or col in out or len(raw) != 2 or None in raw:
                continue
            out[col] = (raw[0].get("value"), raw[1].get("value"))
            if "total" in raw[0]:
                out[f"{col}_att"] = (raw[0].get("total"), raw[1].get("total"))
    return out


@st.cache_data(ttl=FOTMOB_LEAGUE_CACHE_HOURS * 3600, show_spinner="Caricamento partite della squadra (FotMob)…")
def load_team_match_table(league_id: int, season: str | None, team: str) -> pd.DataFrame:
    """
    One row per finished league match of *team*: metadata + team stats
    (plain column names) + opponent stats (``opp_`` prefix).
    """
    fx = fotmob_fixtures(league_id, season)
    fx = fx[fx["finished"] & ((fx["home"] == team) | (fx["away"] == team))]
    rows = []
    for _, m in fx.sort_values("utc_time").iterrows():
        match = load_fotmob_match(m["match_id"])
        is_home = m["home"] == team
        me, opp = (0, 1) if is_home else (1, 0)
        side, opp_side = ("home", "away") if is_home else ("away", "home")
        gf = int(m["home_goals"] if is_home else m["away_goals"])
        ga = int(m["away_goals"] if is_home else m["home_goals"])
        row = {
            "match_id":      m["match_id"],
            "date":          m["date"],
            "round":         m["round"],
            "venue":         "Casa" if is_home else "Trasferta",
            "opponent":      m["away"] if is_home else m["home"],
            "goals_for":     gf,
            "goals_against": ga,
            "result":        "V" if gf > ga else ("N" if gf == ga else "P"),
            "points":        3 if gf > ga else (1 if gf == ga else 0),
            "formation":     match["lineup"][side].get("formation"),
            "opp_formation": match["lineup"][opp_side].get("formation"),
            "coach":         match["lineup"][side].get("coach"),
        }
        for col, vals in _fm_flat_stats(match).items():
            row[col] = vals[me]
            row[f"opp_{col}"] = vals[opp]
        rows.append(row)
    return pd.DataFrame(rows)


@st.cache_data(ttl=FOTMOB_LEAGUE_CACHE_HOURS * 3600, show_spinner=False)
def load_team_shots(league_id: int, season: str | None, team: str) -> pd.DataFrame:
    """
    All shots for and against *team* in finished league matches.
    Coordinates are FotMob's 105x68 frame, shooting team attacking towards x=105.
    """
    fx = fotmob_fixtures(league_id, season)
    fx = fx[fx["finished"] & ((fx["home"] == team) | (fx["away"] == team))]
    rows = []
    for mid in fx["match_id"]:
        match = load_fotmob_match(mid)
        teams = (match.get("header") or {}).get("teams") or []
        team_id = next((t["id"] for t in teams if t.get("name") == team), None)
        for sh in match.get("shots", []):
            rows.append({
                "match_id":  mid,
                "side":      "for" if sh.get("teamId") == team_id else "against",
                "x":         sh.get("x"),
                "y":         sh.get("y"),
                "xg":        sh.get("expectedGoals"),
                "is_goal":   sh.get("eventType") == "Goal" and not sh.get("isOwnGoal"),
                "on_target": sh.get("isOnTarget"),
                "situation": sh.get("situation"),
                "shot_type": sh.get("shotType"),
                "player":    sh.get("playerName"),
                "minute":    sh.get("min"),
            })
    return pd.DataFrame(rows)


@st.cache_data(ttl=FOTMOB_LEAGUE_CACHE_HOURS * 3600, show_spinner="Caricamento statistiche di lega (FotMob)…")
def load_league_team_stats(league_id: int, season: str | None) -> pd.DataFrame:
    """
    Season rankings for every team in the league, one column per stat in
    FM_LEAGUE_STATS (FotMob's own per-match or total values) plus 'matches'.
    """
    path = os.path.join(_FM_DIR, f"league_stats_{league_id}_{_season_slug(season)}.csv")
    if not _is_stale(path, days=FOTMOB_LEAGUE_CACHE_HOURS / 24):
        return pd.read_csv(path)

    league = load_fotmob_league(league_id, season)
    links = {t.get("name"): t.get("fetchAllUrl") for t in (league.get("stats") or {}).get("teams", [])}
    frames = []
    for stat, col in FM_LEAGUE_STATS.items():
        url = links.get(stat)
        if not url:
            continue
        data = _fm_get(url)
        lst = (data.get("TopLists") or [{}])[0].get("StatList", [])
        frames.append(pd.DataFrame(
            [{"team": r["ParticipantName"], col: r["StatValue"], "matches": r.get("MatchesPlayed")} for r in lst]
        ).set_index("team"))
    if not frames:
        return pd.DataFrame()
    df = frames[0]
    for f in frames[1:]:
        df = df.join(f.drop(columns="matches"), how="outer")
    df = df.reset_index()
    df.to_csv(path, index=False)
    return df


def fotmob_finished_match_ids(league_id: int, season: str | None) -> list[int]:
    fx = fotmob_fixtures(league_id, season)
    return fx.loc[fx["finished"], "match_id"].tolist()


def fotmob_missing_match_ids(league_id: int, season: str | None) -> list[int]:
    """Finished league matches not yet cached with the current schema."""
    missing = []
    for mid in fotmob_finished_match_ids(league_id, season):
        path = os.path.join(_FM_DIR, f"match_{mid}.json")
        if not os.path.exists(path) or _fm_read(path).get("version") != _FM_MATCH_VERSION:
            missing.append(mid)
    return missing


def load_league_player_appearances(
    league_id: int, season: str | None, progress=None,
) -> pd.DataFrame:
    """
    One row per player per finished league match, for every team.

    Downloads any match not cached yet (throttled); ``progress(i, n)`` is
    called after each download so the UI can show a progress bar.
    Columns: match_id, date, team, team_id, player_id, player, is_gk,
    usual_position (0 GK, 1 DEF, 2 MID, 3 FWD), started, position_id,
    formation, minutes_played, then one column per FotMob player stat key
    (plus '<key>_att' for fractions).
    """
    fx = fotmob_fixtures(league_id, season)
    fx = fx[fx["finished"]]
    missing = set(fotmob_missing_match_ids(league_id, season))
    done = 0
    rows = []
    for _, m in fx.iterrows():
        mid = m["match_id"]
        match = load_fotmob_match(mid)
        if mid in missing:
            done += 1
            if progress:
                progress(done, len(missing))
        starters = {}
        formations = {}
        # fixture-style names (e.g. "Inter", not playerStats' "Internazionale")
        names = {t.get("id"): t.get("name") for t in (match.get("header") or {}).get("teams") or []}
        for side in ("home", "away"):
            lu = match["lineup"][side]
            formations[lu.get("id")] = lu.get("formation")
            for s in lu.get("starters", []):
                starters[s["id"]] = s.get("positionId")
        for p in match.get("players", []):
            row = {
                "match_id": mid,
                "date": m["date"],
                "team": names.get(p.get("teamId"), p.get("teamName")),
                "team_id": p.get("teamId"),
                "player_id": p.get("id"),
                "player": p.get("name"),
                "is_gk": bool(p.get("isGoalkeeper")),
                "usual_position": p.get("usualPosition"),
                "started": p.get("id") in starters,
                "position_id": starters.get(p.get("id")),
                "formation": formations.get(p.get("teamId")),
            }
            row.update(p.get("stats", {}))
            rows.append(row)
    return pd.DataFrame(rows)
