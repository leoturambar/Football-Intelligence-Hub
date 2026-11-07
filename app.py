import hashlib

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

import analysis
import config
import data_loader as dl
import facts
import llm
import metrics
import report
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


def _narrative_block(key: tuple, fact_sheet: list[dict], kind: str, title: str) -> None:
    """
    Fact-grounded narrative: the facts are computed by code and always shown;
    the LLM only rewrites them, and every number it writes is checked.
    """
    digest = hashlib.md5(facts.as_prompt(fact_sheet).encode("utf-8")).hexdigest()[:10]
    full_key = (*key, digest)
    with st.expander(f"Fatti usati ({len(fact_sheet)}) — calcolati dal codice, sempre affidabili"):
        st.markdown(facts.as_markdown(fact_sheet))

    backend = st.session_state.backend
    model = st.session_state.get("ollama_model") if backend != "Claude API" else None
    who = "Claude API" if backend == "Claude API" else model
    c1, c2 = st.columns([1, 1])
    if c1.button("Genera testo", type="primary", key=f"gen_{kind}"):
        with st.spinner(f"Generazione con {who}…"):
            try:
                result = llm.narrate(kind, title, fact_sheet, backend, model)
                st.session_state[f"narr_{kind}"] = (full_key, result, who)
            except Exception as e:
                st.session_state[f"narr_{kind}"] = None
                st.error(f"Il modello non ha risposto: `{type(e).__name__}: {e}`", icon="🤖")

    saved = st.session_state.get(f"narr_{kind}")
    if not saved or saved[0] != full_key:
        st.caption("Il testo viene scritto dal modello solo a partire dai fatti qui sopra; "
                   "ogni numero viene poi confrontato con i fatti.")
        return
    _, result, used = saved
    show_refs = c2.toggle("Mostra riferimenti ai fatti", key=f"refs_{kind}")
    st.markdown(result["text"] if show_refs else facts.strip_citations(result["text"]))
    chk = result["check"]
    tries = "" if result["attempts"] == 1 else f", corretto al tentativo {result['attempts']}"
    if chk["ok"]:
        st.success(f"Verificato: ogni numero del testo compare nei fatti ({used}{tries}).", icon="✅")
    else:
        bits = []
        if chk["unknown_numbers"]:
            bits.append("numeri non presenti nei fatti: " + ", ".join(chk["unknown_numbers"]))
        if chk["bad_citations"]:
            bits.append("riferimenti inesistenti: " + ", ".join(chk["bad_citations"]))
        st.warning("Da controllare — " + "; ".join(bits) + f" ({used}). "
                   "Fai fede ai fatti qui sopra o rigenera.", icon="⚠️")


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
    st.radio("Backend LLM", options=config.LLM_BACKENDS, key="backend",
             help="Claude API è a pagamento: tenuto solo come riserva.")
    if st.session_state.backend != "Claude API":
        local_models = llm.ollama_models()
        if st.session_state.get("ollama_model") not in local_models:
            st.session_state.ollama_model = (config.OLLAMA_MODEL if config.OLLAMA_MODEL in local_models
                                             else local_models[0])
        st.selectbox("Modello locale", local_models, key="ollama_model")

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
    st.subheader("Analisi narrativa")
    findings_all = analysis.split_findings(team, sel, profiles) if not profiles.empty else []
    _narrative_block(
        key=("team", league_name, season, team, tuple(sel["match_id"])),
        fact_sheet=facts.team_facts(team, sel, summary, ctx, findings_all),
        kind="team", title=f"{team} — {league_name} {season} ({subset_note})",
    )

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
    st.subheader("Report pre-partita")
    _narrative_block(
        key=("opponent", league_name, season, team, opp),
        fact_sheet=facts.opponent_facts(team, opp, s, rec, types, forms, last5,
                                        zones_for, zones_against, ctx, vs_similar, len(opp_matches)),
        kind="opponent", title=f"{opp}, prossimo avversario di {team}",
    )

