import pandas as pd

import metrics
import report
from conftest import LEAGUE_ID, TEAM


# ── Cross-league comparison ───────────────────────────────────────────────────

def _league(xg_totals, xga_totals, prefix):
    n = len(xg_totals)
    return pd.DataFrame({
        "team": [f"{prefix}{i}" for i in range(n)], "matches": [10] * n,
        "possession": [50.0] * n, "xg_total": xg_totals, "xga_total": xga_totals,
        "goals_pm": [1.5] * n, "goals_conceded_pm": [1.5] * n,
    })


def test_equivalent_positions_rank_value_in_other_leagues():
    a = _league([30, 20, 10], [10, 20, 30], "A")       # A0 = 3.0 xG/match
    b = _league([40, 35, 5, 1], [5, 10, 30, 40], "B")
    eq = metrics.equivalent_positions("A0", "A", {"A": a, "B": b}).set_index("Metrica")
    assert eq.loc["xG / partita", "A"] == "1° / 3"
    assert eq.loc["xG / partita", "B"] == "3° / 4"          # 3.0 sits below 4.0 and 3.5
    assert eq.loc["xG concessi / partita", "B"] == "2° / 4"  # 1.0 conceded: only 0.5 is better


def test_league_averages_skip_trivial_rows():
    avg = metrics.league_averages({"A": _league([30, 10], [10, 30], "A")})
    assert "Possesso medio %" not in avg.index            # always 50 by construction
    assert avg.loc["xG / partita", "A"] == 2.0


def test_equivalent_positions_unknown_team():
    assert metrics.equivalent_positions("Nope", "A", {"A": _league([1, 2], [2, 1], "A")}).empty


# ── Report HTML ───────────────────────────────────────────────────────────────

NARR = {"text": "**Identità**\n- Primo punto [F1]\nSecondo <b>paragrafo</b> [F2].",
        "check": {"ok": True, "unknown_numbers": [], "bad_citations": []}}


def test_team_report_is_self_contained():
    parts = report.team_parts(LEAGUE_ID, "Serie A", None, TEAM)
    html = report.render_html(parts, NARR, "qwen3.5:9b")
    assert html.startswith("<!doctype html>")
    assert "http://" not in html and "https://" not in html   # no external assets
    assert html.count("data:image/png;base64,") >= 2
    assert "[F1]" not in html                                  # citations stripped
    assert "&lt;b&gt;paragrafo&lt;/b&gt;" in html              # model text is escaped
    assert "Fatti di riferimento" in html and "Testo verificato" in html


def test_match_report_lists_own_goals():
    parts = report.match_parts(5749729, "Serie A", None)  # Venezia 0-2 Inter (two own goals)
    html = report.render_html(parts)
    assert "Autogol" in html and parts["title"] == "Venezia 0 – 2 Inter"


def test_unverified_narrative_is_flagged():
    parts = report.match_parts(5749730, "Serie A", None)
    bad = {"text": "Inter ha tirato 99 volte.", "check": {"ok": False, "unknown_numbers": ["99"], "bad_citations": []}}
    assert "Da controllare" in report.render_html(parts, bad)


def test_filename_is_safe():
    assert report.filename({"title": "Report avversario — Hellas Verona"}).startswith("report-avversario-hellas-verona-")
