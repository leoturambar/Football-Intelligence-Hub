"""tab_giocatore.py — Tab Giocatore."""

import pandas as pd
import streamlit as st

import analysis
import config
import data_loader as dl
import viz

from ui_common import Ctx, show_load_error, league_player_data, reference_table


def render(ctx: Ctx) -> None:
    league_id, season, team = ctx.league_id, ctx.season, ctx.team
    st.header(f"Analisi giocatori — {team}")

    data = league_player_data(ctx.league_id, ctx.season, "gioc")
    if data is None:
        return
    apps, table = data

    ref, ref_note = reference_table(ctx, "gioc")
    if ref_note:
        st.caption(ref_note)
    report = analysis.team_player_report(team, table, ref)
    st.caption(
        f"Giocatori con almeno {config.PLAYER_MIN_MINUTES} minuti. Idoneità = percentile medio "
        f"pesato rispetto ai pari ruolo del campionato (0–100, 50 = nella media). "
        f"Ruoli dedotti da modulo e posizione in campo di FotMob."
    )
    if report.empty:
        st.info("Nessun giocatore ha ancora abbastanza minuti.", icon="⏱️")
        return

    # ── Squad table ───────────────────────────────────────────────────────────
    st.subheader("Rosa e idoneità al ruolo")
    show = report.drop(columns=["player_id"]).copy()
    show["Profilo più vicino ad altro ruolo"] = show["Profilo più vicino ad altro ruolo"].map({True: "sì", False: ""})
    show["Anello debole"] = show["Anello debole"].map({True: "⚠️", False: ""})
    st.dataframe(
        show, hide_index=True, width="stretch",
        column_config={
            "Idoneità al ruolo": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f"),
            "Idoneità alternativa": st.column_config.NumberColumn(format="%.0f"),
            "Voto medio FotMob": st.column_config.NumberColumn(format="%.2f"),
        },
    )

    weak = report[report["Anello debole"]]
    shift = report[report["Profilo più vicino ad altro ruolo"]]
    cw, cs = st.columns(2)
    with cw:
        st.markdown("**Anelli deboli** (idoneità sotto 30)")
        for _, r in weak.iterrows():
            st.markdown(f"- {r['Giocatore']} ({r['Ruolo'].lower()}): {r['Idoneità al ruolo']:.0f}/100")
        if weak.empty:
            st.caption("Nessun titolare sotto la soglia.")
    with cs:
        st.markdown("**Profilo statistico più vicino a un altro ruolo**")
        for _, r in shift.iterrows():
            st.markdown(
                f"- {r['Giocatore']}: {r['Ruolo'].lower()} {r['Idoneità al ruolo']:.0f} → "
                f"{r['Ruolo alternativo'].lower()} {r['Idoneità alternativa']:.0f}"
            )
        if shift.empty:
            st.caption("Nessuno: ognuno rende meglio nel proprio ruolo.")
        else:
            st.caption("Indica somiglianza di numeri, non un consiglio tattico: va letto con il contesto.")

    # ── Key players (on/off) ──────────────────────────────────────────────────
    st.divider()
    st.subheader("Giocatori chiave — la squadra con e senza")
    try:
        matches = dl.load_team_match_table(league_id, season, team)
    except Exception as e:
        show_load_error("le partite della squadra", e)
        return
    onoff = analysis.on_off_impact(matches, apps, team)
    if onoff.empty:
        st.info("Servono almeno 2 partite con e 2 senza il giocatore titolare.", icon="📏")
    else:
        st.caption(
            "Differenza xG per partita della squadra con il giocatore titolare e senza. "
            "È una correlazione, non una causa: cambiano anche avversari e altre assenze. "
            "Con meno di 3 partite da un lato il dato è aneddotico."
        )
        st.dataframe(
            onoff.drop(columns=["player_id"]), hide_index=True, width="stretch",
            column_config={c: st.column_config.NumberColumn(format="%+.2f" if "xG" in c else "%.2f")
                           for c in onoff.columns if c not in ("Giocatore", "Da titolare", "Senza", "player_id")},
        )

    # ── Player detail ─────────────────────────────────────────────────────────
    st.divider()
    st.subheader("Dettaglio giocatore")
    name = st.selectbox("Giocatore", report["Giocatore"].tolist(), key=f"player_{team}_{str(season).replace('/', '-')}")
    row = report[report["Giocatore"] == name].iloc[0]
    p = table[table["player_id"] == row["player_id"]].iloc[0]
    roles_for_player = ["Portiere"] if p["role"] == "Portiere" else [r for r in analysis.ROLES if r != "Portiere"]
    default_alt = row["Ruolo alternativo"] if isinstance(row["Ruolo alternativo"], str) else p["role"]
    c1, c2 = st.columns(2)
    with c1:
        fit, detail = analysis.role_fit(p, p["role"], table, ref)
        st.markdown(f"**Nel suo ruolo: {p['role'].lower()}** — idoneità "
                    f"{'n/d' if pd.isna(fit) else f'{fit:.0f}/100'}")
        st.pyplot(viz.plot_role_percentiles(detail, title=p["role"]), width="stretch")
    with c2:
        alt = st.selectbox("Confronta con il ruolo", roles_for_player,
                           index=roles_for_player.index(default_alt) if default_alt in roles_for_player else 0,
                           key=f"altrole_{name}")
        fit2, detail2 = analysis.role_fit(p, alt, table, ref)
        st.markdown(f"**Come {alt.lower()}** — idoneità {'n/d' if pd.isna(fit2) else f'{fit2:.0f}/100'}")
        st.pyplot(viz.plot_role_percentiles(detail2, title=alt), width="stretch")
    pool = analysis.role_pool(p["role"], table, ref)
    st.caption(f"Confronto con {len(pool)} giocatori del campionato nello stesso ruolo, con almeno "
               f"{config.PLAYER_MIN_MINUTES} minuti · {int(p['minutes'])} minuti giocati da {name}.")