with tab_avversario:
    _render_avversario()

# ── Tab Giocatore ─────────────────────────────────────────────────────────────

@st.cache_data(show_spinner="Elaborazione statistiche giocatori…")
def _player_data(league_id: int, season: str | None, n_matches: int):
    """(appearances, season table) — n_matches only keys the cache."""
    apps = dl.load_league_player_appearances(league_id, season)
    return apps, analysis.player_season_table(apps)


def _league_player_data(key: str):
    """
    League-wide (apps, player table), downloading missing matches on request.
    Returns None while data is missing or on error (the UI explains why).
    """
    try:
        missing = dl.fotmob_missing_match_ids(league_id, season)
        n_done = len(dl.fotmob_finished_match_ids(league_id, season))
    except Exception as e:
        _show_load_error("il calendario", e)
        return None

    if missing:
        est = max(1, round(len(missing) * (config.FOTMOB_REQUEST_DELAY + 0.6) / 60))
        st.info(
            f"Per confrontare i giocatori con il resto del campionato servono i dati di "
            f"tutte le partite giocate. Mancano **{len(missing)} partite** "
            f"(circa {est} min la prima volta, poi restano in cache).",
            icon="⬇️",
        )
        if not st.button("Scarica dati del campionato", type="primary", key=f"dl_{key}"):
            return None
        bar = st.progress(0.0, text="Download partite…")
        try:
            dl.load_league_player_appearances(
                league_id, season,
                progress=lambda i, n: bar.progress(i / n, text=f"Download partite… {i}/{n}"),
            )
        except Exception as e:
            _show_load_error("le partite del campionato", e)
            return None
        bar.empty()

    apps, table = _player_data(league_id, season, n_done)
    if table.empty:
        st.info("Nessun dato giocatori disponibile.", icon="👤")
        return None
    return apps, table


def _render_giocatore() -> None:
    st.header(f"Analisi giocatori — {team}")

    data = _league_player_data("gioc")
    if data is None:
        return
    apps, table = data

    report = analysis.team_player_report(team, table)
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
        show, hide_index=True, use_container_width=True,
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
        _show_load_error("le partite della squadra", e)
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
            onoff.drop(columns=["player_id"]), hide_index=True, use_container_width=True,
            column_config={c: st.column_config.NumberColumn(format="%+.2f" if "xG" in c else "%.2f")
                           for c in onoff.columns if c not in ("Giocatore", "Da titolare", "Senza", "player_id")},
        )

    # ── Player detail ─────────────────────────────────────────────────────────
    st.divider()
    st.subheader("Dettaglio giocatore")
    name = st.selectbox("Giocatore", report["Giocatore"].tolist(), key=f"player_{team}_{season}")
    row = report[report["Giocatore"] == name].iloc[0]
    p = table[table["player_id"] == row["player_id"]].iloc[0]
    roles_for_player = ["Portiere"] if p["role"] == "Portiere" else [r for r in analysis.ROLES if r != "Portiere"]
    default_alt = row["Ruolo alternativo"] if isinstance(row["Ruolo alternativo"], str) else p["role"]
    c1, c2 = st.columns(2)
    with c1:
        fit, detail = analysis.role_fit(p, p["role"], table)
        st.markdown(f"**Nel suo ruolo: {p['role'].lower()}** — idoneità "
                    f"{'n/d' if pd.isna(fit) else f'{fit:.0f}/100'}")
        st.pyplot(viz.plot_role_percentiles(detail, title=p["role"]), use_container_width=True)
    with c2:
        alt = st.selectbox("Confronta con il ruolo", roles_for_player,
                           index=roles_for_player.index(default_alt) if default_alt in roles_for_player else 0,
                           key=f"altrole_{name}")
        fit2, detail2 = analysis.role_fit(p, alt, table)
        st.markdown(f"**Come {alt.lower()}** — idoneità {'n/d' if pd.isna(fit2) else f'{fit2:.0f}/100'}")
        st.pyplot(viz.plot_role_percentiles(detail2, title=alt), use_container_width=True)
    pool = analysis.role_pool(p["role"], table)
    st.caption(f"Confronto con {len(pool)} giocatori del campionato nello stesso ruolo, con almeno "
               f"{config.PLAYER_MIN_MINUTES} minuti · {int(p['minutes'])} minuti giocati da {name}.")


