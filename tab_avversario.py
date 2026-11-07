"""tab_avversario.py — Tab Avversario."""

import pandas as pd
import streamlit as st

import analysis
import config
import data_loader as dl
import facts
import metrics
import viz

from ui_common import Ctx, show_load_error, narrative_block, league_profiles


def render(ctx: Ctx) -> None:
    league_id, league_name, season, team, teams = ctx.league_id, ctx.league_name, ctx.season, ctx.team, ctx.teams
    fixtures = dl.fotmob_fixtures(league_id, season)
    nxt = analysis.next_opponent(fixtures, team)
    others = [t for t in teams if t != team]
    default = others.index(nxt["opponent"]) if nxt and nxt["opponent"] in others else 0
    opp = st.selectbox("Avversario da analizzare", others, index=default, key=f"opp_{team}_{str(season).replace('/', '-')}")

    st.header(f"Report avversario — {opp}")
    if nxt and nxt["opponent"] == opp:
        st.caption(
            f"Prossima partita: giornata {nxt['round']} · {nxt['date']:%d/%m/%Y} · "
            f"{team} gioca in {'casa' if nxt['venue'] == 'Casa' else 'trasferta'}"
        )

    try:
        opp_matches = dl.load_team_match_table(league_id, season, opp)
        opp_shots = dl.load_team_shots(league_id, season, opp)
    except Exception as e:
        show_load_error(f"le partite di {opp}", e)
        return
    if opp_matches.empty:
        st.info(f"{opp} non ha ancora giocato partite in questa stagione.", icon="📅")
        return

    league_stats, profiles = league_profiles(ctx)
    s = metrics.summarize(opp_matches)
    rec = metrics.record(opp_matches)
    note = metrics.sample_note(len(opp_matches))
    if note:
        st.warning(note, icon="📏")

    # Identity
    f = metrics.fmt
    types = analysis.team_types(opp, profiles)
    if types:
        st.markdown(" · ".join(
            f"**{analysis.OPPONENT_DIMENSIONS[d]['label']}**: {t.lower()}" for d, t in types.items()
        ))
    forms = opp_matches["formation"].dropna().value_counts()
    last5 = " ".join(opp_matches.tail(5)["result"])
    c = st.columns(4)
    c[0].metric("Punti per partita", f("ppg", s["ppg"]), help=rec)
    c[1].metric("xG / xG concessi (per partita)", f"{f('xg_pm', s['xg_pm'])} / {f('xga_pm', s['xga_pm'])}")
    c[2].metric("Modulo più usato", forms.index[0] if len(forms) else "—",
                help=", ".join(f"{k} ({v})" for k, v in forms.items()))
    c[3].metric("Ultime 5", last5 or "—")
    c = st.columns(4)
    c[0].metric("Possesso medio", f"{f('possession', s['possession'])}%")
    c[1].metric("PPDA stimato", f("ppda_est", s["ppda_est"]))
    c[2].metric("Quota xG concessi da palla inattiva", f"{f('set_piece_xga_share', s['set_piece_xga_share'])}%")
    c[3].metric("xG per tiro concesso", f("xga_per_shot", s["xga_per_shot"]))

    st.divider()

    # Where they create / concede
    zones_for = analysis.shot_zones(opp_shots[opp_shots["side"] == "for"]) if not opp_shots.empty else {}
    zones_against = analysis.shot_zones(opp_shots[opp_shots["side"] == "against"]) if not opp_shots.empty else {}
    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("Dove crea")
        fig = viz.plot_shot_map(
            opp_shots[opp_shots["side"] == "for"].reset_index(drop=True) if not opp_shots.empty else opp_shots,
            title=opp, color=config.AWAY_COLOR,
        )
        st.pyplot(fig, width="stretch")
        if zones_for:
            st.dataframe(pd.DataFrame({"Zona / tipo": list(zones_for), "% degli xG": [f"{v:.0f}%" for v in zones_for.values()]}),
                         hide_index=True, width="stretch")
    with col_b:
        st.subheader("Dove concede")
        fig = viz.plot_shot_map(
            opp_shots[opp_shots["side"] == "against"].reset_index(drop=True) if not opp_shots.empty else opp_shots,
            title=f"Contro {opp}", color=config.HOME_COLOR,
        )
        st.pyplot(fig, width="stretch")
        if zones_against:
            st.dataframe(pd.DataFrame({"Zona / tipo": list(zones_against), "% degli xG": [f"{v:.0f}%" for v in zones_against.values()]}),
                         hide_index=True, width="stretch")

    # League position
    ctx = metrics.league_context(opp, league_stats)
    if not ctx.empty:
        st.divider()
        strengths, weaknesses = metrics.strengths_weaknesses(ctx)
        cs, cw = st.columns(2)
        with cs:
            st.markdown(f"**Punti di forza di {opp}**")
            for _, r in strengths.iterrows():
                st.markdown(f"- {r['label']}: **{f(r['metric'], r['value'])}** — {r['rank']}° su {r['n']}")
            if strengths.empty:
                st.caption("Nessuna metrica sopra il 60° percentile.")
        with cw:
            st.markdown(f"**Punti deboli di {opp}**")
            for _, r in weaknesses.iterrows():
                st.markdown(f"- {r['label']}: **{f(r['metric'], r['value'])}** — {r['rank']}° su {r['n']}")
            if weaknesses.empty:
                st.caption("Nessuna area debole rispetto al campionato.")

    # Versus teams like us
    my_types = analysis.team_types(team, profiles)
    vs_similar = analysis.opponent_vs_similar(opp_matches, profiles, my_types)
    if not vs_similar.empty:
        st.divider()
        st.subheader(f"{opp} contro squadre con un profilo simile a {team}")
        st.caption(f"Profilo di {team}: " + " · ".join(
            f"{analysis.OPPONENT_DIMENSIONS[d]['label']} {t.lower()}" for d, t in my_types.items()))
        st.dataframe(vs_similar, hide_index=True, width="stretch")

    # Recent matches
    st.divider()
    st.subheader("Partite giocate")
    show = opp_matches[["date", "round", "venue", "opponent", "goals_for", "goals_against",
                        "xg", "opp_xg", "possession", "formation"]].rename(columns={
        "date": "Data", "round": "Giornata", "venue": "Campo", "opponent": "Avversario",
        "goals_for": "GF", "goals_against": "GS", "xg": "xG", "opp_xg": "xG avv.",
        "possession": "Possesso %", "formation": "Modulo",
    })
    st.dataframe(show.iloc[::-1], hide_index=True, width="stretch")

    # LLM brief
    st.divider()
    st.subheader("Report pre-partita")
    narrative_block(
        key=("opponent", league_name, season, team, opp),
        fact_sheet=facts.opponent_facts(team, opp, s, rec, types, forms, last5,
                                        zones_for, zones_against, ctx, vs_similar, len(opp_matches)),
        kind="opponent", title=f"{opp}, prossimo avversario di {team}",
    )
