"""
ui_common.py — shared Streamlit pieces used by every tab module.
"""

import hashlib
from dataclasses import dataclass

import pandas as pd
import streamlit as st

import analysis
import config
import data_loader as dl
import facts
import llm

@dataclass(frozen=True)
class Ctx:
    """Selection made in the sidebar, passed to every tab."""
    league_name: str
    league_id: int
    season: str | None
    team: str
    teams: list


def show_load_error(what: str, err: Exception) -> None:
    st.error(
        f"Impossibile caricare {what} da FotMob. Controlla la connessione e riprova.\n\n"
        f"Dettaglio tecnico: `{type(err).__name__}: {err}`",
        icon="⚠️",
    )


def narrative_block(key: tuple, fact_sheet: list[dict], kind: str, title: str) -> None:
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


def league_profiles(ctx: Ctx) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(league_stats, opponent profiles) — empty frames if unavailable."""
    try:
        lg = dl.load_league_team_stats(ctx.league_id, ctx.season)
    except Exception as e:
        show_load_error("le statistiche di lega", e)
        return pd.DataFrame(), pd.DataFrame()
    return lg, analysis.opponent_profiles(lg)


@st.cache_data(show_spinner="Elaborazione statistiche giocatori…")
def player_data(league_id: int, season: str | None, n_matches: int):
    """(appearances, season table) — n_matches only keys the cache."""
    apps = dl.load_league_player_appearances(league_id, season)
    return apps, analysis.player_season_table(apps)


def league_player_data(league_id: int, season: str | None, key: str, what: str = "del campionato"):
    """
    League-wide (apps, player table), downloading missing matches on request.
    Returns None while data is missing or on error (the UI explains why).
    """
    try:
        missing = dl.fotmob_missing_match_ids(league_id, season)
        n_done = len(dl.fotmob_finished_match_ids(league_id, season))
    except Exception as e:
        show_load_error("il calendario", e)
        return None

    if missing:
        est = max(1, round(len(missing) * (config.FOTMOB_REQUEST_DELAY + 0.6) / 60))
        st.info(
            f"Per confrontare i giocatori servono i dati di tutte le partite giocate "
            f"{what}. Mancano **{len(missing)} partite** "
            f"(circa {est} min la prima volta, poi restano in cache).",
            icon="⬇️",
        )
        if not st.button(f"Scarica dati {what}", type="primary", key=f"dl_{key}"):
            return None
        bar = st.progress(0.0, text="Download partite…")
        try:
            dl.load_league_player_appearances(
                league_id, season,
                progress=lambda i, n: bar.progress(i / n, text=f"Download partite… {i}/{n}"),
            )
        except Exception as e:
            show_load_error("le partite del campionato", e)
            return None
        bar.empty()

    apps, table = player_data(league_id, season, n_done)
    if table.empty:
        st.info("Nessun dato giocatori disponibile.", icon="👤")
        return None
    return apps, table


def reference_table(ctx: Ctx, key: str):
    """
    Optional previous-season player table used as an extra benchmark for role
    fit (more players per role, steadier percentiles early in the season).
    Returns (table or None, caption text).
    """
    try:
        seasons = dl.fotmob_seasons(ctx.league_id)
    except Exception:
        return None, ""
    current = ctx.season or (seasons[0] if seasons else None)
    if current not in seasons or seasons.index(current) + 1 >= len(seasons):
        return None, ""
    prev = seasons[seasons.index(current) + 1]
    use = st.checkbox(
        f"Confronta anche con la stagione {prev}",
        key=f"ref_{key}_{ctx.league_id}_{str(current).replace('/', '-')}",
        help="Aggiunge i giocatori dello stesso ruolo della stagione precedente al gruppo di "
             "confronto: percentili più stabili a inizio stagione e ruoli rari valutabili.",
    )
    if not use:
        return None, ""
    data = league_player_data(ctx.league_id, prev, f"{key}_ref", what=f"della stagione {prev}")
    if data is None:
        return None, ""
    return data[1], f"Confronto con i pari ruolo di {current} e {prev}."
