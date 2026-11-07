"""tab_partita.py — Tab Partita."""

import streamlit as st

import data_loader as dl
import facts
import viz

from ui_common import Ctx, show_load_error, narrative_block


def render(ctx: Ctx) -> None:
    league_id, season, team = ctx.league_id, ctx.season, ctx.team
    st.header("Report partita")
    try:
        matches = dl.load_team_match_table(league_id, season, team)
    except Exception as e:
        show_load_error("le partite della squadra", e)
        return
    if matches.empty:
        st.info("Nessuna partita giocata in questa stagione.", icon="📅")
        return

    ms = matches.iloc[::-1].reset_index(drop=True)
    labels = [
        f"G{r['round']} · {r['date']:%d/%m} · {'vs' if r['venue'] == 'Casa' else '@'} {r['opponent']} "
        f"{r['goals_for']}-{r['goals_against']}"
        for _, r in ms.iterrows()
    ]
    choice = st.selectbox("Partita", labels, key=f"match_{team}_{str(season).replace('/', '-')}")
    mid = int(ms.loc[labels.index(choice), "match_id"])

    try:
        d = dl.match_report_data(mid)
    except Exception as e:
        show_load_error("i dettagli della partita", e)
        return
    m, stats, shots, players = d["meta"], d["stats"], d["shots"], d["players"]
    home, away = m["home"], m["away"]

    st.subheader(f"{home} {m['home_goals']} – {m['away_goals']} {away}")
    xg_row = stats[stats["Metrica"] == "xG"]
    if not xg_row.empty:  # official match xG, same figure as the stats table
        xg_h, xg_a = float(xg_row[home].iloc[0]), float(xg_row[away].iloc[0])
    else:
        xg_h = shots.loc[shots["side"] == "home", "xg"].sum() if not shots.empty else 0
        xg_a = shots.loc[shots["side"] == "away", "xg"].sum() if not shots.empty else 0
    st.caption(
        f"Giornata {m['round']} · {m['date']} · xG {xg_h:.2f} – {xg_a:.2f} · "
        f"Moduli: {m['home_formation'] or 'n/d'} ({m['home_coach'] or '—'}) vs "
        f"{m['away_formation'] or 'n/d'} ({m['away_coach'] or '—'})"
    )

    st.pyplot(viz.plot_match_shots(shots, home, away), width="stretch")
    st.caption("Dimensione = xG del tiro · pieno = gol. Autogol esclusi.")
    st.pyplot(viz.plot_xg_race(shots, home, away), width="stretch")

    c1, c2 = st.columns([3, 2])
    with c1:
        st.markdown("**Statistiche**")
        st.dataframe(stats, hide_index=True, width="stretch", height=560)
    with c2:
        st.markdown("**Migliori in campo (voto FotMob)**")
        if not players.empty:
            top = players.dropna(subset=["rating"]).sort_values("rating", ascending=False).head(8)
            st.dataframe(
                top[["player", "team", "rating", "goals", "assists", "xg", "xa"]].rename(columns={
                    "player": "Giocatore", "team": "Squadra", "rating": "Voto", "goals": "Gol",
                    "assists": "Assist", "xg": "xG", "xa": "xA"}),
                hide_index=True, width="stretch",
                column_config={"Voto": st.column_config.NumberColumn(format="%.1f")},
            )
        big = shots[shots["xg"] >= 0.3].sort_values("minute") if not shots.empty else shots
        st.markdown("**Occasioni principali (xG ≥ 0,30)**")
        if big.empty:
            st.caption("Nessuna.")
        for _, s in big.iterrows():
            who = home if s["side"] == "home" else away
            st.markdown(f"- {int(s['minute'])}' {s['player']} ({who}) — xG {s['xg']:.2f}"
                        f"{' · **gol**' if s['is_goal'] else ''}")

    st.divider()
    st.subheader("Racconto della partita — LLM")
    narrative_block(
        key=("match", mid),
        fact_sheet=facts.match_facts(m, stats, shots, players),
        kind="match",
        title=f"{home} {m['home_goals']}-{m['away_goals']} {away}",
    )
    st.caption("I dati evento completi (passaggi, pressioni, reti di passaggi) sono disponibili solo per le "
               "competizioni storiche di StatsBomb Open Data, non per le stagioni in corso.")
