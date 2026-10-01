"""
Async streaming client for OpenRouter's chat completions API.
Mirrors the interface of ollama_client so callers can switch between
providers without changing their streaming / error-handling logic.

Key design choices:
- Uses the OpenAI-compatible /chat/completions endpoint that OpenRouter
  exposes, with streaming (stream: true, SSE).
- Returns the curated OPENROUTER_FREE_MODELS list from settings instead
  of calling /api/v1/models — we don't want to surface the full 300+
  model catalog in the UI.
- Catches HTTP 429 from OpenRouter's shared free-tier rate limit and
  raises a clear, user-facing error message.
"""
import json
from collections.abc import AsyncIterator

import httpx
from settings import OPENROUTER_DEFAULT_MODEL, OPENROUTER_FREE_MODELS, settings

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouterError(RuntimeError):
    pass


def is_available() -> bool:
    """True when an OpenRouter API key is configured."""
    return bool(settings.openrouter_api_key)


def list_models() -> list[dict]:
    """Returns the curated free-model list (no live API call)."""
    return OPENROUTER_FREE_MODELS


async def stream_generate(
    system_prompt: str,
    user_prompt: str,
    model: str | None = None,
) -> AsyncIterator[str]:
    """Yields response text chunks streamed from OpenRouter."""
    if not is_available():
        raise OpenRouterError(
            "OpenRouter API key is not configured. "
            "Add OPENROUTER_API_KEY to your .env file."
        )

    payload = {
        "model": model or OPENROUTER_DEFAULT_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": True,
        "temperature": 0.2,
    }

    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/ai-code-reviewer",
        "X-Title": "AI Code Reviewer",
    }

    timeout = httpx.Timeout(settings.request_timeout_seconds)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client: #noqa: SIM117
            async with client.stream(
                "POST",
                OPENROUTER_API_URL,
                json=payload,
                headers=headers,
            ) as response:
                if response.status_code == 429:
                    body = await response.aread()
                    raise OpenRouterError(
                        "OpenRouter free-tier rate limit hit "
                        "(shared across all free models, resets shortly) — "
                        "try again in a minute or switch to Ollama."
                    )
                if response.status_code != 200:
                    body = await response.aread()
                    raise OpenRouterError(
                        f"OpenRouter returned {response.status_code}: "
                        f"{body.decode(errors='replace')}"
                    )

                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line:
                        continue
                    # OpenRouter SSE format: "data: {...}" or "data: [DONE]"
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue
                        # Check for error in the response body
                        if "error" in chunk:
                            err = chunk["error"]
                            msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
                            raise OpenRouterError(msg)
                        choices = chunk.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})
                            text = delta.get("content", "")
                            if text:
                                yield text
    except httpx.ConnectError as e:
        raise OpenRouterError(
            "Could not reach OpenRouter API. Check your internet connection."
        ) from e
