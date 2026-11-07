"""
smoke_test.py — Live check of the FotMob pipeline, outside Streamlit.

Runs every loader and analysis step on real data for each league in
config.FOTMOB_LEAGUES (current season) plus optional past seasons, and
prints one line per check. Use it after FotMob changes or before relying on
a new league/season:

    python smoke_test.py                      # 5 leagues, current season, team level
    python smoke_test.py --players            # + league-wide player data (downloads all matches)
    python smoke_test.py --season 2025/2026   # a past season instead of the current one
"""

from __future__ import annotations

import argparse
import sys
import time
import traceback

import analysis
import config
import data_loader as dl
import facts
import metrics


def check(label: str, fn):
    t0 = time.time()
    try:
        detail = fn()
        print(f"  OK   {label:<38} {detail} ({time.time() - t0:.1f}s)", flush=True)
        return True
    except Exception as e:  # report and keep going
        print(f"  FAIL {label:<38} {type(e).__name__}: {e}", flush=True)
        traceback.print_exc(limit=2, file=sys.stdout)
        return False


def run_league(name: str, league_id: int, season: str | None, players: bool) -> bool:
    print(f"\n== {name} ({league_id}) · {season or 'stagione corrente'}", flush=True)
    ok = True
    st: dict = {}

    def fixtures():
        fx = dl.fotmob_fixtures(league_id, season)
        st["fx"] = fx
        teams = dl.fotmob_teams(league_id, season)
        st["team"] = sorted(teams)[0]
        assert fx["finished"].any(), "no finished matches"
        return f"{len(fx)} partite, {int(fx['finished'].sum())} giocate, {len(teams)} squadre"

    def team_table():
        tm = dl.load_team_match_table(league_id, season, st["team"])
        st["tm"] = tm
        for col in ("possession", "xg", "opp_xg", "shots", "passes_own_half", "tackles"):
            assert col in tm.columns, f"missing column {col}"
        assert tm["xg"].notna().all(), "xg has gaps"
        return f"{st['team']}: {len(tm)} partite, {tm.shape[1]} colonne"

    def summary():
        s = metrics.summarize(st["tm"])
        bad = [k for k, v in s.items() if v != v]  # NaN
        assert not bad, f"NaN metrics: {bad}"
        return f"ppg {s['ppg']:.2f}, xG {s['xg_pm']:.2f}, PPDA {s['ppda_est']:.1f}"

    def league_stats():
        lg = dl.load_league_team_stats(league_id, season)
        st["lg"] = lg
        missing = set(dl.FM_LEAGUE_STATS.values()) - set(lg.columns)
        assert not missing, f"missing league stats {missing}"
        ctx = metrics.league_context(st["team"], lg)
        assert not ctx.empty, f"{st['team']} not found in league stats"
        return f"{len(lg)} squadre, {len(ctx)} metriche di contesto"

    def level2():
        prof = analysis.opponent_profiles(st["lg"])
        tagged = analysis.tag_opponents(st["tm"], prof)
        untagged = tagged["press_tier"].isna().sum()
        assert untagged == 0, f"{untagged} opponents without tier (name mismatch?)"
        st["prof"] = prof
        return "fasce assegnate a tutti gli avversari"

    def shots_and_match():
        sh = dl.load_team_shots(league_id, season, st["team"])
        d = dl.match_report_data(int(st["tm"].iloc[-1]["match_id"]))
        assert not d["stats"].empty and not d["players"].empty
        fs = facts.match_facts(d["meta"], d["stats"], d["shots"], d["players"])
        assert facts.validate(facts.as_markdown(fs), fs)["ok"]
        return f"{len(sh)} tiri, report partita con {len(fs)} fatti"

    def opponent():
        nxt = analysis.next_opponent(st["fx"], st["team"])
        return f"prossimo avversario: {nxt['opponent'] if nxt else 'nessuno (stagione finita)'}"

    for label, fn in [("calendario e squadre", fixtures), ("tabella partite squadra", team_table),
                      ("metriche squadra", summary), ("statistiche di lega", league_stats),
                      ("fasce avversari (Livello 2)", level2), ("tiri e report partita", shots_and_match),
                      ("prossimo avversario", opponent)]:
        if not check(label, fn):
            ok = False
            if label in ("calendario e squadre", "tabella partite squadra"):
                return False

    if players:
        def player_data():
            apps = dl.load_league_player_appearances(league_id, season)
            table = analysis.player_season_table(apps)
            no_role = int(analysis.assign_roles(apps).query("started")["role"].isna().sum())
            assert no_role == 0, f"{no_role} starters without role"
            rep = analysis.team_player_report(st["team"], table)
            pools = {r: len(analysis.role_pool(r, table)) for r in analysis.ROLES}
            small = [r for r, n in pools.items() if n < config.ROLE_MIN_POOL]
            return f"{len(apps)} presenze, {len(rep)} giocatori valutati, ruoli con pochi dati: {small or 'nessuno'}"
        ok &= check("giocatori (Livello 3)", player_data)
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", default=None, help='es. "2025/2026"; default stagione corrente')
    ap.add_argument("--players", action="store_true", help="scarica anche i dati giocatori di lega")
    ap.add_argument("--league", action="append", help="limita a uno o più campionati (nome in config)")
    args = ap.parse_args()
    leagues = {k: v for k, v in config.FOTMOB_LEAGUES.items() if not args.league or k in args.league}
    results = {name: run_league(name, lid, args.season, args.players) for name, lid in leagues.items()}
    print("\n" + " · ".join(f"{k}: {'OK' if v else 'FAIL'}" for k, v in results.items()))
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
