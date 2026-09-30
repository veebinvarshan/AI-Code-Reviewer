# AI Code Reviewer

A self-hosted code review / code explainer tool powered entirely by
open-weight models running locally through [Ollama](https://ollama.com).
No API keys, no per-token billing, no account required. Runs on CPU.

---

## 1. Reality check for your hardware

You have an **i7-10510U (4 cores / 8 threads, no dedicated GPU) with 16GB RAM.**
That's a real constraint worth being upfront about:

- Everything will run on **CPU only**. There's no CUDA GPU to offload to.
- A quantized 7B model on this CPU will generate roughly **3-8 tokens/second**
  in practice — usable for a code review (which is a one-shot generation you
  read afterward), not for a snappy real-time chat experience.
- 16GB RAM is enough for one quantized 7B model (~4-5GB resident) plus the OS
  and the Python backend, but don't try to run two models at once or keep
  a browser with 40 tabs open at the same time.

### Model recommendation

| Model | Size (Q4_K_M) | Notes |
|---|---|---|
| `qwen2.5-coder:7b-instruct-q4_K_M` | ~4.7GB | **Best default.** Strong code understanding, good instruction following. |
| `deepseek-coder:6.7b-instruct-q4_K_M` | ~4.2GB | Very close second, slightly faster. |
| `codellama:7b-instruct-q4_K_M` | ~4.1GB | The one you originally mentioned — solid, slightly older. |
| `qwen2.5-coder:3b-instruct-q4_K_M` | ~2GB | Use this if 7B feels too slow. Noticeably faster, somewhat less thorough reviews. |
| `starcoder2:7b-q4_K_M` | ~4.4GB | Good if you want a StarCoder-family option specifically. |

Start with `qwen2.5-coder:7b-instruct-q4_K_M`. If a review takes uncomfortably
long, switch to the 3B variant — you only need to change one env var.

---

## 2. What's in this project

```
ai-code-reviewer/
├── backend/                 # FastAPI app
│   ├── main.py               # API routes + serves the frontend
│   ├── ollama_client.py      # streaming client for the local Ollama daemon
│   ├── prompts.py            # review / explain prompt templates
│   ├── settings.py           # env-based configuration
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   └── index.html            # single-page UI, no build step needed
├── tests/
│   └── test_api.py           # pytest suite, mocks Ollama
├── .github/workflows/ci.yml  # lint + test + docker build on every push
├── docker-compose.yml        # one-command full stack (Ollama + backend)
├── ollama-entrypoint.sh       # auto-pulls the model on first container start
├── .env.example
└── README.md
```

**Architecture:** browser → FastAPI backend → local Ollama daemon → quantized
model. The backend streams tokens back to the browser over Server-Sent
Events as they're generated, so you see the review appear incrementally
instead of waiting for the whole thing.

---

## 3. Option A — Run with Docker (recommended, one command)

Prerequisites: [Docker](https://docs.docker.com/get-docker/) and Docker Compose installed. That's it — you do not need Python or Ollama installed on your host.

```bash
git clone <your-repo-url> ai-code-reviewer
cd ai-code-reviewer
docker compose up --build
```

First run will download the Ollama image, build the backend image, and pull
the model (~4-5GB) — this can take several minutes depending on your internet
connection. Subsequent starts are fast.

Then open **http://localhost:8000** in your browser.

To use a different model, set it before starting:
```bash
MODEL_NAME=qwen2.5-coder:3b-instruct-q4_K_M docker compose up --build
```

To stop: `docker compose down` (add `-v` to also delete the downloaded model
and free ~5GB of disk).

---

## 4. Option B — Run natively (no Docker)

**Step 1: Install Ollama**
```bash
curl -fsSL https://ollama.com/install.sh | sh
```
(macOS/Windows: download the installer from ollama.com instead.)

**Step 2: Pull the model**
```bash
ollama pull qwen2.5-coder:7b-instruct-q4_K_M
```

**Step 3: Confirm it works from the terminal**
```bash
ollama run qwen2.5-coder:7b-instruct-q4_K_M "Explain what a race condition is in one sentence."
```

**Step 4: Set up the backend**
```bash
cd backend
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp ../.env.example .env         # defaults already point at localhost:11434
uvicorn main:app --reload --port 8000
```

Open **http://localhost:8000**.

---

## 5. Using it

1. Paste code into the left pane, optionally pick a language.
2. Click **Review** for a structured bugs/security/performance/style review,
   or **Explain** for a plain-language walkthrough.
3. Output streams in as Markdown with syntax-highlighted code blocks.

### API reference (for scripting / editor plugins / CI integration)

```
POST /api/review   { "code": "...", "language": "python", "model": null }  -> SSE stream
POST /api/explain   { "code": "...", "language": "python", "model": null }  -> SSE stream
GET  /api/models                                                            -> { "models": [...] }
GET  /api/health                                                            -> { "status", "ollama_reachable", "default_model" }
```

`model` is optional — omit it to use the server's configured default.

---

## 6. Testing & CI

```bash
pip install pytest ruff
ruff check backend
pytest tests/ -v
```

The GitHub Actions workflow (`.github/workflows/ci.yml`) runs this
automatically on every push/PR, plus a Docker build check. It doesn't need a
real Ollama instance — the tests mock the Ollama client.

---

## 7. Deployment: the honest version

This is the part where "totally free" needs a caveat: **running a 7B model
needs real, sustained CPU/RAM**, and essentially no serverless/free web host
gives you that indefinitely. Here are your actual free options, in order of
how "production" they feel:

### Option 1 — Keep it on your machine, expose it with a tunnel (truly $0, easiest)
Run `docker compose up -d` on your laptop (or better, an always-on mini PC /
old desktop if you have one), then expose it publicly for free with
[Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/):
```bash
cloudflared tunnel --url http://localhost:8000
```
You get a stable HTTPS URL, free, with no port forwarding. Downside: it's
only "up" while your machine is on.

### Option 2 — Oracle Cloud "Always Free" ARM VM (free forever, real 24/7 uptime)
Oracle's free tier includes an Ampere ARM instance with up to **4 OCPUs and
24GB RAM**, free indefinitely (subject to Oracle's current terms — check
before committing, free-tier terms do change). This is enough to run the same
Docker Compose stack as a real always-on server:
```bash
git clone <your-repo-url> && cd ai-code-reviewer
docker compose up -d --build
```
Ollama supports ARM natively. This is the closest thing to a genuinely free,
always-on production deployment.

### Option 3 — Hugging Face Spaces (free CPU tier)
Free Spaces give ~16GB RAM / 2 vCPUs but **sleep after inactivity** and are
tighter on CPU. Use the 3B model here, not the 7B. Push a `Dockerfile`-based
Space and it'll build and run the same image.

### What won't work for free
Vercel, Netlify, Render's free tier, Railway's free tier, and most
serverless platforms are built for stateless, low-CPU web apps — they either
don't support long-lived processes, cap CPU/RAM far below what a 7B model
needs, or bill for exactly this kind of workload. If you outgrow the free
options above, that's the point where you'd pay for a small VPS
(~$5-6/month), not before.

### Production hardening checklist (do this regardless of where you deploy)
- Set `CORS_ORIGINS` to your actual frontend domain, not `*`.
- Put the backend behind a reverse proxy (Caddy or nginx) for TLS — Caddy
  gets you free auto-renewing HTTPS with a two-line Caddyfile.
- Add a request size/rate limiter in front if this is public-facing (the
  backend already caps code length via `MAX_CODE_CHARS`, but add
  IP-based rate limiting at the proxy level too).
- The `/api/models` and `/api/health` endpoints are unauthenticated by
  design for simplicity — add basic auth at the proxy layer if you don't
  want them public.

---

## 8. Troubleshooting

| Symptom | Fix |
|---|---|
| `status: degraded` on `/api/health` | Ollama isn't reachable. Check `docker compose ps` / `ollama serve` is running, and that `OLLAMA_HOST` matches. |
| Very slow first response | Model is being loaded into RAM for the first time this session; subsequent requests are faster. |
| Out-of-memory / container killed | You're likely running the 7B model alongside something else memory-hungry. Try the 3B model or close other apps. |
| `ollama pull` fails in Docker | Check the container has internet access; corporate proxies sometimes need extra Docker config. |

---

## 9. Extending this

Natural next steps, roughly in order of effort:
- **GitHub Action / PR bot**: call `POST /api/review` from a workflow and
  post the response as a PR comment via the GitHub API.
- **VS Code extension**: shell out to the same API from a simple extension
  command bound to a keybinding.
- **Diff-aware review**: instead of reviewing a full paste, accept a git
  diff and prompt the model to focus only on changed lines.
- **Multi-file context**: extend `CodeRequest` to accept multiple files so
  the model can reason about cross-file usage.
