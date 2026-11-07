import pandas as pd
import streamlit as st

import analysis
import config
import data_loader as dl
import llm
import metrics
import viz

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Football Intelligence Hub",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Session state defaults ────────────────────────────────────────────────────

_defaults = {
    "league":  list(config.FOTMOB_LEAGUES.keys())[0],
    "backend": config.DEFAULT_BACKEND,
}
for key, val in _defaults.items():
    if key not in st.session_state:
        st.session_state[key] = val


def _show_load_error(what: str, err: Exception) -> None:
    st.error(
        f"Impossibile caricare {what} da FotMob. Controlla la connessione e riprova.\n\n"
        f"Dettaglio tecnico: `{type(err).__name__}: {err}`",
        icon="⚠️",
    )


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("Football Intelligence Hub")
    st.divider()

    st.selectbox("Competizione", options=list(config.FOTMOB_LEAGUES.keys()), key="league")
    league_id = config.FOTMOB_LEAGUES[st.session_state.league]

    try:
        seasons = dl.fotmob_seasons(league_id)
    except Exception as e:  # network / source down
        _show_load_error("le stagioni", e)
        st.stop()
    st.selectbox("Stagione", options=seasons, key="season")

    try:
        teams = dl.fotmob_teams(league_id, st.session_state.season)
    except Exception as e:
        _show_load_error("le squadre", e)
        st.stop()
    if st.session_state.get("team") not in teams:
        st.session_state.team = teams[0]
    st.selectbox("Squadra", options=teams, key="team")

    st.divider()
    st.radio("Backend LLM", options=config.LLM_BACKENDS, key="backend")

    st.divider()
    st.caption("Fonte dati: FotMob (stagioni in corso) · cache locale in `data/fotmob/`")

league_name = st.session_state.league
season = st.session_state.season
team = st.session_state.team

# ── Tabs ──────────────────────────────────────────────────────────────────────

tab_squadra, tab_avversario, tab_giocatore, tab_confronti, tab_partita, tab_report = st.tabs(
    ["Squadra", "Avversario", "Giocatore", "Confronti", "Partita", "Report"]
)


def _league_profiles() -> tuple[pd.DataFrame, pd.DataFrame]:
    """(league_stats, opponent profiles) — empty frames if unavailable."""
    try:
        lg = dl.load_league_team_stats(league_id, season)
    except Exception as e:
        _show_load_error("le statistiche di lega", e)
        return pd.DataFrame(), pd.DataFrame()
    return lg, analysis.opponent_profiles(lg)

# ── Tab Squadra ───────────────────────────────────────────────────────────────

def _render_squadra() -> None:
    st.header(f"Analisi squadra — {team}")

    try:
        matches = dl.load_team_match_table(league_id, season, team)
    except Exception as e:
        _show_load_error("le partite della squadra", e)
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
        st.pyplot(fig, use_container_width=True)
    with col_against:
        st.subheader("Tiri concessi")
        fig = viz.plot_shot_map(
            shots[shots["side"] == "against"].reset_index(drop=True) if not shots.empty else shots,
            title="Avversari", color=config.AWAY_COLOR,
        )
        st.pyplot(fig, use_container_width=True)
    st.caption("Dimensione del cerchio = xG del tiro · pieno = gol · vuoto = non gol.")

    st.divider()

    # ── League context & strengths/weaknesses ────────────────────────────────
    st.subheader("Punti di forza e debolezza")
    league_stats, profiles = _league_profiles()
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
        st.dataframe(table, hide_index=True, use_container_width=True)

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
        st.dataframe(split.drop(columns=["_ppg", "_xgd"]), hide_index=True, use_container_width=True)
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
            st.dataframe(metrics.compare(a, b, la, lb), hide_index=True, use_container_width=True)

    # ── Match list ────────────────────────────────────────────────────────────
    st.divider()
    st.subheader("Partite analizzate")
    show = sel[["date", "round", "venue", "opponent", "goals_for", "goals_against",
                "xg", "opp_xg", "possession", "formation", "opp_formation"]].rename(columns={
        "date": "Data", "round": "Giornata", "venue": "Campo", "opponent": "Avversario",
        "goals_for": "GF", "goals_against": "GS", "xg": "xG", "opp_xg": "xG avv.",
        "possession": "Possesso %", "formation": "Modulo", "opp_formation": "Modulo avv.",
    })
    st.dataframe(show, hide_index=True, use_container_width=True)

    # ── LLM narrative ─────────────────────────────────────────────────────────
    st.divider()
    st.subheader("Analisi narrativa — LLM")
    narr_key = (league_name, season, team, tuple(sel["match_id"]))
    if st.button("Genera analisi", type="primary"):
        payload = metrics.llm_payload(summary, ctx, record_str)
        if not profiles.empty:
            payload["Differenze per tipo di avversario"] = (
                analysis.split_findings(team, sel, profiles) or "nessuna differenza marcata"
            )
        system, user = llm.build_squad_narrative(
            team, payload, league_name, season,
            match_context=f"{subset_note}, {record_str}",
        )
        with st.spinner(f"Generazione con {st.session_state.backend}…"):
            try:
                st.session_state.narrative = (narr_key, llm.call_llm(user, st.session_state.backend, system))
            except Exception as e:
                st.session_state.narrative = None
                st.error(f"Il backend LLM non ha risposto: `{type(e).__name__}: {e}`", icon="🤖")
    saved = st.session_state.get("narrative")
    if saved and saved[0] == narr_key:
        st.markdown(saved[1])