with tab_giocatore:
    _render_giocatore()

# ── Tab Confronti ─────────────────────────────────────────────────────────────

def _render_confronti() -> None:
    st.header("Confronti")
    mode = st.radio("Cosa confrontare", ["Giocatori dello stesso ruolo", "Squadre", "Campionati"],
                    horizontal=True)

    # ── Leagues ───────────────────────────────────────────────────────────────
    if mode == "Campionati":
        stats_by_league = {}
        with st.spinner("Caricamento statistiche dei 5 campionati (la prima volta ~10 s ciascuno)…"):
            for name, lid in config.FOTMOB_LEAGUES.items():
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
                     use_container_width=True)
        st.caption("Media dei valori delle squadre di ciascun campionato. In verde il campionato con il "
                   "valore più alto: ritmo, occasioni e pressing, non qualità.")

        st.subheader(f"{team}: dove si collocherebbero i suoi numeri negli altri campionati")
        eq = metrics.equivalent_positions(team, league_name, stats_by_league)
        if eq.empty:
            st.info("Statistiche della squadra non disponibili.", icon="📊")
        else:
            st.dataframe(eq, hide_index=True, use_container_width=True)
            st.caption(
                f"Per ogni metrica, la posizione che il valore di {team} avrebbe nella classifica di "
                "quel campionato. I numeri NON sono corretti per la forza del campionato: dicono dove "
                "starebbero le statistiche, non come renderebbe la squadra contro quegli avversari."
            )
        return

    # ── Teams ─────────────────────────────────────────────────────────────────
    if mode == "Squadre":
        others = [t for t in teams if t != team]
        other = st.selectbox("Confronta con", others, key=f"cmp_team_{team}_{season}")
        try:
            a = dl.load_team_match_table(league_id, season, team)
            b = dl.load_team_match_table(league_id, season, other)
        except Exception as e:
            _show_load_error("le partite delle squadre", e)
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
        st.dataframe(table, hide_index=True, use_container_width=True)

        league_stats, profiles = _league_profiles()
        if not profiles.empty:
            ta, tb = analysis.team_types(team, profiles), analysis.team_types(other, profiles)
            st.markdown("**Profilo di gioco (fasce del campionato)**")
            st.dataframe(pd.DataFrame({
                "Dimensione": [analysis.OPPONENT_DIMENSIONS[d]["label"] for d in ta],
                team: list(ta.values()),
                other: [tb.get(d, "—") for d in ta],
            }), hide_index=True, use_container_width=True)
        return

    # ── Players ───────────────────────────────────────────────────────────────
    data = _league_player_data("cmp")
    if data is None:
        return
    apps, table = data
    roles = [r for r in analysis.ROLES if len(analysis.role_pool(r, table)) >= config.ROLE_MIN_POOL]
    own = analysis.team_player_report(team, table)
    own_roles = [r for r in own.get("Ruolo", pd.Series(dtype=str)) if r in roles and r != "Portiere"]
    default_role = own_roles[0] if own_roles else roles[0]
    role = st.selectbox("Ruolo", roles, index=roles.index(default_role), key=f"cmp_role_{team}_{season}")

    board = analysis.role_leaderboard(role, table)
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
        key=f"cmp_players_{team}_{season}_{role}",
    )

    if picked:
        series = {}
        for lab in picked:
            pid = board.loc[board["_label"] == lab, "player_id"].iloc[0]
            p = table[table["player_id"] == pid].iloc[0]
            _, detail = analysis.role_fit(p, role, table)
            series[lab] = dict(zip(detail["Metrica"], detail["Percentile"]))
        c1, c2 = st.columns([1, 1])
        with c1:
            st.pyplot(viz.plot_percentile_radar(series, title=role), use_container_width=True)
        with c2:
            st.markdown("**Valori per 90 minuti / %**")
            metric_ids = [m for m in config.ROLE_PROFILES[role] if m in table.columns]
            vals = {}
            for lab in picked:
                pid = board.loc[board["_label"] == lab, "player_id"].iloc[0]
                p = table[table["player_id"] == pid].iloc[0]
                vals[lab.split(" (")[0]] = [p.get(m) for m in metric_ids]
            vt = pd.DataFrame(vals, index=[analysis.PLAYER_METRICS[m][0] for m in metric_ids])
            st.dataframe(vt.round(2), use_container_width=True)
        st.caption("Radar: percentile di ogni giocatore tra i pari ruolo del campionato "
                   f"(almeno {config.PLAYER_MIN_MINUTES} minuti). 50 = mediana.")

    st.divider()
    st.subheader(f"Classifica {role.lower()} — {league_name} {season}")
    teams_filter = st.multiselect("Filtra squadre", sorted(board["Squadra"].unique()),
                                  key=f"cmp_teams_{role}")
    view = board if not teams_filter else board[board["Squadra"].isin(teams_filter)]
    st.dataframe(
        view.drop(columns=["player_id", "_label"]), hide_index=True, use_container_width=True,
        column_config={"Idoneità": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f"),
                       "Voto medio FotMob": st.column_config.NumberColumn(format="%.2f")},
    )


