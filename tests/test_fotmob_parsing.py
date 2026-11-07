"""
Parsing of real (cached) FotMob payloads. If FotMob changes its schema,
refresh the fixtures from data/fotmob/ and these tests show what broke.
"""

import analysis
import data_loader as dl
import facts
import metrics
from conftest import LEAGUE_ID, TEAM


def test_fixtures_parse(team_matches):
    fx = dl.fotmob_fixtures(LEAGUE_ID, None)
    assert fx["finished"].sum() == 3
    assert (~fx["finished"]).sum() == 1
    assert TEAM in dl.fotmob_teams(LEAGUE_ID, None)


def test_team_match_table(team_matches):
    tm = team_matches
    assert len(tm) == 3
    for col in ("possession", "xg", "opp_xg", "shots", "opp_shots", "passes_own_half",
                "passes_opp_half", "tackles", "interceptions", "fouls", "formation", "coach"):
        assert col in tm.columns, col
    assert ((tm["possession"] + tm["opp_possession"]) == 100).all()
    assert set(tm["result"]) <= {"V", "N", "P"}


def test_milan_inter_known_values(team_matches):
    row = team_matches[team_matches["opponent"] == "Milan"].iloc[0]
    assert (row["goals_for"], row["goals_against"]) == (1, 3)
    assert row["venue"] == "Trasferta"
    assert row["xg"] == 1.68 and row["opp_xg"] == 0.62
    assert row["shots"] == 19 and row["opp_shots"] == 7


def test_summary_on_real_matches_has_no_gaps(team_matches):
    s = metrics.summarize(team_matches)
    assert all(v == v for v in s.values()), s  # no NaN


def test_shots_match_goals_and_skip_own_goals(team_matches):
    # Venezia 0-2 Inter was decided by two Venezia own goals: they must not
    # appear as Venezia shots, and shot goals + own goals must equal the score.
    shots = dl.load_team_shots(LEAGUE_ID, None, TEAM)
    own_goals_for = 0
    for mid in team_matches["match_id"]:
        m = dl.load_fotmob_match(mid)
        inter_id = next(t["id"] for t in m["header"]["teams"] if t["name"] == TEAM)
        own_goals_for += sum(1 for s in m["shots"] if s.get("isOwnGoal") and s["teamId"] != inter_id)
    assert own_goals_for == 2
    goals_from_shots = int(shots[shots["side"] == "for"]["is_goal"].sum())
    assert goals_from_shots + own_goals_for == team_matches["goals_for"].sum()
    venezia = shots[shots["match_id"] == 5749729]
    assert not venezia["is_goal"].any()


def test_league_stats_and_context(league_stats):
    assert len(league_stats) == 20
    assert set(dl.FM_LEAGUE_STATS.values()) <= set(league_stats.columns)
    ctx = metrics.league_context(TEAM, league_stats)
    assert not ctx.empty and ctx["rank"].between(1, 20).all()


def test_match_report_and_facts():
    d = dl.match_report_data(5749730)  # Milan 3-1 Inter
    assert d["meta"]["home"] == "Milan" and d["meta"]["home_goals"] == 3
    assert not d["stats"].empty and not d["players"].empty
    sheet = facts.match_facts(d["meta"], d["stats"], d["shots"], d["players"])
    assert any("Pulisic" in f["text"] for f in sheet)
    assert facts.validate(facts.as_markdown(sheet), sheet)["ok"]


def test_player_roles_from_fixture_lineups():
    apps = dl.load_league_player_appearances(LEAGUE_ID, None)
    roles = analysis.assign_roles(apps)
    starters = roles[roles["started"]]
    assert len(starters) == 3 * 22
    assert starters["role"].notna().all()
    assert (starters[starters["is_gk"]]["role"] == "Portiere").all()
    table = analysis.player_season_table(apps)
    barella = table[table["player"] == "Nicolò Barella"].iloc[0]
    assert barella["team"] == "Inter" and barella["minutes"] > 0


def test_match_facts_include_own_goals():
    d = dl.match_report_data(5749729)  # Venezia 0-2 Inter, two Venezia own goals
    assert len(d["meta"]["own_goals"]) == 2
    assert all(og["benefits"] == "Inter" for og in d["meta"]["own_goals"])
    sheet = facts.match_facts(d["meta"], d["stats"], d["shots"], d["players"])
    assert sum("Autogol" in f["text"] for f in sheet) == 2
