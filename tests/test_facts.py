import facts
import metrics
from conftest import make_matches

SHEET = [
    {"id": "F1", "text": "xG prodotti 1,83 a partita, 12° su 20."},
    {"id": "F2", "text": "Possesso medio 62,4%; differenza +0,46."},
]


def test_validate_accepts_numbers_in_any_decimal_format():
    text = "Produce 1.83 xG [F1], è 12° su 20 [F1] con il 62,4% di possesso e +0.46 [F2]."
    assert facts.validate(text, SHEET)["ok"]


def test_validate_flags_invented_numbers():
    chk = facts.validate("Produce 1,85 xG e 7 tiri [F1].", SHEET)
    assert not chk["ok"]
    assert chk["unknown_numbers"] == ["1.85", "7"]


def test_validate_flags_unknown_citations():
    chk = facts.validate("Possesso 62,4% [F2, F9].", SHEET)
    assert chk["bad_citations"] == ["F9"] and not chk["ok"]


def test_harmless_numbers_and_citation_digits_are_ignored():
    # section numbers and the digits inside [F12] must not count as data
    assert facts.validate("1. Identità: 1,83 xG [F1]\n2. Altro [F2]", SHEET)["ok"]


def test_strip_citations():
    assert facts.strip_citations("Testo [F1] e altro [F1, F2].") == "Testo e altro."


def test_team_facts_numbers_come_from_metrics():
    df = make_matches([{"goals_for": 2, "xg": 2.25}, {"goals_against": 1, "xg": 0.75}])
    s = metrics.summarize(df)
    sheet = facts.team_facts("Squadra", df, s, ctx=None)
    text = facts.as_prompt(sheet)
    assert "1,50 xG" not in text  # sanity: formatted with Italian decimals elsewhere
    assert "xG prodotti 1,50 a partita" in text
    assert "record 1V 0N 1P" in text
    # the deterministic fallback always validates against itself
    assert facts.validate(facts.as_markdown(sheet), sheet)["ok"]
