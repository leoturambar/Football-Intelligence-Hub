"""
metrics.py — Derived team metrics for Football Intelligence Hub.

Every function is subset-agnostic: it receives a match table (one row per
match, as built by data_loader.load_team_match_table, possibly filtered by
the UI) and returns plain numbers. Nothing here fetches data.

Column conventions (from data_loader.FM_STAT_KEYS):
    <stat>       value for the analysed team
    opp_<stat>   value for the opponent in the same match
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# ── Metric catalogue ──────────────────────────────────────────────────────────
# label: Italian UI label · fmt: display format · better: "high" | "low" | None

METRICS: dict[str, dict] = {
    "matches":              {"label": "Partite",                        "fmt": "{:.0f}",  "better": None},
    "ppg":                  {"label": "Punti per partita",              "fmt": "{:.2f}",  "better": "high"},
    "gf_pm":                {"label": "Gol fatti / partita",            "fmt": "{:.2f}",  "better": "high"},
    "ga_pm":                {"label": "Gol subiti / partita",           "fmt": "{:.2f}",  "better": "low"},
    "xg_pm":                {"label": "xG / partita",                   "fmt": "{:.2f}",  "better": "high"},
    "xga_pm":               {"label": "xG concessi / partita",          "fmt": "{:.2f}",  "better": "low"},
    "xg_diff_pm":           {"label": "Differenza xG / partita",        "fmt": "{:+.2f}", "better": "high"},
    "finishing":            {"label": "Gol − xG (finalizzazione)",      "fmt": "{:+.1f}", "better": "high"},
    "gk_overperf":          {"label": "xG concessi − gol subiti",       "fmt": "{:+.1f}", "better": "high"},
    "possession":           {"label": "Possesso medio %",               "fmt": "{:.1f}",  "better": None},
    "pass_accuracy":        {"label": "Precisione passaggi %",          "fmt": "{:.1f}",  "better": "high"},
    "territory":            {"label": "Passaggi nella metà avversaria %", "fmt": "{:.1f}", "better": "high"},
    "ppda_est":             {"label": "PPDA stimato",                   "fmt": "{:.1f}",  "better": "low"},
    "shots_pm":             {"label": "Tiri / partita",                 "fmt": "{:.1f}",  "better": "high"},
    "shots_against_pm":     {"label": "Tiri concessi / partita",        "fmt": "{:.1f}",  "better": "low"},
    "xg_per_shot":          {"label": "xG per tiro",                    "fmt": "{:.3f}",  "better": "high"},
    "xga_per_shot":         {"label": "xG per tiro concesso",           "fmt": "{:.3f}",  "better": "low"},
    "big_chances_pm":       {"label": "Grandi occasioni / partita",     "fmt": "{:.1f}",  "better": "high"},
    "big_chances_against_pm": {"label": "Grandi occasioni concesse / partita", "fmt": "{:.1f}", "better": "low"},
    "box_touches_pm":       {"label": "Tocchi in area avversaria / partita", "fmt": "{:.1f}", "better": "high"},
    "set_piece_xg_share":   {"label": "Quota xG da palla inattiva %",   "fmt": "{:.0f}",  "better": None},
    "set_piece_xga_share":  {"label": "Quota xG concessi da palla inattiva %", "fmt": "{:.0f}", "better": None},
    "def_actions_pm":       {"label": "Contrasti + intercetti / partita", "fmt": "{:.1f}", "better": None},
    "aerial_win_pct":       {"label": "Duelli aerei vinti %",           "fmt": "{:.0f}",  "better": "high"},
    "clean_sheets":         {"label": "Porta inviolata",                "fmt": "{:.0f}",  "better": "high"},
    # league-level only (from FotMob season rankings)
    "shots_on_target_pm":   {"label": "Tiri in porta / partita",        "fmt": "{:.1f}",  "better": "high"},
    "passes_accurate_pm":   {"label": "Passaggi riusciti / partita",    "fmt": "{:.0f}",  "better": None},
    "press_high_pm":        {"label": "Palloni recuperati nel terzo offensivo / partita", "fmt": "{:.1f}", "better": None},
}


def _sum(df: pd.DataFrame, col: str) -> float:
    return float(df[col].fillna(0).sum()) if col in df.columns else np.nan


def _ratio(num: float, den: float, scale: float = 1.0) -> float:
    return num / den * scale if den and not np.isnan(den) else np.nan


def summarize(df: pd.DataFrame) -> dict[str, float]:
    """
    Level-1 metrics for a set of matches. Returns {metric_key: value}.

    PPDA stimato: opponent passes in their own half divided by our tackles +
    interceptions + fouls. True PPDA restricts both terms to the opponent's
    defensive 60% of the pitch; FotMob only gives half-pitch pass splits and
    whole-pitch defensive actions, so read it as a relative pressing index.
    """
    n = len(df)
    if n == 0:
        return {"matches": 0}

    xg, xga = _sum(df, "xg"), _sum(df, "opp_xg")
    gf, ga = _sum(df, "goals_for"), _sum(df, "goals_against")
    shots, shots_a = _sum(df, "shots"), _sum(df, "opp_shots")
    passes_own, passes_opp = _sum(df, "passes_own_half"), _sum(df, "passes_opp_half")
    def_actions = _sum(df, "tackles") + _sum(df, "interceptions")

    return {
        "matches":           n,
        "ppg":               _sum(df, "points") / n,
        "gf_pm":             gf / n,
        "ga_pm":             ga / n,
        "xg_pm":             xg / n,
        "xga_pm":            xga / n,
        "xg_diff_pm":        (xg - xga) / n,
        "finishing":         gf - xg,
        "gk_overperf":       xga - ga,
        "possession":        df["possession"].mean() if "possession" in df else np.nan,
        "pass_accuracy":     _ratio(_sum(df, "passes_accurate"), _sum(df, "passes_accurate_att"), 100),
        "territory":         _ratio(passes_opp, passes_own + passes_opp, 100),
        "ppda_est":          _ratio(_sum(df, "opp_passes_own_half"), def_actions + _sum(df, "fouls")),
        "shots_pm":          shots / n,
        "shots_against_pm":  shots_a / n,
        "xg_per_shot":       _ratio(xg, shots),
        "xga_per_shot":      _ratio(xga, shots_a),
        "big_chances_pm":    _sum(df, "big_chances") / n,
        "big_chances_against_pm": _sum(df, "opp_big_chances") / n,
        "box_touches_pm":    _sum(df, "touches_opp_box") / n,
        "set_piece_xg_share":  _ratio(_sum(df, "xg_set_play"), xg, 100),
        "set_piece_xga_share": _ratio(_sum(df, "opp_xg_set_play"), xga, 100),
        "def_actions_pm":    def_actions / n,
        "aerial_win_pct":    _ratio(_sum(df, "aerials_won"), _sum(df, "aerials_won_att"), 100),
        "clean_sheets":      float((df["goals_against"] == 0).sum()),
    }


def sample_note(n: int, short: bool = False) -> str:
    """
    Reliability note for a sample of n matches. Per-match xG and shot rates
    stabilise slowly: under ~8 matches differences of 0.3–0.5 xG/partita are
    within normal noise.
    """
    if n == 0:
        return "—" if short else ""
    if n < 3:
        return "aneddotico" if short else (
            f"Solo {n} partite: i numeri descrivono quanto successo, non una tendenza.")
    if n < 8:
        return "indicativo" if short else (
            f"{n} partite: campione piccolo, differenze sotto ~0,4 xG/partita possono essere rumore.")
    return "solido" if short else ""


def record(df: pd.DataFrame) -> str:
    """'7V 2N 1P'."""
    counts = df["result"].value_counts() if len(df) else {}
    return f"{counts.get('V', 0)}V {counts.get('N', 0)}N {counts.get('P', 0)}P"


def fmt(key: str, value: float) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "—"
    return METRICS.get(key, {"fmt": "{:.2f}"})["fmt"].format(value)


def compare(df_a: pd.DataFrame, df_b: pd.DataFrame,
            label_a: str = "A", label_b: str = "B") -> pd.DataFrame:
    """Same pipeline on two match subsets, side by side (e.g. Casa vs Trasferta)."""
    a, b = summarize(df_a), summarize(df_b)
    rows = []
    for key, meta in METRICS.items():
        va, vb = a.get(key, np.nan), b.get(key, np.nan)
        rows.append({"Metrica": meta["label"], label_a: fmt(key, va), label_b: fmt(key, vb)})
    return pd.DataFrame(rows)


# ── League context ────────────────────────────────────────────────────────────
# Maps our per-match metrics onto columns of data_loader.load_league_team_stats.

_LEAGUE_MAP = {
    # metric        (league column, per-match divisor?, better)
    "possession":   ("possession",            False, None),
    "xg_pm":        ("xg_total",              True,  "high"),
    "xga_pm":       ("xga_total",             True,  "low"),
    "gf_pm":        ("goals_pm",              False, "high"),
    "ga_pm":        ("goals_conceded_pm",     False, "low"),
    "big_chances_pm": ("big_chances_total",   True,  "high"),
    "box_touches_pm": ("touches_opp_box_total", True, "high"),
    "def_actions_pm": (None,                  False, None),
    "shots_on_target_pm": ("shots_on_target_pm", False, "high"),
    "passes_accurate_pm": ("passes_accurate_pm", False, None),
    "press_high_pm":  ("poss_won_att_3rd_pm",   False, None),
}


def league_table(league_stats: pd.DataFrame) -> pd.DataFrame:
    """League stats normalised to per-match where needed, indexed by team."""
    lg = league_stats.set_index("team").copy()
    out = pd.DataFrame(index=lg.index)
    for metric, (col, per_match, _) in _LEAGUE_MAP.items():
        if col and col in lg:
            out[metric] = lg[col] / lg["matches"] if per_match else lg[col]
    if {"tackles_pm", "interceptions_pm"}.issubset(lg.columns):
        out["def_actions_pm"] = lg["tackles_pm"] + lg["interceptions_pm"]
    if {"xg_total", "xga_total"}.issubset(lg.columns):
        out["xg_diff_pm"] = (lg["xg_total"] - lg["xga_total"]) / lg["matches"]
    return out


def league_context(team: str, league_stats: pd.DataFrame) -> pd.DataFrame:
    """
    Season position of *team* in each league-comparable metric.
    Columns: metric, label, value, league_avg, rank (1 = best), n, pct (0–100, higher = better).
    Uses the full-season league numbers, not the UI match subset.
    """
    if league_stats is None or league_stats.empty:
        return pd.DataFrame()
    lt = league_table(league_stats)
    if team not in lt.index:
        return pd.DataFrame()
    rows = []
    for metric in lt.columns:
        col = lt[metric].dropna()
        better = METRICS.get(metric, {}).get("better") or "high"
        ascending = better == "low"
        rank = int(col.rank(ascending=ascending, method="min")[team])
        n = len(col)
        rows.append({
            "metric": metric,
            "label": METRICS.get(metric, {}).get("label", metric),
            "value": col[team],
            "league_avg": col.mean(),
            "rank": rank,
            "n": n,
            "pct": 100 * (n - rank) / (n - 1) if n > 1 else 50.0,
            "directional": METRICS.get(metric, {}).get("better") is not None,
        })
    return pd.DataFrame(rows)


def strengths_weaknesses(ctx: pd.DataFrame, k: int = 3) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Top-k and bottom-k directional metrics by league percentile."""
    if ctx.empty:
        return ctx, ctx
    d = ctx[ctx["directional"]].sort_values("pct", ascending=False)
    strengths = d[d["pct"] >= 60].head(k)
    # Relative weaknesses: the team's lowest-ranked areas, even for a top side
    rest = d[~d["metric"].isin(strengths["metric"])]
    weaknesses = rest[rest["pct"] < 90].sort_values("pct").head(k)
    return strengths, weaknesses




