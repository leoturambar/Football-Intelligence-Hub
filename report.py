"""
report.py — Exportable reports (Tab Report).

Each builder assembles the same analysis the tabs show into "parts"
(title, subtitle, sections, fact sheet); `render_html` turns parts plus an
optional verified narrative into one self-contained HTML file (charts are
embedded PNGs, no external assets) that prints cleanly to PDF from a browser.
"""

from __future__ import annotations

import base64
import html
import io
import re
from datetime import date

import matplotlib.pyplot as plt
import pandas as pd

import analysis
import config
import data_loader as dl
import facts
import metrics
import viz


# ── Helpers ───────────────────────────────────────────────────────────────────

def fig_uri(fig: plt.Figure) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _metric_cards(summary: dict, keys: list[str]) -> list[tuple[str, str]]:
    return [(metrics.METRICS[k]["label"], metrics.fmt(k, summary.get(k))) for k in keys if k in summary]


def _ctx_table(ctx: pd.DataFrame) -> pd.DataFrame:
    if ctx is None or ctx.empty:
        return pd.DataFrame()
    return pd.DataFrame({
        "Metrica": ctx["label"],
        "Valore": [metrics.fmt(m, v) for m, v in zip(ctx["metric"], ctx["value"])],
        "Media lega": [metrics.fmt(m, v) for m, v in zip(ctx["metric"], ctx["league_avg"])],
        "Posizione": [f"{r}° / {n}" for r, n in zip(ctx["rank"], ctx["n"])],
    })


def _sw_lists(ctx: pd.DataFrame) -> tuple[list[str], list[str]]:
    strengths, weaknesses = metrics.strengths_weaknesses(ctx)
    line = lambda r: f"{r['label']}: {metrics.fmt(r['metric'], r['value'])} — {r['rank']}° su {r['n']}"  # noqa: E731
    return [line(r) for _, r in strengths.iterrows()], [line(r) for _, r in weaknesses.iterrows()]


# ── Builders ──────────────────────────────────────────────────────────────────

def team_parts(league_id: int, league_name: str, season: str | None, team: str,
               last_n: int = 0) -> dict:
    matches = dl.load_team_match_table(league_id, season, team)
    sel = matches.tail(last_n) if last_n else matches
    s = metrics.summarize(sel)
    lg = dl.load_league_team_stats(league_id, season)
    prof = analysis.opponent_profiles(lg)
    ctx = metrics.league_context(team, lg)
    findings = analysis.split_findings(team, sel, prof) if not prof.empty else []
    shots = dl.load_team_shots(league_id, season, team)
    shots = shots[shots["match_id"].isin(sel["match_id"])] if not shots.empty else shots
    strengths, weaknesses = _sw_lists(ctx)
    scope = f"ultime {len(sel)} partite" if last_n else f"tutte le {len(sel)} partite"

    sections = [
        {"h": "Numeri chiave", "kind": "metrics", "items": [("Record", metrics.record(sel))] + _metric_cards(
            s, ["ppg", "gf_pm", "ga_pm", "xg_pm", "xga_pm", "possession", "ppda_est", "territory",
                "xg_per_shot", "clean_sheets"])},
        {"h": "Tiri effettuati e concessi", "kind": "images", "items": [
            fig_uri(viz.plot_shot_map(shots[shots["side"] == "for"].reset_index(drop=True), team, config.HOME_COLOR)),
            fig_uri(viz.plot_shot_map(shots[shots["side"] == "against"].reset_index(drop=True), "Avversari", config.AWAY_COLOR)),
        ]},
        {"h": "Punti di forza (rispetto al campionato)", "kind": "list", "items": strengths or ["Nessuno sopra il 60° percentile."]},
        {"h": "Aree da migliorare", "kind": "list", "items": weaknesses or ["Nessuna area debole rispetto al campionato."]},
        {"h": "Posizione in campionato (stagione intera)", "kind": "table", "df": _ctx_table(ctx)},
    ]
    if not prof.empty:
        for dim in analysis.OPPONENT_DIMENSIONS:
            t = analysis.split_by_opponent_type(sel, prof, dim)
            if not t.empty:
                sections.append({"h": f"Rendimento per tipo di avversario — {analysis.OPPONENT_DIMENSIONS[dim]['label']}",
                                 "kind": "table", "df": t.drop(columns=["_ppg", "_xgd", "Avversari affrontati"])})
        if findings:
            sections.append({"h": "Differenze marcate per tipo di avversario", "kind": "list",
                             "items": [f.replace("**", "") for f in findings]})
    sections.append({"h": "Partite analizzate", "kind": "table", "df": sel[[
        "date", "round", "venue", "opponent", "goals_for", "goals_against", "xg", "opp_xg", "possession", "formation"
    ]].rename(columns={"date": "Data", "round": "G", "venue": "Campo", "opponent": "Avversario", "goals_for": "GF",
                       "goals_against": "GS", "xg": "xG", "opp_xg": "xG avv.", "possession": "Poss. %",
                       "formation": "Modulo"})})
    return {
        "title": f"Report squadra — {team}",
        "subtitle": f"{league_name} {season or ''} · {scope}",
        "sections": sections,
        "facts": facts.team_facts(team, sel, s, ctx, findings),
        "kind": "team",
        "note": metrics.sample_note(len(sel)),
    }