with tab_confronti:
    _render_confronti()

# ── Tab Partita ───────────────────────────────────────────────────────────────

def _render_partita() -> None:
    st.header("Report partita")
    try:
        matches = dl.load_team_match_table(league_id, season, team)
    except Exception as e:
        _show_load_error("le partite della squadra", e)
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
    choice = st.selectbox("Partita", labels, key=f"match_{team}_{season}")
    mid = int(ms.loc[labels.index(choice), "match_id"])

    try:
        d = dl.match_report_data(mid)
    except Exception as e:
        _show_load_error("i dettagli della partita", e)
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

    st.pyplot(viz.plot_match_shots(shots, home, away), use_container_width=True)
    st.caption("Dimensione = xG del tiro · pieno = gol. Autogol esclusi.")
    st.pyplot(viz.plot_xg_race(shots, home, away), use_container_width=True)

    c1, c2 = st.columns([3, 2])
    with c1:
        st.markdown("**Statistiche**")
        st.dataframe(stats, hide_index=True, use_container_width=True, height=560)
    with c2:
        st.markdown("**Migliori in campo (voto FotMob)**")
        if not players.empty:
            top = players.dropna(subset=["rating"]).sort_values("rating", ascending=False).head(8)
            st.dataframe(
                top[["player", "team", "rating", "goals", "assists", "xg", "xa"]].rename(columns={
                    "player": "Giocatore", "team": "Squadra", "rating": "Voto", "goals": "Gol",
                    "assists": "Assist", "xg": "xG", "xa": "xA"}),
                hide_index=True, use_container_width=True,
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
    _narrative_block(
        key=("match", mid),
        fact_sheet=facts.match_facts(m, stats, shots, players),
        kind="match",
        title=f"{home} {m['home_goals']}-{m['away_goals']} {away}",
    )
    st.caption("I dati evento completi (passaggi, pressioni, reti di passaggi) sono disponibili solo per le "
               "competizioni storiche di StatsBomb Open Data, non per le stagioni in corso.")


with tab_partita:
    _render_partita()

# ── Tab Report ────────────────────────────────────────────────────────────────

def _render_report() -> None:
    st.header("Report esportabili")
    st.caption("Un file HTML unico (grafici inclusi) da aprire in qualsiasi browser; "
               "per il PDF, aprilo e usa Stampa → Salva come PDF.")
    kind = st.radio("Tipo di report", ["Squadra", "Avversario", "Partita"], horizontal=True, key="rep_kind")

    try:
        matches = dl.load_team_match_table(league_id, season, team)
    except Exception as e:
        _show_load_error("le partite della squadra", e)
        return
    if matches.empty:
        st.info("Nessuna partita giocata in questa stagione.", icon="📅")
        return

    args: dict = {}
    if kind == "Squadra":
        last_n = st.number_input("Ultime N partite (0 = tutta la stagione)", 0, len(matches), 0, key="rep_lastn")
        args = {"last_n": int(last_n)}
        rkey = ("team", league_name, season, team, int(last_n))
    elif kind == "Avversario":
        nxt = analysis.next_opponent(dl.fotmob_fixtures(league_id, season), team)
        others = [t for t in teams if t != team]
        default = others.index(nxt["opponent"]) if nxt and nxt["opponent"] in others else 0
        opp = st.selectbox("Avversario", others, index=default, key=f"rep_opp_{team}_{season}")
        args = {"opp": opp}
        rkey = ("opponent", league_name, season, team, opp)
    else:
        ms = matches.iloc[::-1].reset_index(drop=True)
        labels = [f"G{r['round']} · {r['date']:%d/%m} · {'vs' if r['venue'] == 'Casa' else '@'} "
                  f"{r['opponent']} {r['goals_for']}-{r['goals_against']}" for _, r in ms.iterrows()]
        choice = st.selectbox("Partita", labels, key=f"rep_match_{team}_{season}")
        args = {"match_id": int(ms.loc[labels.index(choice), "match_id"])}
        rkey = ("match", args["match_id"])

    backend = st.session_state.backend
    model = st.session_state.get("ollama_model") if backend != "Claude API" else None
    with_text = st.checkbox(
        f"Includi l'analisi scritta dal modello ({'Claude API' if backend == 'Claude API' else model})",
        value=backend != "Claude API", key="rep_text",
        help="Il testo è generato solo dai fatti del report e verificato; i fatti sono sempre in fondo.",
    )

    if st.button("Prepara report", type="primary", key="rep_go"):
        with st.spinner("Preparazione del report…"):
            try:
                if kind == "Squadra":
                    parts = report.team_parts(league_id, league_name, season, team, **args)
                elif kind == "Avversario":
                    parts = report.opponent_parts(league_id, league_name, season, team, args["opp"])
                else:
                    parts = report.match_parts(args["match_id"], league_name, season)
            except Exception as e:
                _show_load_error("i dati del report", e)
                return
            narrative = None
            if with_text:
                try:
                    narrative = llm.narrate(parts["kind"], parts["title"], parts["facts"], backend, model)
                except Exception as e:
                    st.warning(f"Testo del modello non disponibile ({type(e).__name__}): "
                               "il report contiene solo dati e fatti.", icon="🤖")
            html_doc = report.render_html(parts, narrative, model or "Claude API" if narrative else None)
            st.session_state.rep_out = (rkey, html_doc, report.filename(parts), narrative)

    saved = st.session_state.get("rep_out")
    if not saved or saved[0] != rkey:
        return
    _, html_doc, fname, narrative = saved
    c1, c2 = st.columns([1, 2])
    c1.download_button("Scarica report (HTML)", html_doc, file_name=fname, mime="text/html", type="primary")
    if narrative is not None:
        chk = narrative["check"]
        c2.markdown("✅ Testo verificato sui fatti" if chk["ok"] else
                    "⚠️ Testo con numeri da controllare: " + ", ".join(chk["unknown_numbers"] + chk["bad_citations"]))
    st.caption(f"Anteprima · {fname} · {len(html_doc) // 1024} KB")
    components.html(html_doc, height=900, scrolling=True)


with tab_report:
    _render_report()
