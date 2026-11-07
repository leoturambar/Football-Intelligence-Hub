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

import config
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


# ══════════════════════════════════════════════════════════════════════════════
# Level 3 — players: roles, role fit, mismatch, weak links, key players
# ══════════════════════════════════════════════════════════════════════════════

# metric id → (label, numerator key, denominator key, kind[, "low"])
#   kind "p90": numerator per 90 minutes · "pct": 100 * numerator / denominator
#   "low" marks lower-is-better metrics (inverted in percentiles)
PLAYER_METRICS: dict[str, tuple] = {
    "goals":           ("Gol/90",                        "goals",                      None,                      "p90"),
    "xg":              ("xG/90",                         "expected_goals",             None,                      "p90"),
    "xa":              ("xA/90",                         "expected_assists",           None,                      "p90"),
    "shots":           ("Tiri/90",                       "total_shots",                None,                      "p90"),
    "chances":         ("Occasioni create/90",           "chances_created",            None,                      "p90"),
    "final_third":     ("Passaggi nell'ultimo terzo/90", "passes_into_final_third",    None,                      "p90"),
    "pass_pct":        ("Precisione passaggi %",         "accurate_passes",            "accurate_passes_att",     "pct"),
    "long_balls":      ("Lanci lunghi riusciti/90",      "long_balls_accurate",        None,                      "p90"),
    "long_ball_pct":   ("Precisione lanci lunghi %",     "long_balls_accurate",        "long_balls_accurate_att", "pct"),
    "crosses":         ("Cross riusciti/90",             "accurate_crosses",           None,                      "p90"),
    "dribbles":        ("Dribbling riusciti/90",         "dribbles_succeeded",         None,                      "p90"),
    "box_touches":     ("Tocchi in area avversaria/90",  "touches_opp_box",            None,                      "p90"),
    "touches":         ("Tocchi/90",                     "touches",                    None,                      "p90"),
    "tackles":         ("Contrasti/90",                  "matchstats.headers.tackles", None,                      "p90"),
    "interceptions":   ("Intercetti/90",                 "interceptions",              None,                      "p90"),
    "recoveries":      ("Palloni recuperati/90",         "recoveries",                 None,                      "p90"),
    "clearances":      ("Respinte/90",                   "clearances",                 None,                      "p90"),
    "aerials":         ("Duelli aerei vinti/90",         "aerials_won",                None,                      "p90"),
    "aerial_pct":      ("Duelli aerei vinti %",          "aerials_won",                "aerials_won_att",         "pct"),
    "ground_pct":      ("Duelli a terra vinti %",        "ground_duels_won",           "ground_duels_won_att",    "pct"),
    "dribbled_past":   ("Volte saltato/90",              "dribbled_past",              None,                      "p90", "low"),
    "dispossessed":    ("Palloni persi/90",              "dispossessed",               None,                      "p90", "low"),
    "fouls":           ("Falli commessi/90",             "fouls",                      None,                      "p90", "low"),
    "saves":           ("Parate/90",                     "saves",                      None,                      "p90"),
    "goals_prevented": ("Gol evitati/90",                "goals_prevented",            None,                      "p90"),
    "save_pct":        ("Parate %",                      "saves",                      "_on_target_faced",        "pct"),
}

ROLES = list(config.ROLE_PROFILES)
# Near-identical roles share a family: an "alternative role" must change family
ROLE_FAMILY = {
    "Portiere": "gk",
    "Difensore centrale": "cb",
    "Terzino": "fullback", "Esterno a tutta fascia": "fullback",
    "Mediano": "cm", "Centrocampista centrale": "cm",
    "Esterno di centrocampo": "wide", "Ala": "wide",
    "Trequartista": "am",
    "Punta": "fw", "Centravanti": "fw",
}
_USUAL_FALLBACK = {0: "Portiere", 1: "Difensore centrale", 2: "Centrocampista centrale", 3: "Centravanti"}


def _parse_formation(formation) -> list[int] | None:
    try:
        lines = [int(x) for x in str(formation).split("-")]
    except ValueError:
        return None
    return lines if sum(lines) == 10 and len(lines) >= 2 else None


def _line_roles(lines: list[int]) -> list[list[str]]:
    """Role for each slot (sorted by lateral position) of each outfield line."""
    k = len(lines) - 1
    out = []
    for i, n in enumerate(lines):
        slots = []
        for j in range(n):
            extreme = j in (0, n - 1) and n > 1
            if i == 0:
                role = ("Esterno a tutta fascia" if n >= 5 and extreme
                        else "Terzino" if n == 4 and extreme else "Difensore centrale")
            elif i == k:
                role = ("Ala" if n >= 3 and extreme
                        else "Centravanti" if n in (1, 3) else "Punta")
            elif n >= 4 and extreme:
                role = ("Esterno a tutta fascia" if lines[0] == 3 and i == 1
                        else "Ala" if i == k - 1 and i > 1 else "Esterno di centrocampo")
            elif i < k - 1:  # another midfield line follows: holding line
                centrals = n - (2 if n >= 4 else 0)
                role = "Mediano" if centrals <= 2 else "Centrocampista centrale"
            elif i > 1:      # attacking-midfield line
                role = "Ala" if n == 3 and extreme else "Trequartista"
            else:            # single midfield line
                role = "Centrocampista centrale"
            slots.append(role)
        out.append(slots)
    return out


