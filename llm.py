import os
import re
import json
import requests
import anthropic
from config import (
    CLAUDE_MODEL, OLLAMA_MODEL, OLLAMA_URL, OLLAMA_BASE_URL,
    LLM_MAX_TOKENS, LLM_TEMPERATURE,
    CLAUDE_MAX_TOKENS, CLAUDE_EFFORT,
)

# ── System prompts ────────────────────────────────────────────────────────────

PROMPTS = {
    "system_analyst": (
        "You are an elite football tactical analyst. "
        "You write sharp, concrete coaching insights — no filler, no generic praise. "
        "Every claim must reference a specific metric or pattern from the data provided. "
        "Tone: direct, professional, like a head coach's briefing to staff. "
        "Language: respond in the same language as the user's input data labels "
        "(Italian if labels are Italian, English otherwise)."
    ),
    "system_scout": (
        "You are a football scout writing a player report. "
        "Be specific: name strengths with numbers, flag weaknesses with context. "
        "Compare to role benchmark. Max 3 bullet points per section. "
        "Never speculate beyond the data given."
    ),
}

# ── Private helpers ───────────────────────────────────────────────────────────

def _fmt_stats(d: dict, _indent: int = 0) -> str:
    """Recursively format a stats dict as indented key: value lines."""
    lines = []
    pad = "  " * _indent
    for k, v in d.items():
        if isinstance(v, dict):
            lines.append(f"{pad}{k}:")
            lines.append(_fmt_stats(v, _indent + 1))
        else:
            lines.append(f"{pad}{k}: {v}")
    return "\n".join(lines)


# ── Prompt builders (pure — no API calls) ────────────────────────────────────

def build_squad_narrative(
    team: str,
    stats_dict: dict,
    league: str,
    season: str,
    match_context: str = "",
) -> tuple[str, str]:
    """
    Full tactical briefing for a team.

    Returns (system, user) prompt tuple.
    Output covers: identity/style, 2 strengths, 2 weaknesses, 1 recommendation.
    Max 250 words.
    """
    context_line = f"Context: {match_context}" if match_context else "Context: full season"
    user = (
        f"Team: {team}\n"
        f"Competition: {league} {season}\n"
        f"{context_line}\n\n"
        f"DATA:\n{_fmt_stats(stats_dict)}\n\n"
        "Write a tactical briefing (max 250 words) with these four sections:\n"
        "1. Identity & playing style — what does this team actually do?\n"
        "2. Two key strengths — each with a specific metric from the data.\n"
        "3. Two main weaknesses — each with a specific metric from the data.\n"
        "4. One concrete tactical recommendation for the coaching staff.\n\n"
        "No filler. No observations that could apply to any team.\n"
        "Only compare to the league where the DATA gives a league rank or average.\n"
        "Write the whole briefing in Italian."
    )
    return PROMPTS["system_analyst"], user


def build_opponent_brief(
    team: str,
    opponent: str,
    stats_dict: dict,
    league: str,
    season: str,
) -> tuple[str, str]:
    """
    Pre-match opponent report for *team*'s staff.

    Returns (system, user) prompt tuple. Max 300 words, Italian.
    """
    user = (
        f"Our team: {team}\n"
        f"Next opponent: {opponent}\n"
        f"Competition: {league} {season}\n\n"
        f"DATA:\n{_fmt_stats(stats_dict)}\n\n"
        "Write a pre-match opponent report (max 300 words) for our coaching staff:\n"
        "1. How the opponent plays — style, shape, where their chances come from.\n"
        "2. Where they are vulnerable — with specific metrics from the data.\n"
        "3. How they have done against teams with a profile like ours.\n"
        "4. Two concrete game-plan recommendations for us.\n\n"
        "Every claim must cite a number from the DATA. Flag small samples "
        "(fewer than 5 matches) explicitly. Only compare to the league where the "
        "DATA gives a league rank or average. Write the whole report in Italian."
    )
    return PROMPTS["system_analyst"], user


