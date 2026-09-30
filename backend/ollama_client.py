"""
Thin async wrapper around Ollama's HTTP API.
Docs: the daemon exposes /api/generate (single prompt) and /api/tags
(list locally pulled models). We stream tokens back so the frontend
can render them as they arrive instead of waiting for the full reply.
"""
import json
from collections.abc import AsyncIterator

import httpx
from settings import settings


class OllamaError(RuntimeError):
    pass


async def stream_generate(
    system_prompt: str,
    user_prompt: str,
    model: str | None = None,
) -> AsyncIterator[str]:
    """Yields response text chunks as they stream from Ollama."""
    payload = {
        "model": model or settings.model_name,
        "system": system_prompt,
        "prompt": user_prompt,
        "stream": True,
        "options": {
            "temperature": 0.2,  # low temp: we want consistent, factual review output
        },
    }

    timeout = httpx.Timeout(settings.request_timeout_seconds)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:  # noqa: SIM117
            async with client.stream(
                "POST",
                f"{settings.ollama_host}/api/generate",
                json=payload,
            ) as response:
                if response.status_code != 200:
                    body = await response.aread()
                    raise OllamaError(
                        f"Ollama returned {response.status_code}: {body.decode(errors='replace')}"
                    )
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    chunk = json.loads(line)
                    if chunk.get("error"):
                        raise OllamaError(chunk["error"])
                    text = chunk.get("response", "")
                    if text:
                        yield text
                    if chunk.get("done"):
                        break
    except httpx.ConnectError as e:
        raise OllamaError(
            f"Could not reach Ollama at {settings.ollama_host}. "
            "Is the Ollama service running?"
        ) from e


async def list_models() -> list[str]:
    """Returns the tags of models currently pulled into Ollama."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{settings.ollama_host}/api/tags")
        resp.raise_for_status()
        data = resp.json()
        return [m["name"] for m in data.get("models", [])]


async def health_check() -> bool:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{settings.ollama_host}/api/tags")
            return resp.status_code == 200
    except httpx.HTTPError:
        return False
