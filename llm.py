import re
import requests
import anthropic
from config import (
    CLAUDE_MODEL, OLLAMA_MODEL, OLLAMA_BASE_URL,
    LLM_MAX_TOKENS, LLM_TEMPERATURE,
    CLAUDE_MAX_TOKENS, CLAUDE_EFFORT,
)

# ── System prompts ────────────────────────────────────────────────────────────


# ── Private helpers ───────────────────────────────────────────────────────────


# ── Prompt builders (pure — no API calls) ────────────────────────────────────


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
