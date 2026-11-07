"""tab_confronti.py — Tab Confronti."""

import pandas as pd
import streamlit as st

import analysis
import config
import data_loader as dl
import metrics
import viz

from ui_common import Ctx, show_load_error, league_profiles, league_player_data, reference_table


def render(ctx: Ctx) -> None:
    league_id, league_name, season, team, teams = ctx.league_id, ctx.league_name, ctx.season, ctx.team, ctx.teams
    st.header("Confronti")
    mode = st.radio("Cosa confrontare", ["Giocatori dello stesso ruolo", "Squadre", "Campionati"],
                    horizontal=True)

    # ── Leagues ───────────────────────────────────────────────────────────────
    if mode == "Campionati":
        if league_name in config.FOTMOB_CUPS:
            st.info("Il confronto riguarda i campionati nazionali: scegli un campionato nella barra "
                    "laterale per vedere dove si collocherebbero i numeri della squadra.", icon="🏆")
        stats_by_league = {}
        with st.spinner(f"Caricamento statistiche di {len(config.FOTMOB_DOMESTIC)} campionati "
                        "(la prima volta ~10 s ciascuno)…"):
            for name, lid in config.FOTMOB_DOMESTIC.items():
                try:
                    if season and season not in dl.fotmob_seasons(lid):
                        continue
                    stats_by_league[name] = dl.load_league_team_stats(lid, season)
                except Exception as e:
                    st.warning(f"{name}: statistiche non disponibili ({type(e).__name__}).", icon="⚠️")
        if not stats_by_league:
            st.info("Nessuna statistica di lega disponibile per questa stagione.", icon="📊")
            return
        st.subheader(f"Media per squadra — stagione {season}")
        avg = metrics.league_averages(stats_by_league)
        st.dataframe(avg.style.format("{:.2f}").highlight_max(axis=1, color="#2e5e3e"),
                     width="stretch")
        st.caption("Media dei valori delle squadre di ciascun campionato. In verde il campionato con il "
                   "valore più alto: ritmo, occasioni e pressing, non qualità.")

        if league_name in config.FOTMOB_CUPS:
            return
        st.subheader(f"{team}: dove si collocherebbero i suoi numeri negli altri campionati")
        eq = metrics.equivalent_positions(team, league_name, stats_by_league)
        if eq.empty:
            st.info("Statistiche della squadra non disponibili.", icon="📊")
        else:
            st.dataframe(eq, hide_index=True, width="stretch")
            st.caption(
                f"Per ogni metrica, la posizione che il valore di {team} avrebbe nella classifica di "
                "quel campionato. I numeri NON sono corretti per la forza del campionato: dicono dove "
                "starebbero le statistiche, non come renderebbe la squadra contro quegli avversari."
            )
        return

    # ── Teams ─────────────────────────────────────────────────────────────────
    if mode == "Squadre":
        others = [t for t in teams if t != team]
        other = st.selectbox("Confronta con", others, key=f"cmp_team_{team}_{str(season).replace('/', '-')}")
        try:
            a = dl.load_team_match_table(league_id, season, team)
            b = dl.load_team_match_table(league_id, season, other)
        except Exception as e:
            show_load_error("le partite delle squadre", e)
            return
        if a.empty or b.empty:
            st.info("Una delle due squadre non ha ancora partite giocate.", icon="📅")
            return
        st.caption(f"Stagione intera · {team}: {metrics.record(a)} · {other}: {metrics.record(b)}")
        table = metrics.compare(a, b, team, other)
        sa, sb = metrics.summarize(a), metrics.summarize(b)
        better = []
        for key, meta in metrics.METRICS.items():
            va, vb = sa.get(key), sb.get(key)
            if meta["better"] is None or va is None or vb is None or pd.isna(va) or pd.isna(vb) or va == vb:
                better.append("")
            else:
                a_wins = (va > vb) if meta["better"] == "high" else (va < vb)
                better.append(team if a_wins else other)
        table["Meglio"] = better
        st.dataframe(table, hide_index=True, width="stretch")

        league_stats, profiles = league_profiles(ctx)
        if not profiles.empty:
            ta, tb = analysis.team_types(team, profiles), analysis.team_types(other, profiles)
            st.markdown("**Profilo di gioco (fasce del campionato)**")
            st.dataframe(pd.DataFrame({
                "Dimensione": [analysis.OPPONENT_DIMENSIONS[d]["label"] for d in ta],
                team: list(ta.values()),
                other: [tb.get(d, "—") for d in ta],
            }), hide_index=True, width="stretch")
        return

    # ── Players ───────────────────────────────────────────────────────────────
    data = league_player_data(ctx.league_id, ctx.season, "cmp")
    if data is None:
        return
    apps, table = data
    ref, ref_note = reference_table(ctx, "cmp")
    if ref_note:
        st.caption(ref_note)
    roles = [r for r in analysis.ROLES
             if len(analysis.role_pool(r, table)) and len(analysis.role_pool(r, table, ref)) >= config.ROLE_MIN_POOL]
    if not roles:
        st.info(
            f"Nessun ruolo ha ancora almeno {config.ROLE_MIN_POOL} giocatori con "
            f"{config.PLAYER_MIN_MINUTES} minuti: troppo presto per confronti affidabili. "
            "Prova ad aggiungere la stagione precedente come riferimento.", icon="📏")
        return
    own = analysis.team_player_report(team, table, ref)
    own_roles = [r for r in own.get("Ruolo", pd.Series(dtype=str)) if r in roles and r != "Portiere"]
    default_role = own_roles[0] if own_roles else roles[0]
    role = st.selectbox("Ruolo", roles, index=roles.index(default_role), key=f"cmp_role_{team}_{str(season).replace('/', '-')}")

    board = analysis.role_leaderboard(role, table, ref)
    if board.empty:
        st.info("Troppi pochi giocatori in questo ruolo per un confronto.", icon="📏")
        return

    label = lambda r: f"{r['Giocatore']} ({r['Squadra']})"  # noqa: E731
    board["_label"] = board.apply(label, axis=1)
    mine = board[board["Squadra"] == team]["_label"].tolist()
    best_others = board[board["Squadra"] != team]["_label"].head(3 if mine else 4).tolist()
    picked = st.multiselect(
        "Giocatori (massimo 4)", board["_label"].tolist(),
        default=(mine[:1] + best_others)[:4], max_selections=4,
        key=f"cmp_players_{team}_{str(season).replace('/', '-')}_{role}",
    )

    if picked:
        series = {}
        for lab in picked:
            pid = board.loc[board["_label"] == lab, "player_id"].iloc[0]
            p = table[table["player_id"] == pid].iloc[0]
            _, detail = analysis.role_fit(p, role, table, ref)
            series[lab] = dict(zip(detail["Metrica"], detail["Percentile"]))
        c1, c2 = st.columns([1, 1])
        with c1:
            st.pyplot(viz.plot_percentile_radar(series, title=role), width="stretch")
        with c2:
            st.markdown("**Valori per 90 minuti / %**")
            metric_ids = [m for m in config.ROLE_PROFILES[role] if m in table.columns]
            vals = {}
            for lab in picked:
                pid = board.loc[board["_label"] == lab, "player_id"].iloc[0]
                p = table[table["player_id"] == pid].iloc[0]
                vals[lab.split(" (")[0]] = [p.get(m) for m in metric_ids]
            vt = pd.DataFrame(vals, index=[analysis.PLAYER_METRICS[m][0] for m in metric_ids])
            st.dataframe(vt.round(2), width="stretch")
        st.caption("Radar: percentile di ogni giocatore tra i pari ruolo del campionato "
                   f"(almeno {config.PLAYER_MIN_MINUTES} minuti). 50 = mediana.")

    st.divider()
    st.subheader(f"Classifica {role.lower()} — {league_name} {season}")
    teams_filter = st.multiselect("Filtra squadre", sorted(board["Squadra"].unique()),
                                  key=f"cmp_teams_{role}")
    view = board if not teams_filter else board[board["Squadra"].isin(teams_filter)]
    st.dataframe(
        view.drop(columns=["player_id", "_label"]), hide_index=True, width="stretch",
        column_config={"Idoneità": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f"),
                       "Voto medio FotMob": st.column_config.NumberColumn(format="%.2f")},
    )