def assign_roles(apps: pd.DataFrame) -> pd.DataFrame:
    """
    Add 'role' to every appearance. Starters: formation + FotMob positionId
    (line = order of sorted positionIds, side = positionId % 10). Substitutes
    and unparseable lineups: the player's most-played starting role, else a
    fallback from FotMob's usual position.
    """
    apps = apps.copy()
    apps["role"] = None
    gk = apps["is_gk"].astype(bool)
    apps.loc[gk & apps["started"], "role"] = "Portiere"

    starters = apps[apps["started"] & ~gk & apps["position_id"].notna()]
    for _, grp in starters.groupby(["match_id", "team_id"]):
        lines = _parse_formation(grp["formation"].iloc[0])
        if not lines or len(grp) != 10:
            continue
        roles = _line_roles(lines)
        g = grp.assign(pid=grp["position_id"].astype(int)).sort_values("pid")
        start = 0
        for i, n in enumerate(lines):
            line = g.iloc[start:start + n]
            line = line.assign(lat=line["pid"] % 10).sort_values("lat")
            for idx, role in zip(line.index, roles[i]):
                apps.at[idx, "role"] = role
            start += n

    mins = apps["minutes_played"].fillna(0) if "minutes_played" in apps else pd.Series(0, index=apps.index)
    known = apps[apps["role"].notna()].assign(_m=mins)
    main_role = (known.groupby(["player_id", "role"])["_m"].sum().reset_index()
                 .sort_values("_m").drop_duplicates("player_id", keep="last")
                 .set_index("player_id")["role"])
    apps["role"] = (apps["role"].fillna(apps["player_id"].map(main_role))
                    .fillna(apps["usual_position"].map(_USUAL_FALLBACK)))
    apps.loc[gk, "role"] = "Portiere"
    return apps


def player_season_table(apps: pd.DataFrame) -> pd.DataFrame:
    """
    One row per player and team: minutes, apps, starts, main role (by
    minutes), minutes-weighted FotMob rating, and every PLAYER_METRICS value.
    """
    if apps is None or apps.empty:
        return pd.DataFrame()
    a = assign_roles(apps)
    a["minutes_played"] = a["minutes_played"].fillna(0)
    if {"saves", "goals_conceded"}.issubset(a.columns):
        a["_on_target_faced"] = a["saves"].fillna(0) + a["goals_conceded"].fillna(0)

    keys = sorted(({s[1] for s in PLAYER_METRICS.values()}
                   | {s[2] for s in PLAYER_METRICS.values() if s[2]}) & set(a.columns))
    by = ["player_id", "player", "team"]
    sums = a.groupby(by)[keys + ["minutes_played"]].sum(min_count=1)
    out = a.groupby(by).agg(apps=("match_id", "nunique"), starts=("started", "sum"))
    out["minutes"] = sums["minutes_played"]
    out["role"] = (a.groupby(by + ["role"])["minutes_played"].sum().reset_index()
                   .sort_values("minutes_played").drop_duplicates(by, keep="last")
                   .set_index(by)["role"])
    if "rating_title" in a.columns:
        rated = a[a["rating_title"].notna()]
        out["rating"] = ((rated["rating_title"] * rated["minutes_played"]).groupby([rated[c] for c in by]).sum()
                         / rated.groupby(by)["minutes_played"].sum().replace(0, np.nan))

    m90 = (sums["minutes_played"] / 90).replace(0, np.nan)
    for mid, spec in PLAYER_METRICS.items():
        num, den, kind = spec[1], spec[2], spec[3]
        if num not in sums:
            continue
        if kind == "p90":
            out[mid] = sums[num] / m90
        elif den in sums:
            out[mid] = 100 * sums[num] / sums[den].replace(0, np.nan)
    return out.reset_index()


def _pct_rank(values: pd.Series, x, lower_better: bool) -> float:
    v = values.dropna()
    if v.empty or pd.isna(x):
        return np.nan
    p = (v < x).mean() * 100 + (v == x).mean() * 50
    return 100 - p if lower_better else p


def role_pool(role: str, table: pd.DataFrame) -> pd.DataFrame:
    return table[(table["role"] == role) & (table["minutes"] >= config.PLAYER_MIN_MINUTES)]


