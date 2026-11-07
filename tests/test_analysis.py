import numpy as np
import pandas as pd
import pytest

import analysis
import config
from conftest import make_matches


# ── Roles from formation ──────────────────────────────────────────────────────

@pytest.mark.parametrize("formation, expected", [
    ("4-3-3", [["Terzino", "Difensore centrale", "Difensore centrale", "Terzino"],
               ["Centrocampista centrale"] * 3,
               ["Ala", "Centravanti", "Ala"]]),
    ("4-2-3-1", [["Terzino", "Difensore centrale", "Difensore centrale", "Terzino"],
                 ["Mediano", "Mediano"],
                 ["Ala", "Trequartista", "Ala"],
                 ["Centravanti"]]),
    ("3-5-2", [["Difensore centrale"] * 3,
               ["Esterno a tutta fascia", "Centrocampista centrale", "Centrocampista centrale",
                "Centrocampista centrale", "Esterno a tutta fascia"],
               ["Punta", "Punta"]]),
    ("3-4-2-1", [["Difensore centrale"] * 3,
                 ["Esterno a tutta fascia", "Mediano", "Mediano", "Esterno a tutta fascia"],
                 ["Trequartista", "Trequartista"],
                 ["Centravanti"]]),
    ("5-4-1", [["Esterno a tutta fascia", "Difensore centrale", "Difensore centrale",
                "Difensore centrale", "Esterno a tutta fascia"],
               ["Esterno di centrocampo", "Centrocampista centrale", "Centrocampista centrale",
                "Esterno di centrocampo"],
               ["Centravanti"]]),
    ("4-4-2", [["Terzino", "Difensore centrale", "Difensore centrale", "Terzino"],
               ["Esterno di centrocampo", "Centrocampista centrale", "Centrocampista centrale",
                "Esterno di centrocampo"],
               ["Punta", "Punta"]]),
])
def test_line_roles(formation, expected):
    lines = analysis._parse_formation(formation)
    assert analysis._line_roles(lines) == expected


def test_parse_formation_rejects_garbage():
    assert analysis._parse_formation(None) is None
    assert analysis._parse_formation("4-4") is None       # not 10 outfielders
    assert analysis._parse_formation("abc") is None


def test_every_role_has_a_profile():
    produced = {r for f in ("4-3-3", "4-2-3-1", "3-5-2", "3-4-2-1", "5-4-1", "4-4-2")
                for line in analysis._line_roles(analysis._parse_formation(f)) for r in line}
    assert produced <= set(config.ROLE_PROFILES)
    for role, profile in config.ROLE_PROFILES.items():
        assert set(profile) <= set(analysis.PLAYER_METRICS), role


# ── Level 2 ───────────────────────────────────────────────────────────────────

def _league(n=9):
    return pd.DataFrame({
        "team": [f"T{i}" for i in range(n)], "matches": [10] * n,
        "poss_won_att_3rd_pm": np.arange(n, dtype=float),
        "possession": 40 + np.arange(n, dtype=float),
        "xg_total": 10 + np.arange(n, dtype=float),
        "xga_total": 20 - np.arange(n, dtype=float),
    })


def test_opponent_profiles_split_into_equal_tertiles():
    prof = analysis.opponent_profiles(_league())
    for dim in ("press", "possession", "attack", "defence"):
        counts = prof[f"{dim}_tier"].value_counts()
        assert counts.to_dict() == {"Basso": 3, "Medio": 3, "Alto": 3}
    assert prof.loc["T8", "defence_tier"] == "Alto"     # concedes least
    assert prof.loc["T0", "press_tier"] == "Basso"