# ── Cross-league comparison ───────────────────────────────────────────────────
# FotMob league stats are raw season numbers: they are NOT adjusted for league
# strength. A team's "equivalent position" in another league says where its
# numbers would sit there, not how it would actually perform against those sides.

def league_averages(stats_by_league: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Average team value per metric, one column per league."""
    cols = {}
    for name, lg in stats_by_league.items():
        if lg is None or lg.empty:
            continue
        cols[name] = league_table(lg).mean()
    df = pd.DataFrame(cols)
    # league-wide means of these are identical or mirror another row by construction
    skip = {"possession", "xg_diff_pm", "ga_pm", "xga_pm"}
    df = df.loc[[m for m in METRICS if m in df.index and m not in skip]]
    df.index = [METRICS[m]["label"] for m in df.index]
    return df


def _equivalent_rank(values: pd.Series, v: float, better: str | None) -> int:
    values = values.dropna()
    if better == "low":
        return int((values < v).sum()) + 1
    return int((values > v).sum()) + 1  # "high" or style metrics: from the top


def equivalent_positions(team: str, own_league: str,
                         stats_by_league: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    For each metric: the team's value, its rank in its own league and the rank
    the same value would have in every other league ('n' = league size).
    """
    tables = {n: league_table(lg) for n, lg in stats_by_league.items() if lg is not None and not lg.empty}
    if own_league not in tables or team not in tables[own_league].index:
        return pd.DataFrame()
    own = tables[own_league]
    rows = []
    for metric in [m for m in METRICS if m in own.columns]:
        better = METRICS[metric]["better"]
        v = own.loc[team, metric]
        if pd.isna(v):
            continue
        row = {"Metrica": METRICS[metric]["label"], "Valore": fmt(metric, v)}
        for name, t in tables.items():
            if metric not in t:
                continue
            others = t[metric].drop(index=team, errors="ignore") if name == own_league else t[metric]
            rank = _equivalent_rank(others, v, better)
            row[name] = f"{rank}° / {len(t[metric].dropna())}"
        rows.append(row)
    return pd.DataFrame(rows)
