"""
analysis.py — Level 2 (context) analysis for Football Intelligence Hub.

Opponent categorisation: every opponent "type" is a numeric league metric
split into tertiles (Basso / Medio / Alto) computed on the fly from the
current league distribution — never hardcoded thresholds.

Caveat: types use full-season league numbers available today, so an opponent
met in August is classified by what it has done over the whole season so far.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import metrics

TERTILE_LABELS = ["Basso", "Medio", "Alto"]

# dimension key → (UI label, builder from league_stats, explanation of "Alto")
OPPONENT_DIMENSIONS: dict[str, dict] = {
    "press": {
        "label": "Pressing alto",
        "help": "Palloni recuperati nel terzo offensivo per partita. Alto = avversario che pressa in avanti.",
    },
    "possession": {
        "label": "Possesso",
        "help": "Possesso medio. Alto = avversario che gestisce il pallone.",
    },
    "attack": {
        "label": "Pericolosità offensiva",
        "help": "xG prodotti per partita. Alto = attacco forte.",
    },
    "defence": {
        "label": "Solidità difensiva",
        "help": "xG concessi per partita (invertiti). Alto = difesa che concede poco.",
    },
}

# Below this many matches a split is shown but flagged as anecdotal
MIN_SPLIT_MATCHES = 3


def opponent_profiles(league_stats: pd.DataFrame) -> pd.DataFrame:
    """
    One row per league team with the raw dimension values and their tertile
    label (columns '<dim>' and '<dim>_tier').
    """
    if league_stats is None or league_stats.empty:
        return pd.DataFrame()
    lg = league_stats.set_index("team")
    m = lg["matches"].replace(0, np.nan)
    raw = pd.DataFrame(index=lg.index)
    if "poss_won_att_3rd_pm" in lg:
        raw["press"] = lg["poss_won_att_3rd_pm"]
    if "possession" in lg:
        raw["possession"] = lg["possession"]
    if "xg_total" in lg:
        raw["attack"] = lg["xg_total"] / m
    if "xga_total" in lg:
        raw["defence"] = -(lg["xga_total"] / m)  # higher = more solid
    for dim in list(raw.columns):
        col = raw[dim]
        if col.nunique() >= 3:
            raw[f"{dim}_tier"] = pd.qcut(col.rank(method="first"), 3, labels=TERTILE_LABELS).astype(str)
        else:
            raw[f"{dim}_tier"] = "Medio"
    return raw


def team_types(team: str, profiles: pd.DataFrame) -> dict[str, str]:
    """{dimension: tier} for one team."""
    if profiles.empty or team not in profiles.index:
        return {}
    return {d: profiles.loc[team, f"{d}_tier"] for d in OPPONENT_DIMENSIONS if f"{d}_tier" in profiles}


def tag_opponents(matches: pd.DataFrame, profiles: pd.DataFrame) -> pd.DataFrame:
    """Add '<dim>_tier' columns describing each match's opponent."""
    out = matches.copy()
    for dim in OPPONENT_DIMENSIONS:
        col = f"{dim}_tier"
        if col in profiles:
            out[col] = out["opponent"].map(profiles[col])
    return out


def split_by_opponent_type(matches: pd.DataFrame, profiles: pd.DataFrame, dim: str) -> pd.DataFrame:
    """
    Performance of the team against Basso / Medio / Alto opponents on *dim*.
    One row per tier, with a 'campione' reliability note.
    """
    tagged = tag_opponents(matches, profiles)
    col = f"{dim}_tier"
    if col not in tagged:
        return pd.DataFrame()
    rows = []
    for tier in TERTILE_LABELS:
        sub = tagged[tagged[col] == tier]
        s = metrics.summarize(sub)
        n = s.get("matches", 0)
        rows.append({
            "Avversari": tier,
            "Partite": n,
            "Record": metrics.record(sub) if n else "—",
            "Punti/partita": metrics.fmt("ppg", s.get("ppg", np.nan)) if n else "—",
            "xG/partita": metrics.fmt("xg_pm", s.get("xg_pm", np.nan)) if n else "—",
            "xG concessi/partita": metrics.fmt("xga_pm", s.get("xga_pm", np.nan)) if n else "—",
            "Possesso %": metrics.fmt("possession", s.get("possession", np.nan)) if n else "—",
            "Avversari affrontati": ", ".join(sub["opponent"]) if n else "",
            "Campione": metrics.sample_note(n, short=True),
            "_ppg": s.get("ppg", np.nan) if n else np.nan,
            "_xgd": s.get("xg_diff_pm", np.nan) if n else np.nan,
        })
    return pd.DataFrame(rows)


