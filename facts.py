"""
facts.py — Deterministic fact sheets for the LLM narrative.

The LLM never sees raw tables. Code turns metrics into short Italian
sentences with exact numbers ("facts", ids F1, F2, …); the model only
rewrites and orders them, citing ids. `validate` then checks that every
number in the generated text exists in the facts, so invented or misread
numbers are caught before they reach the user.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

import analysis
import metrics


def _n(x, d: int = 2) -> str:
    """Italian decimal formatting: 1.834 → '1,83'."""
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "n/d"
    if isinstance(x, (int, np.integer)) or float(x).is_integer() and d == 0:
        return str(int(round(float(x))))
    return f"{float(x):.{d}f}".replace(".", ",")


def _sheet(lines: list[str]) -> list[dict]:
    return [{"id": f"F{i}", "text": t} for i, t in enumerate(lines, 1) if t]


# ── Team (Tab Squadra) ────────────────────────────────────────────────────────

def team_facts(team: str, sel: pd.DataFrame, summary: dict, ctx: pd.DataFrame,
               findings: list[str] | None = None) -> list[dict]:
    s = summary
    n = int(s.get("matches", 0))
    lines = [
        f"{team} ha giocato {n} partite nel campione analizzato, con record {metrics.record(sel)} "
        f"e {_n(s['ppg'])} punti per partita.",
        f"Gol fatti {int(sel['goals_for'].sum())} e subiti {int(sel['goals_against'].sum())}; "
        f"per partita {_n(s['gf_pm'])} fatti e {_n(s['ga_pm'])} subiti.",
        f"xG prodotti {_n(s['xg_pm'])} a partita, xG concessi {_n(s['xga_pm'])}: "
        f"differenza {_n(s['xg_diff_pm'])} a partita.",
        f"Finalizzazione: {_n(s['finishing'], 1)} gol rispetto agli xG (positivo = segna più del previsto).",
        f"Possesso medio {_n(s['possession'], 1)}% e precisione passaggi {_n(s['pass_accuracy'], 1)}%.",
        f"Il {_n(s['territory'], 1)}% dei passaggi è giocato nella metà campo avversaria.",
        f"PPDA stimato {_n(s['ppda_est'], 1)} (più basso = pressing più intenso; è una stima).",
        f"Tiri: {_n(s['shots_pm'], 1)} a partita fatti e {_n(s['shots_against_pm'], 1)} concessi; "
        f"qualità media {_n(s['xg_per_shot'], 3)} xG per tiro fatto e {_n(s['xga_per_shot'], 3)} per tiro concesso.",
        f"Grandi occasioni: {_n(s['big_chances_pm'], 1)} create e {_n(s['big_chances_against_pm'], 1)} concesse a partita.",
        f"Il {_n(s['set_piece_xg_share'], 0)}% degli xG prodotti e il {_n(s['set_piece_xga_share'], 0)}% "
        f"di quelli concessi arrivano da palla inattiva.",
        f"Porta inviolata in {int(s['clean_sheets'])} partite.",
    ]
    note = metrics.sample_note(n)
    if note:
        lines.append(f"Attenzione al campione: {note}")
    if ctx is not None and not ctx.empty:
        for _, r in ctx[ctx["directional"]].iterrows():
            lines.append(
                f"In campionato (stagione intera) {r['label'].lower()}: {metrics.fmt(r['metric'], r['value']).replace('.', ',')}, "
                f"{r['rank']}° su {r['n']} (media {metrics.fmt(r['metric'], r['league_avg']).replace('.', ',')})."
            )
    for f in findings or []:
        lines.append("Per tipo di avversario — " + f.replace("**", ""))
    return _sheet(lines)


# ── Opponent (Tab Avversario) ─────────────────────────────────────────────────

def opponent_facts(team: str, opp: str, s: dict, rec: str, types: dict, forms: pd.Series,
                   last5: str, zones_for: dict, zones_against: dict,
                   ctx: pd.DataFrame, vs_similar: pd.DataFrame, n: int) -> list[dict]:
    lines = [
        f"{opp} ha giocato {n} partite: record {rec}, {_n(s['ppg'])} punti per partita, ultime 5: {last5}.",
        f"{opp} produce {_n(s['xg_pm'])} xG e ne concede {_n(s['xga_pm'])} a partita.",
        f"Possesso medio di {opp}: {_n(s['possession'], 1)}%; PPDA stimato {_n(s['ppda_est'], 1)}.",
        f"Il {_n(s['set_piece_xga_share'], 0)}% degli xG concessi da {opp} arriva da palla inattiva; "
        f"concede {_n(s['xga_per_shot'], 3)} xG per tiro.",
    ]
    if len(forms):
        lines.append(f"Moduli usati da {opp}: " + ", ".join(f"{k} ({v} volte)" for k, v in forms.items()) + ".")
    if types:
        lines.append(f"Profilo di {opp} nelle fasce del campionato: " + "; ".join(
            f"{analysis.OPPONENT_DIMENSIONS[d]['label'].lower()} {t.lower()}" for d, t in types.items()) + ".")
    if zones_for:
        lines.append(f"Da dove crea {opp} (quota degli xG): " + "; ".join(
            f"{k.lower()} {_n(v, 0)}%" for k, v in zones_for.items()) + ".")
    if zones_against:
        lines.append(f"Da dove concede {opp} (quota degli xG subiti): " + "; ".join(
            f"{k.lower()} {_n(v, 0)}%" for k, v in zones_against.items()) + ".")
    if ctx is not None and not ctx.empty:
        for _, r in ctx[ctx["directional"]].iterrows():
            lines.append(
                f"{opp} in campionato, {r['label'].lower()}: {metrics.fmt(r['metric'], r['value']).replace('.', ',')}, "
                f"{r['rank']}° su {r['n']}."
            )
    if vs_similar is not None and not vs_similar.empty:
        for _, r in vs_similar.iterrows():
            lines.append(
                f"{opp} contro squadre con profilo come {team} ({r['Profilo simile al nostro'].lower()}): "
                f"{r['Partite']} partite, {r['Record']}, differenza xG {r['Diff. xG/partita'].replace('.', ',')} "
                f"(contro le altre {r['Diff. xG vs altri'].replace('.', ',')}); campione {r['Campione']}."
            )
    return _sheet(lines)


# ── Match (Tab Partita) ───────────────────────────────────────────────────────

def match_facts(meta: dict, stats: pd.DataFrame, shots: pd.DataFrame, players: pd.DataFrame) -> list[dict]:
    h, a = meta["home"], meta["away"]
    lines = [f"Risultato finale: {h} {meta['home_goals']}, {a} {meta['away_goals']}."]
    if meta.get("home_formation") or meta.get("away_formation"):
        lines.append(f"Moduli: {h} {meta.get('home_formation') or 'n/d'}, {a} {meta.get('away_formation') or 'n/d'}.")
    for _, r in stats.iterrows():
        dec = 2 if "xG" in r["Metrica"] else 0
        lines.append(f"{r['Metrica']}: {h} {_n(r[h], dec)}, {a} {_n(r[a], dec)}.")
    if shots is not None and not shots.empty:
        for side, name in (("home", h), ("away", a)):
            g = shots[(shots["side"] == side) & shots["is_goal"].astype(bool)].sort_values("minute")
            for _, s in g.iterrows():
                lines.append(f"Gol di {s['player']} ({name}) al minuto {int(s['minute'])}, tiro da {_n(s['xg'])} xG.")
        big = shots[(shots["xg"] >= 0.3) & ~shots["is_goal"].astype(bool)].sort_values("minute")
        for _, s in big.iterrows():
            name = h if s["side"] == "home" else a
            lines.append(f"Occasione mancata di {s['player']} ({name}) al minuto {int(s['minute'])}: {_n(s['xg'])} xG.")
        for side, name in (("home", h), ("away", a)):
            ht = shots[(shots["side"] == side) & (shots["minute"] <= 45)]["xg"].sum()
            st_ = shots[(shots["side"] == side) & (shots["minute"] > 45)]["xg"].sum()
            lines.append(f"{name}: {_n(ht)} xG nel primo tempo e {_n(st_)} nel secondo.")
    if players is not None and not players.empty:
        top = players.dropna(subset=["rating"]).sort_values("rating", ascending=False).head(3)
        for _, p in top.iterrows():
            lines.append(f"Tra i migliori in campo: {p['player']} ({p['team']}), voto FotMob {_n(p['rating'], 1)}.")
    return _sheet(lines)


# ── Rendering & validation ────────────────────────────────────────────────────

def as_prompt(facts: list[dict]) -> str:
    return "\n".join(f"[{f['id']}] {f['text']}" for f in facts)


def as_markdown(facts: list[dict]) -> str:
    """Deterministic fallback text: the facts themselves, as a list."""
    return "\n".join(f"- {f['text']}" for f in facts)


_NUM = re.compile(r"(?<![\w\[])[-+]?\d+(?:[.,]\d+)?")
_CITE = re.compile(r"\[(F\d+(?:\s*,\s*F\d+)*)\]")


def _numbers(text: str) -> set[str]:
    text = _CITE.sub(" ", text)
    out = set()
    for m in _NUM.findall(text):
        v = m.replace(",", ".").lstrip("+")
        try:
            f = float(v)
        except ValueError:
            continue
        out.add(f"{abs(f):g}")
    return out


# Numbers that may appear without being "data": list numbering, half-times, etc.
_HARMLESS = {"1", "2", "3", "4", "5", "45", "90"}


def validate(text: str, facts: list[dict]) -> dict:
    """
    Check an LLM narrative against its fact sheet.
    Returns {'unknown_numbers': [...], 'bad_citations': [...], 'ok': bool}.
    """
    allowed = set()
    for f in facts:
        allowed |= _numbers(f["text"])
    found = _numbers(text)
    unknown = sorted(found - allowed - _HARMLESS, key=lambda x: float(x))
    ids = {f["id"] for f in facts}
    cited = {c.strip() for grp in _CITE.findall(text) for c in grp.split(",")}
    bad = sorted(cited - ids)
    return {"unknown_numbers": unknown, "bad_citations": bad, "ok": not unknown and not bad}


def strip_citations(text: str) -> str:
    return re.sub(r"\s?\[F\d+(?:\s*,\s*F\d+)*\]", "", text)