def opponent_parts(league_id: int, league_name: str, season: str | None, team: str, opp: str) -> dict:
    om = dl.load_team_match_table(league_id, season, opp)
    osh = dl.load_team_shots(league_id, season, opp)
    lg = dl.load_league_team_stats(league_id, season)
    prof = analysis.opponent_profiles(lg)
    s = metrics.summarize(om)
    rec = metrics.record(om)
    types = analysis.team_types(opp, prof)
    forms = om["formation"].dropna().value_counts()
    last5 = " ".join(om.tail(5)["result"])
    z_for = analysis.shot_zones(osh[osh["side"] == "for"]) if not osh.empty else {}
    z_against = analysis.shot_zones(osh[osh["side"] == "against"]) if not osh.empty else {}
    ctx = metrics.league_context(opp, lg)
    my_types = analysis.team_types(team, prof)
    vs = analysis.opponent_vs_similar(om, prof, my_types)
    strengths, weaknesses = _sw_lists(ctx)
    nxt = analysis.next_opponent(dl.fotmob_fixtures(league_id, season), team)
    when = (f"Prossima partita: giornata {nxt['round']}, {nxt['date']:%d/%m/%Y}, {team} in "
            f"{'casa' if nxt['venue'] == 'Casa' else 'trasferta'}") if nxt and nxt["opponent"] == opp else ""

    zones = pd.DataFrame({"Zona / tipo": list(z_for) or list(z_against),
                          "% xG creati": [f"{v:.0f}%" for v in z_for.values()] or None,
                          "% xG concessi": [f"{v:.0f}%" for v in z_against.values()] or None})
    sections = [
        {"h": "Profilo", "kind": "metrics", "items": [
            ("Record", rec), ("Ultime 5", last5 or "—"),
            ("Modulo più usato", forms.index[0] if len(forms) else "—"),
            *[(analysis.OPPONENT_DIMENSIONS[d]["label"], t) for d, t in types.items()],
        ] + _metric_cards(s, ["ppg", "xg_pm", "xga_pm", "possession", "ppda_est", "set_piece_xga_share", "xga_per_shot"])},
        {"h": "Dove crea e dove concede", "kind": "images", "items": [
            fig_uri(viz.plot_shot_map(osh[osh["side"] == "for"].reset_index(drop=True), opp, config.AWAY_COLOR)),
            fig_uri(viz.plot_shot_map(osh[osh["side"] == "against"].reset_index(drop=True), f"Contro {opp}", config.HOME_COLOR)),
        ]},
        {"h": "Distribuzione degli xG", "kind": "table", "df": zones},
        {"h": f"Punti di forza di {opp}", "kind": "list", "items": strengths or ["—"]},
        {"h": f"Punti deboli di {opp}", "kind": "list", "items": weaknesses or ["—"]},
    ]
    if not vs.empty:
        sections.append({"h": f"{opp} contro squadre con un profilo simile a {team}", "kind": "table", "df": vs})
    sections.append({"h": "Partite giocate", "kind": "table", "df": om.iloc[::-1][[
        "date", "round", "venue", "opponent", "goals_for", "goals_against", "xg", "opp_xg", "formation"
    ]].rename(columns={"date": "Data", "round": "G", "venue": "Campo", "opponent": "Avversario", "goals_for": "GF",
                       "goals_against": "GS", "xg": "xG", "opp_xg": "xG avv.", "formation": "Modulo"})})
    return {
        "title": f"Report avversario — {opp}",
        "subtitle": f"Preparato per {team} · {league_name} {season or ''}" + (f" · {when}" if when else ""),
        "sections": sections,
        "facts": facts.opponent_facts(team, opp, s, rec, types, forms, last5, z_for, z_against, ctx, vs, len(om)),
        "kind": "opponent",
        "note": metrics.sample_note(len(om)),
    }