with tab_squadra:
    _render_squadra()


# ── Tab Avversario ────────────────────────────────────────────────────────────

def _render_avversario() -> None:
    fixtures = dl.fotmob_fixtures(league_id, season)
    nxt = analysis.next_opponent(fixtures, team)
    others = [t for t in teams if t != team]
    default = others.index(nxt["opponent"]) if nxt and nxt["opponent"] in others else 0
    opp = st.selectbox("Avversario da analizzare", others, index=default, key=f"opp_{team}_{season}")

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
        _show_load_error(f"le partite di {opp}", e)
        return
    if opp_matches.empty:
        st.info(f"{opp} non ha ancora giocato partite in questa stagione.", icon="📅")
        return

    league_stats, profiles = _league_profiles()
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
        st.pyplot(fig, use_container_width=True)
        if zones_for:
            st.dataframe(pd.DataFrame({"Zona / tipo": list(zones_for), "% degli xG": [f"{v:.0f}%" for v in zones_for.values()]}),
                         hide_index=True, use_container_width=True)
    with col_b:
        st.subheader("Dove concede")
        fig = viz.plot_shot_map(
            opp_shots[opp_shots["side"] == "against"].reset_index(drop=True) if not opp_shots.empty else opp_shots,
            title=f"Contro {opp}", color=config.HOME_COLOR,
        )
        st.pyplot(fig, use_container_width=True)
        if zones_against:
            st.dataframe(pd.DataFrame({"Zona / tipo": list(zones_against), "% degli xG": [f"{v:.0f}%" for v in zones_against.values()]}),
                         hide_index=True, use_container_width=True)

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
        st.dataframe(vs_similar, hide_index=True, use_container_width=True)

    # Recent matches
    st.divider()
    st.subheader("Partite giocate")
    show = opp_matches[["date", "round", "venue", "opponent", "goals_for", "goals_against",
                        "xg", "opp_xg", "possession", "formation"]].rename(columns={
        "date": "Data", "round": "Giornata", "venue": "Campo", "opponent": "Avversario",
        "goals_for": "GF", "goals_against": "GS", "xg": "xG", "opp_xg": "xG avv.",
        "possession": "Possesso %", "formation": "Modulo",
    })
    st.dataframe(show.iloc[::-1], hide_index=True, use_container_width=True)

    # LLM brief
    st.divider()
    st.subheader("Report pre-partita — LLM")
    brief_key = (league_name, season, team, opp, len(opp_matches))
    if st.button("Genera report", type="primary", key="btn_opp_brief"):
        payload = metrics.llm_payload(s, ctx, rec)
        payload["Profilo avversario"] = {analysis.OPPONENT_DIMENSIONS[d]["label"]: t for d, t in types.items()}
        payload["Moduli usati"] = ", ".join(f"{k} ({v})" for k, v in forms.items()) or "n/d"
        payload["Ultime 5 (V/N/P)"] = last5
        if zones_for:
            payload["Da dove crea (% xG)"] = {k: f"{v:.0f}%" for k, v in zones_for.items()}
        if zones_against:
            payload["Da dove concede (% xG)"] = {k: f"{v:.0f}%" for k, v in zones_against.items()}
        if not vs_similar.empty:
            payload[f"Contro squadre simili a {team}"] = {
                r["Profilo simile al nostro"]: f"{r['Partite']} partite, {r['Record']}, diff. xG {r['Diff. xG/partita']} "
                                               f"(vs altri {r['Diff. xG vs altri']})"
                for _, r in vs_similar.iterrows()
            }
        system, user = llm.build_opponent_brief(team, opp, payload, league_name, season)
        with st.spinner(f"Generazione con {st.session_state.backend}…"):
            try:
                st.session_state.opp_brief = (brief_key, llm.call_llm(user, st.session_state.backend, system))
            except Exception as e:
                st.session_state.opp_brief = None
                st.error(f"Il backend LLM non ha risposto: `{type(e).__name__}: {e}`", icon="🤖")
    saved = st.session_state.get("opp_brief")
    if saved and saved[0] == brief_key:
        st.markdown(saved[1])


with tab_avversario:
    _render_avversario()

# ── Tab Giocatore ─────────────────────────────────────────────────────────────

with tab_giocatore:
    st.header("Analisi giocatore")
    st.info(
        "Coming soon — role fit scoring, position mismatch detection, weak link analysis.",
        icon="👤",
    )

# ── Tab Confronti ─────────────────────────────────────────────────────────────

with tab_confronti:
    st.header("Confronti")
    st.info(
        "Coming soon — cross-team role comparisons, overlaid radar charts.",
        icon="📡",
    )

# ── Tab Partita ───────────────────────────────────────────────────────────────

with tab_partita:
    st.header("Report partita")
    st.info(
        "Coming soon — event-level match report via StatsBomb (where available).",
        icon="🎬",
    )

# ── Tab Report ────────────────────────────────────────────────────────────────

with tab_report:
    st.header("Report esportabili")
    st.info(
        "Coming soon — Italia post-mortem, scouting report, match report, "
        "formation comparison.",
        icon="📄",
    )
