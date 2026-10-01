"""
Centralized configuration. Everything is overridable via environment
variables / .env so the same image works locally, in Docker, and on
whatever free-tier VM you eventually deploy to.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", protected_namespaces=("settings_",)
    )

    # Where Ollama is reachable. In docker-compose this is the service
    # name "ollama"; locally it's your machine's Ollama daemon.
    ollama_host: str = "http://localhost:11434"

    # Pick a model that actually fits your CPU-only 16GB laptop.
    # See README for the trade-off table.
    model_name: str = "qwen2.5-coder:7b-instruct-q4_K_M"

    # Hard caps so a huge paste can't hang the server or blow past
    # the model's context window.
    max_code_chars: int = 20_000
    request_timeout_seconds: int = 300

    # Comma-separated list, or "*" for local dev only.
    cors_origins: str = "*"

    log_level: str = "INFO"

    # OpenRouter API key.  Leave blank to disable the OpenRouter provider.
    # Get a free key at https://openrouter.ai/keys — the five curated
    # free coding models below cost $0 to use.
    openrouter_api_key: str = ""


settings = Settings()


# ── Curated free-tier OpenRouter models ──────────────────────────
# NOT user-editable via .env — this is a curated, known-good list
# of the best FREE coding models, maintained by us so users don't
# have to wade through 500+ models.  All cost $0 to use.
OPENROUTER_FREE_MODELS = [
    {"id": "mistralai/mistral-7b-instruct:free", "label": "Mistral 7B (free)"},
    {"id": "cohere/north-mini-code:free", "label": "Cohere North Mini Code (free)"},
    {"id": "nvidia/nemotron-3-ultra-550b-a55b:free", "label": "Nemotron 3 Ultra (free)"},
    {"id": "openrouter/free", "label": "Auto (any free model)"},
]

OPENROUTER_DEFAULT_MODEL = "mistralai/mistral-7b-instruct:free"


