# CLAUDE.md — Handoff Context

## What This Repo Is

A local reverse proxy (`proxy.py`, 233 lines) that lets Node.js AI coding clients (OpenCode, Cursor, Claude Code, Cline, etc.) use AgentRouter (agentrouter.org) as an Anthropic-compatible LLM backend. It exists because AgentRouter's Aliyun WAF fingerprints TLS handshakes and only allows the Python sync `anthropic` SDK through. The proxy receives HTTP requests from any client, re-issues them using the sync SDK, and streams SSE responses back.

Built with FastAPI + uvicorn. Single file, no database, no auth of its own.

## What Was Built On Top Of It

An **Askable Labs SWE Q&A evaluation task** — a hard question about this codebase designed to trip up frontier coding models. Everything lives under `task/`.

### The Question (task/instruction.md)

When upstream AgentRouter returns HTTP 503 ("no available channel"), what HTTP status code does the downstream client receive for streaming vs non-streaming requests?

### The Answer (task/reference/answer.md)

- **Non-streaming:** Client gets **HTTP 503**. The Anthropic SDK raises `APIStatusError`, the `except` block at line 201 catches it, and `Response(status_code=e.status_code)` is returned. Headers haven't been sent yet, so the real error code goes through.
- **Streaming:** Client gets **HTTP 200**. The route handler returns `StreamingResponse(_safe_stream(), ...)` at line 188. Starlette's `stream_response()` sends `http.response.start` with status 200 before iterating the generator. The upstream 503 is only discovered later when `_stream_worker` tries to connect, raises an exception, puts it on the queue, `_stream_gen` re-raises it, and `_safe_stream` catches it and yields an `event: error` SSE frame. By then, the 200 is already on the wire.

### Why Models Get It Wrong

Without reading the code, models assume the proxy checks upstream before committing headers (says 503). With code access, models trace the `StreamingResponse` default `status_code=200` and get it right. The rubric (13 criteria) separates "right status code, wrong mechanism" from "right status code, right mechanism."

## Key Architecture

```
Client (OpenCode/Cursor/etc.)
    │
    ▼  HTTP POST /messages
proxy.py (FastAPI, port 7187)
    │
    ├─ stream=false → asyncio.to_thread(_run) → SDK .create() → Response(status_code=...)
    │
    └─ stream=true  → StreamingResponse(_safe_stream())
                          │
                          ▼
                       _stream_gen() → spawns _stream_worker in daemon Thread
                          │                    │
                          │              SDK .with_streaming_response.create()
                          │                    │
                          ▼                    ▼
                       queue.Queue ◄──── raw SSE bytes or Exception
                          │
                          ▼
                       yields chunks (or re-raises exception)
                          │
                          ▼
                       _safe_stream catches errors → yields SSE error frame
```

## File Map

```
proxy.py                          # The entire proxy (233 lines)
pyproject.toml                    # Deps: fastapi, uvicorn, httpx, anthropic
start.sh                          # Venv setup + launch script
README.md                         # Full docs, research trail, client setup
AGENT_SETUP_PROMPT.md             # Paste-into-agent setup prompt
CONTRIBUTING.md                   # Contribution guidelines

task/
├── instruction.md                # The question (what participants see)
├── provenance.json               # Repo ownership, licensing, dep pins, contamination probe
├── reference/
│   ├── answer.md                 # Full reference answer with mechanism trace
│   └── evidence.json             # 6 evidence records with file:line citations
├── evaluation/
│   ├── rubric.json               # 13 binary grading criteria
│   ├── self_check_grader.py      # Automated keyword grader (not a substitute for human review)
│   ├── self_check_prompt.txt     # Prompt template for code-access self-checks
│   ├── self_check_1_gemini_no_code.txt   # Gemini 3.1 Pro, no code — WRONG (said 503)
│   ├── self_check_blind_a.txt            # Flash blind — got status codes, missed mechanism
│   ├── self_check_blind_b.txt            # Flash blind — got status codes, missed mechanism
│   ├── self_check_blind_c.txt            # Flash blind — got status codes, missed mechanism
│   ├── self_check_2_flash_with_code.txt  # Flash with code — 13/13
│   ├── self_check_3_flash_with_code.txt  # Flash with code — 13/13
│   └── self_check_4_flash_with_code.txt  # Flash with code — 13/13
└── environment/
    ├── Dockerfile                # Offline container (python:3.11-slim, --network none)
    ├── mock_upstream.py          # Local stub returning 503 on localhost:9000
    ├── test_harness.py           # Starts mock + proxy, sends both request types, captures output
    └── experiment_output.txt     # Captured proof: non-streaming=503, streaming=200
```

## Important Commits

| Commit | What |
|--------|------|
| `336bd4e` | **Pinned source commit** — the version of proxy.py the task question is about. All evidence.json line numbers reference this. |
| `e484b0a` | **Task commit** — added all task/ artifacts, self-checks, and environment. |

## Dependency Pinning

- `anthropic==0.49.0` — pinned because >=1.0 migrated from `httpx` to `httpx2`, breaking the custom `httpx.Client` at line 46-53. The proxy was written against 0.49.0.
- `fastapi>=0.111`, `uvicorn>=0.30`, `httpx>=0.27`
- Python 3.11+

## Running the Experiment

```bash
# Set up venv (if not already done)
python3 -m venv .venv
.venv/bin/pip install fastapi "uvicorn[standard]" httpx "anthropic==0.49.0" pytest

# Run the test harness (starts mock upstream + proxy, captures HTTP status codes)
.venv/bin/python task/environment/test_harness.py

# Expected output:
#   Non-streaming: HTTP 503
#   Streaming:     HTTP 200
#   >>> STATUS CODES DIFFER <<<
```

## Current Status

- Task is **built, verified, committed, and pushed** to GitHub.
- Submitted to Francisco at Askable Labs for review.
- Waiting for the 30-minute walkthrough where we defend the conclusion, evidence, and rubric.
- Expect at least one revision round (per the brief).

## Potential Revision Areas

1. **Question difficulty with code access:** All three Flash attempts with code access scored 13/13. If Francisco wants the task to trip models even with code access, the question may need to be combined with a follow-up about thread lifecycle on client disconnection (the `_stream_worker` daemon thread has no cancellation mechanism).
2. **Rubric false positives:** The automated `self_check_grader.py` has regex issues with R10 (false-fails when "streaming" and "503" appear near each other in the non-streaming section). Human review is needed.
3. **anthropic SDK version:** If the task needs to run against a newer SDK, the `_HTTP_CLIENT` custom httpx.Client at line 46 needs to be replaced with an `httpx2.Client` or removed entirely.