def match_parts(match_id: int, league_name: str, season: str | None) -> dict:
    d = dl.match_report_data(match_id)
    m, stats, shots, players = d["meta"], d["stats"], d["shots"], d["players"]
    top = (players.dropna(subset=["rating"]).sort_values("rating", ascending=False).head(8)
           [["player", "team", "rating", "goals", "assists", "xg", "xa"]]
           .rename(columns={"player": "Giocatore", "team": "Squadra", "rating": "Voto", "goals": "Gol",
                            "assists": "Assist", "xg": "xG", "xa": "xA"})) if not players.empty else pd.DataFrame()
    og = [f"{o['minute']}' autogol di {o['player']} ({o['player_team']}), a favore di {o['benefits']}"
          for o in m.get("own_goals", [])]
    sections = [
        {"h": "Tiri", "kind": "images", "items": [fig_uri(viz.plot_match_shots(shots, m["home"], m["away"]))]},
        {"h": "xG cumulati", "kind": "images", "items": [fig_uri(viz.plot_xg_race(shots, m["home"], m["away"]))]},
        {"h": "Statistiche", "kind": "table", "df": stats},
        {"h": "Migliori in campo (voto FotMob)", "kind": "table", "df": top},
    ]
    if og:
        sections.append({"h": "Autogol", "kind": "list", "items": og})
    return {
        "title": f"{m['home']} {m['home_goals']} – {m['away_goals']} {m['away']}",
        "subtitle": (f"{league_name} {season or ''} · giornata {m['round']} · {m['date']} · "
                     f"{m['home_formation'] or 'n/d'} vs {m['away_formation'] or 'n/d'}"),
        "sections": sections,
        "facts": facts.match_facts(m, stats, shots, players),
        "kind": "match",
        "note": "",
    }


# ── HTML ──────────────────────────────────────────────────────────────────────

_CSS = """
:root { --ink:#1b1f2a; --muted:#5d6475; --line:#d9dce3; --accent:#2f5bd3; --ok:#1d7a46; --warn:#a15c00; }
* { box-sizing: border-box; }
body { font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; color: var(--ink);
       max-width: 1000px; margin: 0 auto; padding: 32px 24px 64px; line-height: 1.5; background:#fff; }
h1 { font-size: 28px; margin: 0 0 4px; } h2 { font-size: 18px; margin: 32px 0 10px;
     padding-bottom: 6px; border-bottom: 2px solid var(--line); } h4 { margin: 16px 0 4px; }
.sub { color: var(--muted); margin: 0 0 8px; } .note { color: var(--warn); font-size: 14px; }
.cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); gap: 10px; }
.card { border: 1px solid var(--line); border-radius: 8px; padding: 10px 12px; }
.card .l { color: var(--muted); font-size: 12px; } .card .v { font-size: 20px; font-weight: 600; }
.imgs { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 12px; }
.imgs img { width: 100%; border-radius: 8px; }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
th, td { border-bottom: 1px solid var(--line); padding: 5px 8px; text-align: left; }
th { background: #f4f5f8; }
.narr { background: #f7f8fb; border-left: 4px solid var(--accent); padding: 4px 18px; border-radius: 4px; }
.check-ok { color: var(--ok); font-size: 13px; } .check-warn { color: var(--warn); font-size: 13px; }
.facts li { font-size: 13px; margin-bottom: 2px; }
footer { margin-top: 40px; color: var(--muted); font-size: 12px; }
@media print { body { padding: 0; } h2 { break-after: avoid; } .imgs, table, .card { break-inside: avoid; } }
"""