def role_fit(player: pd.Series, role: str, table: pd.DataFrame) -> tuple[float, pd.DataFrame]:
    """
    Weighted mean percentile of *player* against league players whose main
    role is *role* (≥ PLAYER_MIN_MINUTES). Returns (score 0–100, detail).
    """
    pool = role_pool(role, table)
    if len(pool) < config.ROLE_MIN_POOL:
        return np.nan, pd.DataFrame()
    rows = []
    for mid, w in config.ROLE_PROFILES[role].items():
        if mid not in table.columns or mid not in PLAYER_METRICS:
            continue
        spec = PLAYER_METRICS[mid]
        low = len(spec) > 4 and spec[4] == "low"
        rows.append({
            "metric": mid, "Metrica": spec[0], "Valore": player.get(mid),
            "Mediana ruolo": pool[mid].median(),
            "Percentile": _pct_rank(pool[mid], player.get(mid), low), "Peso": w,
        })
    d = pd.DataFrame(rows).dropna(subset=["Percentile"])
    if d.empty:
        return np.nan, d
    return float(np.average(d["Percentile"], weights=d["Peso"])), d


def team_player_report(team: str, table: pd.DataFrame) -> pd.DataFrame:
    """
    For every player of *team* with enough minutes: fit in the main role,
    best alternative role (mismatch) and weak-link flag.
    """
    t = table[(table["team"] == team) & (table["minutes"] >= config.PLAYER_MIN_MINUTES)]
    rows = []
    for _, p in t.iterrows():
        fit, _ = role_fit(p, p["role"], table)
        best_role, best_fit = None, np.nan
        family = ROLE_FAMILY.get(p["role"])
        candidates = [] if p["role"] == "Portiere" else [
            r for r in ROLES if r != "Portiere" and ROLE_FAMILY.get(r) != family]
        for r in candidates:
            f_alt, _ = role_fit(p, r, table)
            if not np.isnan(f_alt) and (np.isnan(best_fit) or f_alt > best_fit):
                best_role, best_fit = r, f_alt
        rows.append({
            "player_id": p["player_id"], "Giocatore": p["player"], "Ruolo": p["role"],
            "Minuti": int(p["minutes"]), "Presenze": int(p["apps"]), "Da titolare": int(p["starts"]),
            "Voto medio FotMob": p.get("rating"), "Idoneità al ruolo": fit,
            "Ruolo alternativo": best_role, "Idoneità alternativa": best_fit,
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["Profilo più vicino ad altro ruolo"] = (df["Idoneità alternativa"] - df["Idoneità al ruolo"]) >= 15
    df["Anello debole"] = df["Idoneità al ruolo"] < 30
    return df.sort_values("Minuti", ascending=False).reset_index(drop=True)


def on_off_impact(team_matches: pd.DataFrame, apps: pd.DataFrame, team: str,
                  min_each: int = 2) -> pd.DataFrame:
    """
    'Remove-one' proxy: team xG difference and points per match with the
    player in the starting XI vs without. Needs ≥ min_each matches each side.
    Correlation, not causation: opponents and other absences differ too.
    """
    ta = apps[(apps["team"] == team) & apps["started"]]
    played = set(team_matches["match_id"])
    rows = []
    for (pid, name), g in ta.groupby(["player_id", "player"]):
        on_ids = set(g["match_id"]) & played
        on = team_matches[team_matches["match_id"].isin(on_ids)]
        off = team_matches[~team_matches["match_id"].isin(on_ids)]
        if len(on) < min_each or len(off) < min_each:
            continue
        s_on, s_off = metrics.summarize(on), metrics.summarize(off)
        rows.append({
            "player_id": pid, "Giocatore": name, "Da titolare": len(on), "Senza": len(off),
            "Diff. xG con": s_on["xg_diff_pm"], "Diff. xG senza": s_off["xg_diff_pm"],
            "Impatto xG/partita": s_on["xg_diff_pm"] - s_off["xg_diff_pm"],
            "Punti/partita con": s_on["ppg"], "Punti/partita senza": s_off["ppg"],
        })
    df = pd.DataFrame(rows)
    return df.sort_values("Impatto xG/partita", ascending=False).reset_index(drop=True) if not df.empty else df


def role_leaderboard(role: str, table: pd.DataFrame) -> pd.DataFrame:
    """
    Every league player whose main role is *role* (enough minutes), ranked by
    role fit. One percentile column per profile metric.
    """
    pool = role_pool(role, table)
    if len(pool) < config.ROLE_MIN_POOL:
        return pd.DataFrame()
    rows = []
    for _, p in pool.iterrows():
        fit, detail = role_fit(p, role, table)
        row = {"player_id": p["player_id"], "Giocatore": p["player"], "Squadra": p["team"],
               "Minuti": int(p["minutes"]), "Voto medio FotMob": p.get("rating"), "Idoneità": fit}
        row.update({f"{m} (pct)": v for m, v in zip(detail.get("Metrica", []), detail.get("Percentile", []))})
        rows.append(row)
    df = pd.DataFrame(rows).sort_values("Idoneità", ascending=False).reset_index(drop=True)
    df.insert(0, "#", range(1, len(df) + 1))
    pct_cols = [c for c in df.columns if c.endswith("(pct)")]
    df[pct_cols] = df[pct_cols].round(0)
    return df
