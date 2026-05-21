import os
import requests
import anthropic
from config import (
    CLAUDE_MODEL, OLLAMA_MODEL, OLLAMA_URL,
    LLM_MAX_TOKENS, LLM_TEMPERATURE
)


def call_llm(prompt: str, backend: str, system: str = "") -> str:
    """Route LLM call to Claude API or local Ollama."""
    if backend == "Claude API":
        return _call_claude(prompt, system)
    return _call_ollama(prompt, system)


def _call_claude(prompt: str, system: str) -> str:
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    kwargs = {
        "model":      CLAUDE_MODEL,
        "max_tokens": LLM_MAX_TOKENS,
        "messages":   [{"role": "user", "content": prompt}],
    }
    if system:
        kwargs["system"] = system
    response = client.messages.create(**kwargs)
    return response.content[0].text


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