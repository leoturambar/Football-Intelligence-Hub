"""
UI smoke tests with Streamlit's AppTest: the real app script runs, offline,
on the saved FotMob fixtures. Every tab must render without exceptions.
"""

import pytest
from streamlit.testing.v1 import AppTest

import llm


@pytest.fixture(autouse=True)
def no_ollama(monkeypatch):
    # never touch a local LLM from tests
    monkeypatch.setattr(llm, "ollama_models", lambda: ["test-model"])

    def no_llm(*a, **k):
        raise AssertionError("tests must not call an LLM")

    monkeypatch.setattr(llm, "call_llm", no_llm)


def _run(team: str = "Inter") -> AppTest:
    at = AppTest.from_file("app.py", default_timeout=120)
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    at.selectbox(key="team").set_value(team).run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def _texts(at: AppTest) -> str:
    parts = [h.value for h in at.header] + [s.value for s in at.subheader]
    parts += [m.value for m in at.markdown] + [c.value for c in at.caption]
    parts += [i.value for i in at.info] + [w.value for w in at.warning]
    return "\n".join(str(p) for p in parts)


def test_all_tabs_render_for_a_team():
    at = _run("Inter")
    txt = _texts(at)
    for heading in ("Analisi squadra — Inter", "Report avversario —", "Analisi giocatori — Inter",
                    "Confronti", "Report partita", "Report esportabili"):
        assert heading in txt, heading
    # Squadra: real numbers, not placeholders
    labels = {m.label: m.value for m in at.metric}
    assert labels["Gol fatti / subiti"] == "5 / 4"
    # Avversario defaults to the next opponent in the fixture calendar
    assert "Report avversario — Como" in txt


def test_team_without_matches_shows_message():
    at = _run("Como")  # only an unplayed match in the fixtures
    assert "Nessuna partita giocata" in _texts(at)


def test_confronti_modes():
    at = _run("Inter")
    for value in ("Squadre", "Giocatori dello stesso ruolo"):
        mode = next(r for r in at.radio if r.label == "Cosa confrontare")  # fresh element each run
        mode.set_value(value).run()
        assert not at.exception, (value, [e.value for e in at.exception])


def test_report_without_llm_text():
    at = _run("Inter")
    at.checkbox(key="rep_text").uncheck().run()
    at.button(key="rep_go").click().run()
    assert not at.exception, [e.value for e in at.exception]
    _, html_doc, fname, narrative = at.session_state["rep_out"]
    assert html_doc.startswith("<!doctype html>") and fname.endswith(".html")
    assert narrative is None


def test_narrative_block_shows_facts_without_calling_llm():
    at = _run("Inter")
    assert any("Fatti usati" in e.label for e in at.expander)