def build_sw_bullets(
    team: str,
    stats_dict: dict,
) -> tuple[str, str]:
    """
    Structured strengths & weaknesses as JSON.

    Returns (system, user) prompt tuple.
    Expected LLM output: {"strengths": [...], "weaknesses": [...]}
    Each item is one sentence with an embedded metric.
    """
    user = (
        f"Team: {team}\n\n"
        f"DATA:\n{_fmt_stats(stats_dict)}\n\n"
        "Return ONLY a JSON object with this exact structure — no other text:\n"
        '{"strengths": ["...", "...", "..."], "weaknesses": ["...", "...", "..."]}\n\n'
        "Rules:\n"
        "- Exactly 3 strengths and 3 weaknesses.\n"
        "- Each item is one sentence with a specific metric embedded.\n"
        "- No phrases like 'the team shows' or 'it is evident that'.\n"
        "- Start directly with the stat or the consequence."
    )
    return PROMPTS["system_analyst"], user


def build_player_fit(
    player_name: str,
    role: str,
    fit_score: float,
    metrics_dict: dict,
    role_profile: dict,
) -> tuple[str, str]:
    """
    Player role-fit report.

    Returns (system, user) prompt tuple.
    Output: fit verdict, top strength, main gap, alt-role suggestion if score < 60.
    Max 150 words.
    """
    all_metrics = sorted(set(metrics_dict) | set(role_profile))
    comparison_lines = [
        f"  {m}: player={metrics_dict.get(m, '—')}  benchmark={role_profile.get(m, '—')}"
        for m in all_metrics
    ]
    comparison = "\n".join(comparison_lines)

    alt_instruction = (
        "\n- Suggest one alternative role where this player's profile fits better."
        if fit_score < 60 else ""
    )

    user = (
        f"Player: {player_name}\n"
        f"Evaluated role: {role}\n"
        f"Fit score: {fit_score:.1f}/100\n\n"
        f"Metrics vs benchmark:\n{comparison}\n\n"
        f"Write a player fit report (max 150 words) covering:\n"
        f"- Fit verdict: is this the right role? Reference the score.\n"
        f"- Top strength for this role: name the specific metric and value.\n"
        f"- Main gap: name the specific deficit vs the benchmark."
        f"{alt_instruction}"
    )
    return PROMPTS["system_scout"], user


def build_match_summary(
    home: str,
    away: str,
    score: str,
    stats_dict: dict,
) -> tuple[str, str]:
    """
    Three-sentence tactical match summary.

    Returns (system, user) prompt tuple.
    stats_dict should contain side-by-side stats for both teams.
    Max 100 words.
    """
    user = (
        f"Match: {home} {score} {away}\n\n"
        f"Statistics:\n{_fmt_stats(stats_dict)}\n\n"
        "Write exactly 3 sentences (max 100 words total) describing "
        "the tactical story of this match. "
        "Each sentence must reference at least one specific stat. "
        "No filler. Start with the most decisive tactical factor."
    )
    return PROMPTS["system_analyst"], user


# ── Fact-grounded narrative (facts.py) ──────────────────────────────────────

_FACT_TASKS = {
    "team": (
        "Scrivi un briefing tattico per lo staff (massimo 220 parole) con quattro sezioni "
        "titolate: Identità di gioco, Punti di forza, Punti deboli, Cosa cambiare."
    ),
    "opponent": (
        "Scrivi un report pre-partita sull'avversario per lo staff (massimo 250 parole) con "
        "quattro sezioni titolate: Come gioca, Dove è vulnerabile, Contro squadre come noi, "
        "Piano gara (due indicazioni concrete)."
    ),
    "match": (
        "Racconta la partita in 4-6 frasi (massimo 150 parole): chi ha dominato e come, "
        "i momenti decisivi, se il risultato rispecchia le occasioni create."
    ),
}

FACT_SYSTEM = (
    "Sei un analista tattico di calcio. Scrivi in italiano, in modo diretto e concreto. "
    "REGOLE RIGIDE: usa SOLO le informazioni dei FATTI forniti. Non aggiungere numeri, "
    "nomi, moduli o confronti che non compaiono nei fatti. Copia i numeri esattamente "
    "come sono scritti. Dopo ogni frase che usa un fatto, cita il suo identificativo tra "
    "parentesi quadre, ad esempio [F3] o [F2, F7]. Se un fatto segnala un campione "
    "piccolo, dillo. Le raccomandazioni devono derivare dai fatti citati. "
    "Attribuisci ogni numero alla squadra o al giocatore indicato nel fatto e non "
    "cambiarne il significato (es. tocchi nell'area avversaria = azione offensiva)."
)


