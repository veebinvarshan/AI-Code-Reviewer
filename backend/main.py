import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import ollama_client
import openrouter_client
from prompts import build_prompt
from settings import settings

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger("ai-code-reviewer")

app = FastAPI(
    title="AI Code Reviewer",
    description="Local, free, open-model code review and explanation service.",
    version="1.0.0",
)

origins = ["*"] if settings.cors_origins == "*" else settings.cors_origins.split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CodeRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=settings.max_code_chars)
    language: str | None = None
    model: str | None = None  # override default model per-request
    provider: str | None = None  # "ollama" (default) or "openrouter"


def _validate_and_build(mode: str, req: CodeRequest) -> tuple[str, str]:
    if not req.code.strip():
        raise HTTPException(400, "code must not be empty")
    return build_prompt(mode, req.code, req.language)


async def _sse_stream(
    system_prompt: str,
    user_prompt: str,
    model: str | None,
    provider: str | None = None,
):
    """Wraps the raw token stream as Server-Sent Events.

    Routes to Ollama or OpenRouter based on the provider field.
    """
    use_openrouter = (provider or "").lower() == "openrouter"

    try:
        if use_openrouter:
            gen = openrouter_client.stream_generate(system_prompt, user_prompt, model)
        else:
            gen = ollama_client.stream_generate(system_prompt, user_prompt, model)

        async for chunk in gen:
            # SSE frames: each 'data:' line is one event. We escape newlines
            # inside a chunk so the frame boundary stays unambiguous.
            safe = chunk.replace("\n", "\\n")
            yield f"data: {safe}\n\n"
        yield "event: done\ndata: {}\n\n"

    except openrouter_client.OpenRouterError as e:
        logger.error("OpenRouter error: %s", e)
        yield f"event: error\ndata: {e!s}\n\n"
    except ollama_client.OllamaError as e:
        logger.error("Ollama error: %s", e)
        yield f"event: error\ndata: {e!s}\n\n"


@app.post("/api/review")
async def review(req: CodeRequest):
    system_prompt, user_prompt = _validate_and_build("review", req)
    return StreamingResponse(
        _sse_stream(system_prompt, user_prompt, req.model, req.provider),
        media_type="text/event-stream",
    )


@app.post("/api/explain")
async def explain(req: CodeRequest):
    system_prompt, user_prompt = _validate_and_build("explain", req)
    return StreamingResponse(
        _sse_stream(system_prompt, user_prompt, req.model, req.provider),
        media_type="text/event-stream",
    )


@app.post("/api/fix")
async def fix(req: CodeRequest):
    system_prompt, user_prompt = _validate_and_build("fix", req)
    return StreamingResponse(
        _sse_stream(system_prompt, user_prompt, req.model, req.provider),
        media_type="text/event-stream",
    )


@app.get("/api/models")
async def models(provider: str = Query(default="ollama")):
    """Returns available models for the given provider.

    - ollama:      live query to Ollama's /api/tags
    - openrouter:  curated OPENROUTER_FREE_MODELS list
    """
    if provider == "openrouter":
        return {"models": openrouter_client.list_models()}
    try:
        model_names = await ollama_client.list_models()
        return {"models": [{"id": m, "label": m} for m in model_names]}
    except Exception as e:
        raise HTTPException(502, f"Could not list models: {e}") from e


@app.get("/api/providers")
async def providers():
    """Reports which providers are available."""
    ollama_ok = await ollama_client.health_check()
    return {
        "ollama": ollama_ok,
        "openrouter": openrouter_client.is_available(),
    }


@app.get("/api/health")
async def health():
    ollama_ok = await ollama_client.health_check()
    return {
        "status": "ok" if ollama_ok else "degraded",
        "ollama_reachable": ollama_ok,
        "default_model": settings.model_name,
        "openrouter_available": openrouter_client.is_available(),
    }


# Serve the static frontend (index.html + assets) from the same origin,
# so there's no separate frontend server to deploy or configure CORS for.
frontend_dir = Path(__file__).parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
