"""tab_squadra.py — Tab Squadra."""

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
    league_id, league_name, season, team = ctx.league_id, ctx.league_name, ctx.season, ctx.team
    st.header(f"Analisi squadra — {team}")

    try:
        matches = dl.load_team_match_table(league_id, season, team)
    except Exception as e:
        show_load_error("le partite della squadra", e)
        return

    if matches.empty:
        st.info("Nessuna partita giocata in questa stagione per la squadra selezionata.", icon="📅")
        return

    # ── Match selector ────────────────────────────────────────────────────────
    with st.expander("Selezione partite", expanded=False):
        c1, c2, c3 = st.columns(3)
        venues = c1.multiselect("Campo", ["Casa", "Trasferta"], default=["Casa", "Trasferta"])
        coaches = sorted(matches["coach"].dropna().unique())
        sel_coaches = c2.multiselect(
            "Allenatore", coaches, default=coaches,
            help="Dal dato di formazione FotMob: utile per il prima/dopo un cambio in panchina.",
        )
        last_n = c3.number_input(
            "Ultime N partite (0 = tutte)", min_value=0, max_value=len(matches), value=0, step=1,
        )
        rounds = pd.to_numeric(matches["round"], errors="coerce")
        if rounds.notna().any() and rounds.min() < rounds.max():
            r_lo, r_hi = st.slider(
                "Giornate", int(rounds.min()), int(rounds.max()),
                (int(rounds.min()), int(rounds.max())),
            )
        else:
            r_lo, r_hi = rounds.min(), rounds.max()
        excl_opp = st.multiselect("Escludi avversari", sorted(matches["opponent"].unique()))
        compare_mode = st.radio(
            "Confronto", ["Nessuno", "Casa vs Trasferta", "Prima metà vs seconda metà"],
            horizontal=True,
        )

    sel = matches[
        matches["venue"].isin(venues)
        & (matches["coach"].isin(sel_coaches) | matches["coach"].isna())
        & ~matches["opponent"].isin(excl_opp)
        & rounds.between(r_lo, r_hi)
    ]
    if last_n:
        sel = sel.tail(int(last_n))

    if sel.empty:
        st.warning("Nessuna partita corrisponde ai filtri selezionati.", icon="🔎")
        return

    summary = metrics.summarize(sel)
    record_str = metrics.record(sel)
    subset_note = (
        "tutte le partite" if len(sel) == len(matches)
        else f"{len(sel)} partite su {len(matches)}"
    )
    st.caption(f"{league_name} · {season} · {subset_note} · {record_str}")
    note = metrics.sample_note(len(sel))
    if note:
        st.warning(note, icon="📏")

    # ── Metric cards ──────────────────────────────────────────────────────────
    f = metrics.fmt
    r1 = st.columns(4)
    r1[0].metric("Punti per partita", f("ppg", summary["ppg"]), help=record_str)
    r1[1].metric("Gol fatti / subiti", f"{int(sel['goals_for'].sum())} / {int(sel['goals_against'].sum())}")
    r1[2].metric("xG / xG concessi (per partita)", f"{f('xg_pm', summary['xg_pm'])} / {f('xga_pm', summary['xga_pm'])}")
    r1[3].metric("Possesso medio", f"{f('possession', summary['possession'])}%")
    r2 = st.columns(4)
    r2[0].metric(
        "PPDA stimato", f("ppda_est", summary["ppda_est"]),
        help="Passaggi avversari nella loro metà ÷ (contrasti + intercetti + falli). "
             "Più basso = pressing più intenso. Stima: FotMob non fornisce la posizione "
             "delle azioni difensive, quindi va letto in termini relativi.",
    )
    r2[1].metric(
        "Passaggi nella metà avversaria", f"{f('territory', summary['territory'])}%",
        help="Quota dei passaggi della squadra giocati nella metà campo avversaria.",
    )
    r2[2].metric("xG per tiro", f("xg_per_shot", summary["xg_per_shot"]),
                 help="Qualità media delle occasioni create.")
    r2[3].metric("Porta inviolata", f("clean_sheets", summary["clean_sheets"]))

    st.divider()

    # ── Shot maps ─────────────────────────────────────────────────────────────
    shots = dl.load_team_shots(league_id, season, team)
    shots = shots[shots["match_id"].isin(sel["match_id"])] if not shots.empty else shots
    col_for, col_against = st.columns(2)
    with col_for:
        st.subheader("Tiri effettuati")
        fig = viz.plot_shot_map(
            shots[shots["side"] == "for"].reset_index(drop=True) if not shots.empty else shots,
            title=team, color=config.HOME_COLOR,
        )
        st.pyplot(fig, width="stretch")
    with col_against:
        st.subheader("Tiri concessi")
        fig = viz.plot_shot_map(
            shots[shots["side"] == "against"].reset_index(drop=True) if not shots.empty else shots,
            title="Avversari", color=config.AWAY_COLOR,
        )
        st.pyplot(fig, width="stretch")
    st.caption("Dimensione del cerchio = xG del tiro · pieno = gol · vuoto = non gol.")

    st.divider()

    # ── League context & strengths/weaknesses ────────────────────────────────
    st.subheader("Punti di forza e debolezza")
    league_stats, profiles = league_profiles(ctx)
    ctx = metrics.league_context(team, league_stats)

    if ctx.empty:
        st.info("Statistiche di lega non disponibili per questa stagione.", icon="📊")
    else:
        strengths, weaknesses = metrics.strengths_weaknesses(ctx)
        cs, cw = st.columns(2)
        with cs:
            st.markdown("**Punti di forza** (rispetto al campionato)")
            for _, r in strengths.iterrows():
                st.markdown(f"- {r['label']}: **{f(r['metric'], r['value'])}** — {r['rank']}° su {r['n']}")
            if strengths.empty:
                st.caption("Nessuna metrica sopra il 60° percentile.")
        with cw:
            st.markdown("**Aree da migliorare** (le meno forti in classifica)")
            for _, r in weaknesses.iterrows():
                st.markdown(f"- {r['label']}: **{f(r['metric'], r['value'])}** — {r['rank']}° su {r['n']}")
            if weaknesses.empty:
                st.caption("Nessuna area debole rispetto al campionato.")
        own_flags = []
        if summary["finishing"] < -2:
            own_flags.append(f"segna {abs(summary['finishing']):.1f} gol in meno di quanto valgono le occasioni (gol − xG)")
        if summary["gk_overperf"] < -2:
            own_flags.append(f"subisce {abs(summary['gk_overperf']):.1f} gol in più di quanto concede in xG")
        if own_flags:
            st.markdown("**Segnali dalle partite selezionate:** " + "; ".join(own_flags) + ".")

        table = ctx.assign(
            Valore=[f(m, v) for m, v in zip(ctx["metric"], ctx["value"])],
            **{"Media lega": [f(m, v) for m, v in zip(ctx["metric"], ctx["league_avg"])]},
            Posizione=[f"{r}° / {n}" for r, n in zip(ctx["rank"], ctx["n"])],
        )[["label", "Valore", "Media lega", "Posizione"]].rename(columns={"label": "Metrica"})
        st.caption("Classifica sull'intera stagione (fonte: statistiche di lega FotMob), non sul sottoinsieme di partite.")
        st.dataframe(table, hide_index=True, width="stretch")

    # ── Level 2: performance by opponent type ─────────────────────────────────
    if not profiles.empty:
        st.divider()
        st.subheader("Rendimento per tipo di avversario")
        dims = list(analysis.OPPONENT_DIMENSIONS)
        dim = st.radio(
            "Classifica gli avversari per", dims, horizontal=True,
            format_func=lambda d: analysis.OPPONENT_DIMENSIONS[d]["label"],
        )
        st.caption(
            analysis.OPPONENT_DIMENSIONS[dim]["help"]
            + " Fasce (terzili) calcolate sulla classifica attuale del campionato."
        )
        split = analysis.split_by_opponent_type(sel, profiles, dim)
        st.dataframe(split.drop(columns=["_ppg", "_xgd"]), hide_index=True, width="stretch")
        findings = analysis.split_findings(team, sel, profiles)
        if findings:
            st.markdown("**Differenze marcate (almeno 3 partite per fascia):**")
            for fnd in findings:
                st.markdown(f"- {fnd}")
        else:
            st.caption("Nessuna differenza marcata tra fasce con campioni sufficienti.")

    # ── Subset comparison ─────────────────────────────────────────────────────
    if compare_mode != "Nessuno":
        st.divider()
        st.subheader(f"Confronto — {compare_mode}")
        if compare_mode == "Casa vs Trasferta":
            a, b, la, lb = sel[sel["venue"] == "Casa"], sel[sel["venue"] == "Trasferta"], "Casa", "Trasferta"
        else:
            half = len(sel) // 2
            a, b, la, lb = sel.head(half), sel.iloc[half:], "Prima metà", "Seconda metà"
        if a.empty or b.empty:
            st.info("Uno dei due gruppi è vuoto con i filtri attuali.")
        else:
            st.caption(f"{la}: {len(a)} partite ({metrics.record(a)}) · {lb}: {len(b)} partite ({metrics.record(b)})")
            st.dataframe(metrics.compare(a, b, la, lb), hide_index=True, width="stretch")

    # ── Match list ────────────────────────────────────────────────────────────
    st.divider()
    st.subheader("Partite analizzate")
    show = sel[["date", "round", "venue", "opponent", "goals_for", "goals_against",
                "xg", "opp_xg", "possession", "formation", "opp_formation"]].rename(columns={
        "date": "Data", "round": "Giornata", "venue": "Campo", "opponent": "Avversario",
        "goals_for": "GF", "goals_against": "GS", "xg": "xG", "opp_xg": "xG avv.",
        "possession": "Possesso %", "formation": "Modulo", "opp_formation": "Modulo avv.",
    })
    st.dataframe(show, hide_index=True, width="stretch")

    # ── LLM narrative ─────────────────────────────────────────────────────────
    st.divider()
    st.subheader("Analisi narrativa")
    findings_all = analysis.split_findings(team, sel, profiles) if not profiles.empty else []
    narrative_block(
        key=("team", league_name, season, team, tuple(sel["match_id"])),
        fact_sheet=facts.team_facts(team, sel, summary, ctx, findings_all),
        kind="team", title=f"{team} — {league_name} {season} ({subset_note})",
    )
