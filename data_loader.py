"""
data_loader.py — FBref scraping via requests + pandas.read_html().

Two-layer caching:
  1. Disk CSV — persists across restarts; invalidated after CACHE_DAYS.
               Keyed per league+season (all teams together) to minimise scrape calls.
  2. st.cache_data — in-memory within a Streamlit session; same TTL.

FBref wraps some tables in HTML comments; _uncomment() strips them before
parsing so pd.read_html() can see every table on the page.

Column names are printed to stdout on the first scrape of each dataset to
facilitate discovery before building metrics / role profiles.
"""

import os
import re
import sys
import time
from datetime import datetime, timedelta
from io import StringIO

import requests
import pandas as pd
import streamlit as st

from config import (
    CACHE_DAYS,
    DATA_DIR,
    FBREF_LEAGUE_URLS,
    STAT_TYPE_SLUGS,
    STAT_TYPE_TABLE_KEYS,
)

os.makedirs(DATA_DIR, exist_ok=True)

_REQUEST_DELAY = 4  # seconds between live FBref requests

_session = requests.Session()
_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36"
})


# ── URL builders ──────────────────────────────────────────────────────────────

def _season_fmt(season: str) -> str:
    """'2425' → '2024-2025'"""
    return f"20{season[:2]}-20{season[2:]}"


def _stats_url(league: str, season: str, stat_type: str) -> str:
    cfg = FBREF_LEAGUE_URLS[league]
    url_s = _season_fmt(season)
    slug = STAT_TYPE_SLUGS[stat_type]
    return (
        f"https://fbref.com/en/comps/{cfg['comp_id']}/{url_s}"
        f"/{slug}/{url_s}-{cfg['league_slug']}-Stats"
    )


def _schedule_url(league: str, season: str) -> str:
    cfg = FBREF_LEAGUE_URLS[league]
    url_s = _season_fmt(season)
    return (
        f"https://fbref.com/en/comps/{cfg['comp_id']}/{url_s}/schedule"
        f"/{url_s}-{cfg['league_slug']}-Scores-and-Fixtures"
    )


# ── scraping helpers ──────────────────────────────────────────────────────────

def _fetch_html(url: str) -> str:
    time.sleep(_REQUEST_DELAY)
    resp = _session.get(url, timeout=30)
    resp.raise_for_status()
    return resp.text


def _uncomment(html: str) -> str:
    """FBref wraps some tables in <!-- --> — strip comment markers to expose them."""
    return re.sub(r"<!--(.*?)-->", lambda m: m.group(1), html, flags=re.DOTALL)


def _parse_table(html: str, table_id: str) -> pd.DataFrame:
    """Extract a single FBref table by HTML id, removing repeat-header rows."""
    clean = _uncomment(html)
    tables = pd.read_html(StringIO(clean), attrs={"id": table_id}, flavor="lxml")
    if not tables:
        raise ValueError(f"Table '{table_id}' not found on page")
    df = tables[0]
    # FBref injects repeat header rows where Rk == "Rk" — drop them
    rk_col = _find_rk_col(df)
    if rk_col is not None:
        df = df[df[rk_col].astype(str) != "Rk"].copy()
    return df.reset_index(drop=True)


def _find_rk_col(df: pd.DataFrame):
    if "Rk" in df.columns:
        return "Rk"
    if isinstance(df.columns, pd.MultiIndex):
        for col in df.columns:
            if col[-1] == "Rk":
                return col
    return None


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
    print(f"\n{bar}\n  FBref columns  [{label}]\n{bar}")
    for col in df.columns:
        print(f"    {col}")
    print(f"\n  → {len(df.columns)} columns | {len(df)} rows\n{bar}\n")
    sys.stdout.flush()


# ── caching helpers ───────────────────────────────────────────────────────────

def _cache_path(prefix: str, league: str, season: str, extra: str = "") -> str:
    slug = f"{league}_{season}".replace(" ", "_").replace("-", "_")
    suffix = f"_{extra}" if extra else ""
    return os.path.join(DATA_DIR, f"{prefix}_{slug}{suffix}.csv")


def _is_stale(path: str) -> bool:
    if not os.path.exists(path):
        return True
    age = datetime.now() - datetime.fromtimestamp(os.path.getmtime(path))
    return age > timedelta(days=CACHE_DAYS)


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
        league:    Key from config.FBREF_LEAGUE_URLS, e.g. "ITA-Serie A"
        season:    Season code, e.g. "2425"
        stat_type: standard | shooting | passing | defense | possession | misc | keeper
    """
    path = _cache_path("team_season", league, season, stat_type)
    if not _is_stale(path):
        return pd.read_csv(path)

    url = _stats_url(league, season, stat_type)
    html = _fetch_html(url)
    key = STAT_TYPE_TABLE_KEYS[stat_type]
    df = _parse_table(html, f"stats_squads_{key}_for")
    df = _flatten_cols(df)
    df.to_csv(path, index=False)
    _print_cols(df, f"team_season | {league} {season} | {stat_type}")
    return df


@st.cache_data(ttl=CACHE_DAYS * 86_400, show_spinner="Caricamento partite squadra…")
def load_team_match_stats(league: str, season: str, team: str) -> pd.DataFrame:
    """
    Fixtures and results for *team*, from the FBref season schedule page.

    Columns include date, home/away teams, score, xG, attendance, venue.
    Full league schedule cached on disk; team filtering is in-memory.

    Args:
        league:  Key from config.FBREF_LEAGUE_URLS, e.g. "ITA-Serie A"
        season:  Season code, e.g. "2425"
        team:    Team name as FBref uses it, e.g. "Inter"
    """
    path = _cache_path("schedule", league, season)
    if _is_stale(path):
        url = _schedule_url(league, season)
        html = _fetch_html(url)
        cfg = FBREF_LEAGUE_URLS[league]
        table_id = f"sched_{_season_fmt(season)}_{cfg['comp_id']}_1"
        try:
            df = _parse_table(html, table_id)
        except ValueError:
            # ID pattern may vary — fall back to the largest table on the page
            all_tables = pd.read_html(StringIO(_uncomment(html)), flavor="lxml")
            df = max(all_tables, key=len).reset_index(drop=True)
        df = _flatten_cols(df)
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
        league:    Key from config.FBREF_LEAGUE_URLS, e.g. "ITA-Serie A"
        season:    Season code, e.g. "2425"
        team:      Team name as FBref uses it, e.g. "Inter"
        stat_type: standard | shooting | passing | defense | possession | misc | keeper
    """
    path = _cache_path("player_season", league, season, stat_type)
    if _is_stale(path):
        url = _stats_url(league, season, stat_type)
        html = _fetch_html(url)
        key = STAT_TYPE_TABLE_KEYS[stat_type]
        df = _parse_table(html, f"stats_{key}")
        df = _flatten_cols(df)
        df.to_csv(path, index=False)
        _print_cols(df, f"player_season | {league} {season} | {stat_type}")
    else:
        df = pd.read_csv(path)

    return _filter_team(df, team)