def test_split_by_opponent_type_counts_matches():
    prof = analysis.opponent_profiles(_league())
    df = make_matches([{"opponent": "T0"}, {"opponent": "T1"}, {"opponent": "T8", "goals_for": 1}])
    split = analysis.split_by_opponent_type(df, prof, "press").set_index("Avversari")
    assert split.loc["Basso", "Partite"] == 2
    assert split.loc["Alto", "Partite"] == 1
    assert split.loc["Alto", "Record"] == "1V 0N 0P"
    assert split.loc["Medio", "Partite"] == 0


def test_next_opponent():
    fx = pd.DataFrame({
        "utc_time": ["2026-01-01", "2026-01-08", "2026-01-15"],
        "home": ["A", "B", "A"], "away": ["B", "A", "C"],
        "finished": [True, False, False], "date": pd.to_datetime(["2026-01-01", "2026-01-08", "2026-01-15"]).date,
        "round": [1, 2, 3],
    })
    nxt = analysis.next_opponent(fx, "A")
    assert nxt["opponent"] == "B" and nxt["venue"] == "Trasferta" and nxt["round"] == 2


def test_shot_zones_partition():
    shots = pd.DataFrame({
        "x": [104, 95, 70], "y": [34, 34, 34], "xg": [0.5, 0.3, 0.2],
        "situation": ["RegularPlay", "FromCorner", "RegularPlay"], "shot_type": ["Header", "RightFoot", "LeftFoot"],
    })
    z = analysis.shot_zones(shots)
    assert z["Area piccola"] + z["Area grande (esclusa area piccola)"] + z["Fuori area"] == pytest.approx(100)
    assert z["Da palla inattiva"] == pytest.approx(30)
    assert z["Di testa"] == pytest.approx(50)


# ── Level 3: fit ──────────────────────────────────────────────────────────────

def _player_table():
    rng = np.random.default_rng(0)
    n = 20
    t = pd.DataFrame({
        "player_id": range(n), "player": [f"P{i}" for i in range(n)], "team": ["X"] * n,
        "role": ["Centravanti"] * n, "minutes": [900] * n, "apps": [10] * n, "starts": [10] * n,
        "rating": [7.0] * n,
    })
    for m in config.ROLE_PROFILES["Centravanti"]:
        t[m] = rng.uniform(0, 1, n)
    return t


def test_role_fit_is_monotonic():
    t = _player_table()
    best = t.copy().iloc[0]
    worst = t.copy().iloc[0]
    for m in config.ROLE_PROFILES["Centravanti"]:
        best[m], worst[m] = 10.0, -1.0
    fit_best, detail = analysis.role_fit(best, "Centravanti", t)
    fit_worst, _ = analysis.role_fit(worst, "Centravanti", t)
    assert fit_best > 90 and fit_worst < 10
    assert set(detail["metric"]) == set(config.ROLE_PROFILES["Centravanti"])


def test_role_fit_needs_minimum_pool():
    t = _player_table().head(config.ROLE_MIN_POOL - 1)
    fit, detail = analysis.role_fit(t.iloc[0], "Centravanti", t)
    assert np.isnan(fit) and detail.empty


def test_lower_is_better_metrics_are_inverted():
    pool = pd.Series([1.0, 2.0, 3.0, 4.0])
    assert analysis._pct_rank(pool, 1.0, lower_better=True) > analysis._pct_rank(pool, 4.0, lower_better=True)


def test_reference_season_extends_the_pool():
    cur = _player_table().head(4)                     # too few on its own
    prev = _player_table().assign(player_id=lambda d: d["player_id"] + 100)
    assert len(analysis.role_pool("Centravanti", cur)) == 4
    assert len(analysis.role_pool("Centravanti", cur, prev)) == 24
    fit_alone, _ = analysis.role_fit(cur.iloc[0], "Centravanti", cur)
    fit_ref, _ = analysis.role_fit(cur.iloc[0], "Centravanti", cur, prev)
    assert np.isnan(fit_alone) and not np.isnan(fit_ref)
    board = analysis.role_leaderboard("Centravanti", cur, prev)
    assert len(board) == 4                            # ranks only current-season players