_BULLET = re.compile(r"^(- |\* |\d+\.\s)")


def _md(text: str) -> str:
    """Minimal markdown → HTML for LLM narratives (bold, headings, bullets, paragraphs)."""
    out, in_list = [], False
    for raw in text.splitlines():
        line = html.escape(raw.strip())
        line = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line)
        if line.startswith(("- ", "* ")) or re.match(r"^\d+\.\s", line):
            if not in_list:
                out.append("<ul>")
                in_list = True
            item = _BULLET.sub("", line)
            out.append(f"<li>{item}</li>")
            continue
        if in_list:
            out.append("</ul>")
            in_list = False
        if not line:
            continue
        if line.startswith("#"):
            out.append(f"<h4>{line.lstrip('#').strip()}</h4>")
        elif re.fullmatch(r"<strong>.+</strong>:?", line):
            out.append(f"<h4>{line}</h4>")
        else:
            out.append(f"<p>{line}</p>")
    if in_list:
        out.append("</ul>")
    return "\n".join(out)


def _table(df: pd.DataFrame) -> str:
    if df is None or df.empty:
        return "<p class='sub'>Dati non disponibili.</p>"
    d = df.copy()
    for c in d.columns:
        if pd.api.types.is_float_dtype(d[c]):
            d[c] = d[c].map(lambda v: "" if pd.isna(v) else f"{v:.2f}")
    return d.to_html(index=False, border=0, escape=True)


def render_html(parts: dict, narrative: dict | None = None, model: str | None = None) -> str:
    body = [f"<h1>{html.escape(parts['title'])}</h1>",
            f"<p class='sub'>{html.escape(parts['subtitle'])}</p>"]
    if parts.get("note"):
        body.append(f"<p class='note'>{html.escape(parts['note'])}</p>")
    if narrative:
        chk = narrative["check"]
        status = ("<p class='check-ok'>✔ Testo verificato: ogni numero compare nei fatti in fondo al report"
                  f"{f' ({html.escape(model)})' if model else ''}.</p>") if chk["ok"] else (
            "<p class='check-warn'>⚠ Da controllare: numeri non presenti nei fatti: "
            f"{html.escape(', '.join(chk['unknown_numbers'] + chk['bad_citations']))}. Fanno fede i fatti.</p>")
        body.append("<h2>Analisi</h2>")
        body.append(f"<div class='narr'>{_md(facts.strip_citations(narrative['text']))}</div>{status}")
    for sec in parts["sections"]:
        body.append(f"<h2>{html.escape(sec['h'])}</h2>")
        if sec["kind"] == "metrics":
            body.append("<div class='cards'>" + "".join(
                f"<div class='card'><div class='l'>{html.escape(str(l))}</div><div class='v'>{html.escape(str(v))}</div></div>"
                for l, v in sec["items"]) + "</div>")
        elif sec["kind"] == "images":
            body.append("<div class='imgs'>" + "".join(f"<img src='{u}' alt=''>" for u in sec["items"]) + "</div>")
        elif sec["kind"] == "table":
            body.append(_table(sec["df"]))
        elif sec["kind"] == "list":
            body.append("<ul>" + "".join(f"<li>{html.escape(str(i))}</li>" for i in sec["items"]) + "</ul>")
    body.append("<h2>Fatti di riferimento</h2>")
    body.append("<ol class='facts'>" + "".join(f"<li>{html.escape(f['text'])}</li>" for f in parts["facts"]) + "</ol>")
    body.append(f"<footer>Football Intelligence Hub · dati FotMob · generato il {date.today():%d/%m/%Y}. "
                "Il PPDA è una stima; con meno di 8 partite i numeri sono indicativi.</footer>")
    return (f"<!doctype html><html lang='it'><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width, initial-scale=1'>"
            f"<title>{html.escape(parts['title'])}</title><style>{_CSS}</style></head>"
            f"<body>{''.join(body)}</body></html>")


def filename(parts: dict) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", parts["title"].lower()).strip("-")
    return f"{slug}-{date.today():%Y%m%d}.html"