def build_from_facts(kind: str, title: str, fact_prompt: str) -> tuple[str, str]:
    """(system, user) for a narrative grounded only in the given fact sheet."""
    user = f"Oggetto: {title}\n\nFATTI:\n{fact_prompt}\n\nCOMPITO: {_FACT_TASKS[kind]}"
    return FACT_SYSTEM, user


def build_fix_request(previous: str, unknown: list[str], bad_cites: list[str]) -> str:
    problems = []
    if unknown:
        problems.append("numeri che non compaiono nei fatti: " + ", ".join(unknown))
    if bad_cites:
        problems.append("citazioni a fatti inesistenti: " + ", ".join(bad_cites))
    return (
        "Il testo seguente contiene " + "; ".join(problems) + ".\n"
        "Riscrivilo togliendo o correggendo quelle parti, usando solo i FATTI e le loro "
        "citazioni. Restituisci solo il testo corretto.\n\nTESTO:\n" + previous
    )


# ── LLM routing ───────────────────────────────────────────────────────────────

def call_llm(prompt: str, backend: str, system: str = "", model: str | None = None) -> str:
    """Route LLM call to Claude API or local Ollama (optionally a specific Ollama model)."""
    if backend == "Claude API":
        return _call_claude(prompt, system)
    return _call_ollama(prompt, system, model or OLLAMA_MODEL)


def ollama_models() -> list[str]:
    """Chat models installed in the local Ollama (embedding models excluded)."""
    try:
        r = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=3)
        r.raise_for_status()
        names = [m["name"] for m in r.json().get("models", [])]
    except Exception:
        return [OLLAMA_MODEL]
    return [n for n in names if "embed" not in n] or [OLLAMA_MODEL]


def _call_claude(prompt: str, system: str) -> str:
    # Credentials resolved by the SDK (ANTHROPIC_API_KEY or `ant auth login`).
    client = anthropic.Anthropic()
    kwargs = {
        "model":         CLAUDE_MODEL,
        "max_tokens":    CLAUDE_MAX_TOKENS,
        "output_config": {"effort": CLAUDE_EFFORT},
        "messages":      [{"role": "user", "content": prompt}],
        # Server-side fallback: if the model declines, the API retries on a
        # fallback model within the same call.
        "betas":         ["server-side-fallback-2026-07-01"],
        "extra_body":    {"fallbacks": "default"},
    }
    if system:
        kwargs["system"] = system
    response = client.beta.messages.create(**kwargs)
    if response.stop_reason == "refusal":
        raise RuntimeError("Claude ha rifiutato la richiesta.")
    # Thinking blocks precede the text block: pick the text explicitly.
    return "".join(b.text for b in response.content if b.type == "text")


def _call_ollama(prompt: str, system: str, model: str) -> str:
    messages = ([{"role": "system", "content": system}] if system else []) + [
        {"role": "user", "content": prompt}]
    payload = {
        "model":    model,
        "messages": messages,
        "stream":   False,
        "think":    False,   # qwen3.x: answer directly, no reasoning trace
        "options":  {"temperature": LLM_TEMPERATURE, "num_predict": LLM_MAX_TOKENS},
    }
    response = requests.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload, timeout=300)
    if response.status_code == 400 and "think" in response.text:
        payload.pop("think")  # models without thinking support reject the flag
        response = requests.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload, timeout=300)
    response.raise_for_status()
    text = response.json()["message"]["content"]
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def narrate(kind: str, title: str, fact_sheet: list[dict], backend: str,
            model: str | None = None, max_fixes: int = 1) -> dict:
    """
    Generate a fact-grounded narrative and check it. If the text contains
    numbers or citations not backed by the fact sheet, ask the model to fix
    it (up to max_fixes times). Returns {text, check, attempts}.
    """
    import facts  # local import: facts depends on analysis/metrics

    system, user = build_from_facts(kind, title, facts.as_prompt(fact_sheet))
    text = call_llm(user, backend, system, model)
    check = facts.validate(text, fact_sheet)
    attempts = 1
    while not check["ok"] and attempts <= max_fixes:
        fix = build_fix_request(text, check["unknown_numbers"], check["bad_citations"])
        text = call_llm(user + "\n\n" + fix, backend, system, model)
        check = facts.validate(text, fact_sheet)
        attempts += 1
    return {"text": text, "check": check, "attempts": attempts}