def split_findings(team: str, matches: pd.DataFrame, profiles: pd.DataFrame) -> list[str]:
    """
    Plain-language findings where performance clearly differs by opponent type
    (xG difference per match gap ≥ 0.75 between tiers, both tiers ≥ MIN_SPLIT_MATCHES).
    """
    findings = []
    for dim, meta in OPPONENT_DIMENSIONS.items():
        t = split_by_opponent_type(matches, profiles, dim)
        if t.empty:
            continue
        ok = t[(t["Partite"] >= MIN_SPLIT_MATCHES) & t["_xgd"].notna()]
        if len(ok) < 2:
            continue
        best, worst = ok.loc[ok["_xgd"].idxmax()], ok.loc[ok["_xgd"].idxmin()]
        gap = best["_xgd"] - worst["_xgd"]
        if gap >= 0.75:
            findings.append(
                f"{meta['label']}: contro avversari di livello **{worst['Avversari'].lower()}** "
                f"differenza xG {worst['_xgd']:+.2f}/partita ({int(worst['Partite'])} partite), "
                f"contro livello **{best['Avversari'].lower()}** {best['_xgd']:+.2f} "
                f"({int(best['Partite'])} partite)."
            )
    return findings


# ── Next opponent ─────────────────────────────────────────────────────────────

def next_opponent(fixtures: pd.DataFrame, team: str) -> dict | None:
    """First unplayed league match of *team*: {'opponent', 'venue', 'date', 'round'}."""
    fx = fixtures[(~fixtures["finished"]) & ((fixtures["home"] == team) | (fixtures["away"] == team))]
    if fx.empty:
        return None
    m = fx.sort_values("utc_time").iloc[0]
    home = m["home"] == team
    return {
        "opponent": m["away"] if home else m["home"],
        "venue": "Casa" if home else "Trasferta",
        "date": m["date"],
        "round": m["round"],
    }


def opponent_vs_similar(opp_matches: pd.DataFrame, profiles: pd.DataFrame,
                        my_types: dict[str, str]) -> pd.DataFrame:
    """
    How the opponent has done against teams of the same type as ours, per
    dimension (e.g. we are 'Alto' pressing → their record vs 'Alto' pressing sides).
    """
    tagged = tag_opponents(opp_matches, profiles)
    rows = []
    for dim, tier in my_types.items():
        col = f"{dim}_tier"
        if col not in tagged:
            continue
        sub, rest = tagged[tagged[col] == tier], tagged[tagged[col] != tier]
        s_sub, s_rest = metrics.summarize(sub), metrics.summarize(rest)
        rows.append({
            "Profilo simile al nostro": f"{OPPONENT_DIMENSIONS[dim]['label']}: {tier.lower()}",
            "Partite": s_sub.get("matches", 0),
            "Record": metrics.record(sub) if len(sub) else "—",
            "Punti/partita": metrics.fmt("ppg", s_sub.get("ppg", np.nan)) if len(sub) else "—",
            "Diff. xG/partita": metrics.fmt("xg_diff_pm", s_sub.get("xg_diff_pm", np.nan)) if len(sub) else "—",
            "Diff. xG vs altri": metrics.fmt("xg_diff_pm", s_rest.get("xg_diff_pm", np.nan)) if len(rest) else "—",
            "Campione": metrics.sample_note(s_sub.get("matches", 0), short=True),
        })
    return pd.DataFrame(rows)


def shot_zones(shots: pd.DataFrame) -> dict[str, float]:
    """Share of xG by zone for a set of shots (FotMob 105x68, attacking x=105)."""
    if shots is None or shots.empty:
        return {}
    s = shots.copy()
    s["xg"] = s["xg"].fillna(0)
    total = s["xg"].sum() or np.nan
    in_box = (s["x"] >= 105 - 16.5) & (s["y"].between(34 - 20.16, 34 + 20.16))
    six = (s["x"] >= 105 - 5.5) & (s["y"].between(34 - 9.16, 34 + 9.16))
    set_piece = s["situation"].fillna("").str.contains("SetPiece|FromCorner|FreeKick|Penalty", regex=True)
    header = s["shot_type"].fillna("") == "Header"
    return {
        "Area piccola": s.loc[six, "xg"].sum() / total * 100,
        "Area grande (esclusa area piccola)": s.loc[in_box & ~six, "xg"].sum() / total * 100,
        "Fuori area": s.loc[~in_box, "xg"].sum() / total * 100,
        "Da palla inattiva": s.loc[set_piece, "xg"].sum() / total * 100,
        "Di testa": s.loc[header, "xg"].sum() / total * 100,
    }
