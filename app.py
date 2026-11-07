"""
app.py — Streamlit entry point: page config, sidebar selection, tab routing.
Each tab lives in its own tab_*.py module and receives a ui_common.Ctx.
"""

import streamlit as st

import config
import data_loader as dl
import llm
import tab_avversario
import tab_confronti
import tab_giocatore
import tab_partita
import tab_report
import tab_squadra
from ui_common import Ctx, show_load_error

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


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("Football Intelligence Hub")
    st.divider()

    st.selectbox("Competizione", options=list(config.FOTMOB_LEAGUES.keys()), key="league")
    league_id = config.FOTMOB_LEAGUES[st.session_state.league]

    try:
        seasons = dl.fotmob_seasons(league_id)
    except Exception as e:  # network / source down
        show_load_error("le stagioni", e)
        st.stop()
    st.selectbox("Stagione", options=seasons, key="season")

    try:
        teams = dl.fotmob_teams(league_id, st.session_state.season)
    except Exception as e:
        show_load_error("le squadre", e)
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

ctx = Ctx(
    league_name=st.session_state.league,
    league_id=league_id,
    season=st.session_state.season,
    team=st.session_state.team,
    teams=teams,
)

# ── Tabs ──────────────────────────────────────────────────────────────────────

tabs = st.tabs(["Squadra", "Avversario", "Giocatore", "Confronti", "Partita", "Report"])
modules = [tab_squadra, tab_avversario, tab_giocatore, tab_confronti, tab_partita, tab_report]
for tab, module in zip(tabs, modules):
    with tab:
        module.render(ctx)
