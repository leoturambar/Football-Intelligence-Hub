import streamlit as st

import config
import data_loader  # imported but not called yet

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Football Intelligence Hub",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Session state defaults ────────────────────────────────────────────────────

_defaults = {
    "league":       list(config.FBREF_LEAGUES.keys())[0],
    "season":       "2425",
    "team":         "",
    "backend":      config.DEFAULT_BACKEND,
    "match_filter": "Tutta la stagione",
}
for key, val in _defaults.items():
    if key not in st.session_state:
        st.session_state[key] = val

# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("Football Intelligence Hub")
    st.divider()

    st.session_state.league = st.selectbox(
        "Competizione",
        options=list(config.FBREF_LEAGUES.keys()),
        index=list(config.FBREF_LEAGUES.keys()).index(st.session_state.league),
    )

    st.session_state.season = st.text_input(
        "Stagione",
        value=st.session_state.season,
        help='Formato: "2425" per 2024-25, "2324" per 2023-24',
    )

    st.session_state.team = st.text_input(
        "Squadra",
        value=st.session_state.team,
        placeholder="es. Inter, Arsenal, Real Madrid…",
    )

    st.divider()

    st.session_state.backend = st.radio(
        "Backend LLM",
        options=config.LLM_BACKENDS,
        index=config.LLM_BACKENDS.index(st.session_state.backend),
    )

    st.divider()

    st.session_state.match_filter = st.radio(
        "Partite da analizzare",
        options=["Tutta la stagione", "Seleziona partite"],
        index=0 if st.session_state.match_filter == "Tutta la stagione" else 1,
    )

    if st.session_state.match_filter == "Seleziona partite":
        st.info(
            "Selezione partite disponibile dopo il caricamento dati. "
            "Inserisci squadra e premi Carica.",
            icon="ℹ️",
        )

    st.divider()
    st.caption(
        f"Lega FBref: `{config.FBREF_LEAGUES[st.session_state.league]}`"
    )

# ── Tabs ──────────────────────────────────────────────────────────────────────

tab_squadra, tab_giocatore, tab_confronti, tab_partita, tab_report = st.tabs(
    ["Squadra", "Giocatore", "Confronti", "Partita", "Report"]
)

# ── Tab Squadra ───────────────────────────────────────────────────────────────

with tab_squadra:
    team_label = st.session_state.team or "—"
    st.header(f"Analisi squadra — {team_label}")
    st.caption(
        f"{st.session_state.league} · {st.session_state.season} · "
        f"{st.session_state.match_filter.lower()}"
    )

    # Metric cards row
    col_poss, col_goals, col_cs = st.columns(3)
    with col_poss:
        st.metric(
            label="Possesso medio",
            value="—",
            help="% possesso palla medio per partita",
        )
    with col_goals:
        st.metric(
            label="Gol segnati / subiti",
            value="— / —",
            help="Totale gol stagionali (o subset selezionato)",
        )
    with col_cs:
        st.metric(
            label="Clean sheets",
            value="—",
            help="Partite senza subire gol",
        )

    st.divider()

    # Visualizations row
    col_heat, col_press = st.columns(2)
    with col_heat:
        st.subheader("Heatmap posizionale")
        st.info(
            "Heatmap delle zone d'azione della squadra (mplsoccer KDE). "
            "Disponibile dopo caricamento dati.",
            icon="🗺️",
        )
    with col_press:
        st.subheader("Mappa del pressing")
        st.info(
            "Pressing map: dove la squadra recupera palla (PPDA proxy). "
            "Disponibile dopo caricamento dati.",
            icon="🔴",
        )

    st.divider()

    # Strengths & Weaknesses summary
    st.subheader("Punti di forza e debolezza")
    st.info(
        "Riepilogo S&W basato su metriche aggregate: possesso, verticalità, "
        "intensità difensiva, minaccia offensiva, calci piazzati. "
        "Disponibile dopo caricamento dati.",
        icon="📊",
    )

    st.divider()

    # LLM narrative
    st.subheader("Analisi narrativa — LLM")
    llm_placeholder = st.empty()
    llm_placeholder.info(
        "L'analisi narrativa sarà generata qui in linguaggio da allenatore. "
        "Premi il pulsante per avviare.",
        icon="🤖",
    )
    if st.button("Genera analisi", type="primary", use_container_width=False):
        if not st.session_state.team:
            st.warning("Inserisci il nome della squadra nella barra laterale.")
        else:
            llm_placeholder.info(
                f"Generazione analisi con **{st.session_state.backend}** "
                f"per **{st.session_state.team}** — funzionalità in arrivo.",
                icon="⏳",
            )

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
