"""tab_report.py — Tab Report."""

import streamlit as st
import streamlit.components.v1 as components

import analysis
import data_loader as dl
import llm
import report

from ui_common import Ctx, show_load_error


def render(ctx: Ctx) -> None:
    league_id, league_name, season, team, teams = ctx.league_id, ctx.league_name, ctx.season, ctx.team, ctx.teams
    st.header("Report esportabili")
    st.caption("Un file HTML unico (grafici inclusi) da aprire in qualsiasi browser; "
               "per il PDF, aprilo e usa Stampa → Salva come PDF.")
    kind = st.radio("Tipo di report", ["Squadra", "Avversario", "Partita"], horizontal=True, key="rep_kind")

    try:
        matches = dl.load_team_match_table(league_id, season, team)
    except Exception as e:
        show_load_error("le partite della squadra", e)
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
        opp = st.selectbox("Avversario", others, index=default, key=f"rep_opp_{team}_{str(season).replace('/', '-')}")
        args = {"opp": opp}
        rkey = ("opponent", league_name, season, team, opp)
    else:
        ms = matches.iloc[::-1].reset_index(drop=True)
        labels = [f"G{r['round']} · {r['date']:%d/%m} · {'vs' if r['venue'] == 'Casa' else '@'} "
                  f"{r['opponent']} {r['goals_for']}-{r['goals_against']}" for _, r in ms.iterrows()]
        choice = st.selectbox("Partita", labels, key=f"rep_match_{team}_{str(season).replace('/', '-')}")
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
                show_load_error("i dati del report", e)
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
