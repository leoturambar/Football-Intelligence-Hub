import os
import json
import requests
import anthropic
from config import (
    CLAUDE_MODEL, OLLAMA_MODEL, OLLAMA_URL,
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


# ── LLM routing ───────────────────────────────────────────────────────────────

def call_llm(prompt: str, backend: str, system: str = "") -> str:
    """Route LLM call to Claude API or local Ollama."""
    if backend == "Claude API":
        return _call_claude(prompt, system)
    return _call_ollama(prompt, system)


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


def _call_ollama(prompt: str, system: str) -> str:
    full_prompt = f"{system}\n\n{prompt}" if system else prompt
    payload = {
        "model":   OLLAMA_MODEL,
        "prompt":  full_prompt,
        "stream":  False,
        "options": {
            "temperature": LLM_TEMPERATURE,
            "num_predict": LLM_MAX_TOKENS,
        },
    }
    response = requests.post(OLLAMA_URL, json=payload, timeout=120)
    response.raise_for_status()
    return response.json()["response"]