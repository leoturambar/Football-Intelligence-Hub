"""
Shared fixtures. Tests never hit the network: data_loader is pointed at
tests/fixtures/fotmob (3 real Inter matches from Serie A 2026/27, a trimmed
league payload and the league stats CSV) and cache staleness is disabled.
"""

import os
import sys
import warnings

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)  # config.DATA_DIR is relative
warnings.filterwarnings("ignore", message=".*No runtime found.*")

import data_loader as dl  # noqa: E402

FIXTURES = os.path.join(ROOT, "tests", "fixtures", "fotmob")
LEAGUE_ID = 55
TEAM = "Inter"


@pytest.fixture(autouse=True)
def offline_fotmob(monkeypatch):
    monkeypatch.setattr(dl, "_FM_DIR", FIXTURES)
    monkeypatch.setattr(dl, "_is_stale", lambda path, days=0: not os.path.exists(path))

    def no_network(*a, **k):
        raise AssertionError("tests must not call FotMob")

    monkeypatch.setattr(dl, "_fm_get", no_network)
    for fn in (dl.load_fotmob_league, dl.load_team_match_table, dl.load_team_shots,
               dl.load_league_team_stats):
        fn.clear()


@pytest.fixture
def team_matches():
    return dl.load_team_match_table(LEAGUE_ID, None, TEAM)


@pytest.fixture
def league_stats():
    return dl.load_league_team_stats(LEAGUE_ID, None)


def make_matches(rows: list[dict]) -> pd.DataFrame:
    """Synthetic match table with the columns metrics.summarize reads."""
    base = {
        "match_id": 0, "opponent": "X", "venue": "Casa", "round": 1,
        "goals_for": 0, "goals_against": 0, "result": "N", "points": 1,
        "xg": 1.0, "opp_xg": 1.0, "xg_set_play": 0.2, "opp_xg_set_play": 0.2,
        "possession": 50, "shots": 10, "opp_shots": 10, "passes_accurate": 400,
        "passes_accurate_att": 500, "passes_own_half": 200, "passes_opp_half": 200,
        "opp_passes_own_half": 200, "tackles": 15, "interceptions": 10, "fouls": 15,
        "big_chances": 2, "opp_big_chances": 2, "touches_opp_box": 20,
        "aerials_won": 10, "aerials_won_att": 20,
    }
    out = []
    for i, r in enumerate(rows):
        row = dict(base, match_id=i + 1, round=i + 1)
        row.update(r)
        gf, ga = row["goals_for"], row["goals_against"]
        row["result"] = "V" if gf > ga else ("N" if gf == ga else "P")
        row["points"] = 3 if gf > ga else (1 if gf == ga else 0)
        out.append(row)
    return pd.DataFrame(out)
