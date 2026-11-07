import math

import pandas as pd
import pytest

import metrics
from conftest import make_matches


def test_summarize_basic_rates():
    df = make_matches([
        {"goals_for": 2, "goals_against": 0, "xg": 2.0, "opp_xg": 0.5},
        {"goals_for": 1, "goals_against": 1, "xg": 1.0, "opp_xg": 1.5},
    ])
    s = metrics.summarize(df)
    assert s["matches"] == 2
    assert s["ppg"] == pytest.approx(2.0)          # 3 + 1 points
    assert s["xg_pm"] == pytest.approx(1.5)
    assert s["xga_pm"] == pytest.approx(1.0)
    assert s["xg_diff_pm"] == pytest.approx(0.5)
    assert s["finishing"] == pytest.approx(0.0)    # 3 goals vs 3.0 xG
    assert s["clean_sheets"] == 1


def test_summarize_ratios():
    df = make_matches([{"passes_own_half": 100, "passes_opp_half": 300,
                        "opp_passes_own_half": 160, "tackles": 10, "interceptions": 5, "fouls": 5,
                        "xg": 2.0, "xg_set_play": 0.5}])
    s = metrics.summarize(df)
    assert s["territory"] == pytest.approx(75.0)
    assert s["ppda_est"] == pytest.approx(160 / 20)
    assert s["set_piece_xg_share"] == pytest.approx(25.0)
    assert s["pass_accuracy"] == pytest.approx(80.0)


def test_summarize_empty():
    assert metrics.summarize(make_matches([]).iloc[0:0]) == {"matches": 0}


def test_record_and_sample_note():
    df = make_matches([{"goals_for": 1}, {"goals_against": 1}, {}])
    assert metrics.record(df) == "1V 1N 1P"
    assert metrics.sample_note(2, short=True) == "aneddotico"
    assert metrics.sample_note(5, short=True) == "indicativo"
    assert metrics.sample_note(8, short=True) == "solido"
    assert metrics.sample_note(8) == ""


def test_fmt_handles_nan():
    assert metrics.fmt("xg_pm", float("nan")) == "—"
    assert metrics.fmt("xg_diff_pm", 0.5) == "+0.50"


def test_compare_has_one_row_per_metric():
    a = make_matches([{"goals_for": 2}])
    b = make_matches([{"goals_against": 2}])
    t = metrics.compare(a, b, "A", "B")
    assert list(t.columns) == ["Metrica", "A", "B"]
    assert len(t) == len(metrics.METRICS)


def _league():
    teams = [f"T{i}" for i in range(6)]
    return pd.DataFrame({
        "team": teams, "matches": [10] * 6,
        "possession": [40, 45, 50, 55, 60, 65],
        "xg_total": [10, 12, 14, 16, 18, 20],
        "xga_total": [20, 18, 16, 14, 12, 10],
        "goals_pm": [1.0] * 6, "goals_conceded_pm": [1.0] * 6,
        "big_chances_total": [20] * 6, "touches_opp_box_total": [200] * 6,
        "tackles_pm": [15] * 6, "interceptions_pm": [10] * 6,
    })


def test_league_context_ranks_respect_direction():
    ctx = metrics.league_context("T5", _league()).set_index("metric")
    assert ctx.loc["xg_pm", "rank"] == 1          # most xG = best
    assert ctx.loc["xga_pm", "rank"] == 1         # least xGA = best (lower is better)
    assert ctx.loc["xg_pm", "value"] == pytest.approx(2.0)
    assert ctx.loc["xga_pm", "pct"] == pytest.approx(100.0)


def test_league_context_unknown_team():
    assert metrics.league_context("Nope", _league()).empty


def test_strengths_and_relative_weaknesses():
    ctx = metrics.league_context("T5", _league())
    strengths, weaknesses = metrics.strengths_weaknesses(ctx)
    assert "xg_pm" in set(strengths["metric"])
    # every directional metric is either a strength or ≥ 90th pct, never both
    assert not set(strengths["metric"]) & set(weaknesses["metric"])
    assert all(not math.isnan(p) for p in ctx["pct"])
