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

import os
import sys
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
