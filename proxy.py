#!/usr/bin/env python3
"""
agentrouter-proxy: thin reverse-proxy for agentrouter.org.

AgentRouter's Aliyun WAF fingerprints TLS handshakes AND inspects
Anthropic SDK-specific headers (x-stainless-*, user-agent). Raw httpx
is blocked. Only requests made through the Python sync `anthropic` SDK
pass the check.

This proxy uses `anthropic.Anthropic` (sync) in a thread so OpenCode's
Node.js AI SDK can talk to it on localhost and we handle the upstream
leg with the correct fingerprint.

Usage:
    python proxy.py           # reads key from ~/.config/opencode/api_keys/AGENT_ROUTER_API_KEY
    AGENTROUTER_API_KEY=sk-... python proxy.py
"""
import asyncio
import json
import os
import queue
import threading
from pathlib import Path

import anthropic
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import Response, StreamingResponse

# ── Config ─────────────────────────────────────────────────────────────────────

TARGET   = "https://agentrouter.org"
PORT     = 7187
KEY_FILE = Path.home() / ".config/opencode/api_keys/AGENT_ROUTER_API_KEY"


def _api_key() -> str:
    k = os.environ.get("AGENTROUTER_API_KEY", "").strip()
    if not k and KEY_FILE.exists():
        k = KEY_FILE.read_text().strip()
    if not k:
        raise RuntimeError(
            "No AGENTROUTER_API_KEY. "
            f"Set env var or create {KEY_FILE}"
        )
    return k


def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=_api_key(), base_url=TARGET)


# ── Request translation ─────────────────────────────────────────────────────────────────

_SKIP   = {"stream"}                        # handled separately
_STRIP  = {"thinking", "output_config"}     # non-standard; trigger agentrouter content filter


def _kwargs(body: dict) -> dict:
    """Forward all fields except stream (handled separately) and non-standard extras."""
    return {k: v for k, v in body.items() if k not in _SKIP and k not in _STRIP}


# ── Streaming helper ───────────────────────────────────────────────────────────────────

def _stream_worker(kw: dict, q: queue.Queue) -> None:
    """
    Run inside a thread. Uses the sync Anthropic SDK's with_streaming_response
    to get raw SSE bytes and puts them into the queue, stripping any
    non-standard event types (e.g. billing_summary) that break OpenCode's parser.
    """
    SKIP_EVENTS: set[bytes] = {b"billing_summary"}

    try:
        with _client().messages.with_streaming_response.create(**kw) as resp:
            buf = b""
            skip_block = False

            for raw_chunk in resp.iter_bytes(chunk_size=1024):
                buf += raw_chunk

                while True:
                    nl = buf.find(b"\n")
                    if nl == -1:
                        break
                    line = buf[: nl + 1]          # include \n
                    buf  = buf[nl + 1:]
                    stripped = line.rstrip(b"\r\n")

                    if stripped.startswith(b"event:"):
                        event_name = stripped[6:].strip()
                        skip_block = event_name in SKIP_EVENTS
                        if skip_block:
                            continue
                    elif skip_block:
                        if stripped == b"":
                            skip_block = False    # blank line ends the event block
                        continue

                    q.put(line)

            if buf:
                q.put(buf)

    except Exception as exc:
        q.put(exc)
    finally:
        q.put(None)  # sentinel


async def _stream_gen(kw: dict):
    q: queue.Queue = queue.Queue()
    t = threading.Thread(target=_stream_worker, args=(kw, q), daemon=True)
    t.start()
    loop = asyncio.get_event_loop()
    while True:
        chunk = await loop.run_in_executor(None, q.get)
        if chunk is None:
            break
        if isinstance(chunk, Exception):
            raise chunk
        yield chunk


# ── Routes ────────────────────────────────────────────────────────────────────────

app = FastAPI()


@app.post("/v1/messages")
@app.post("/messages")
async def messages(request: Request):
    body = await request.json()
    kw   = _kwargs(body)

    if body.get("stream", False):
        kw["stream"] = True

        async def _safe_stream():
            try:
                async for chunk in _stream_gen(kw):
                    yield chunk
            except anthropic.APIStatusError as e:
                err = json.dumps({"type": "error", "error": {"type": "api_error", "message": str(e.body)}})
                yield f"event: error\ndata: {err}\n\n".encode()
            except Exception as e:
                err = json.dumps({"type": "error", "error": {"type": "api_error", "message": str(e)}})
                yield f"event: error\ndata: {err}\n\n".encode()

        return StreamingResponse(
            _safe_stream(),
            media_type="text/event-stream",
            headers={"cache-control": "no-cache", "x-accel-buffering": "no"},
        )

    # Non-streaming: sync SDK call in thread
    def _run():
        return _client().messages.create(**kw)

    try:
        msg = await asyncio.to_thread(_run)
        return Response(content=msg.model_dump_json(), media_type="application/json")
    except anthropic.APIStatusError as e:
        return Response(
            content=json.dumps(e.body) if e.body else b"",
            status_code=e.status_code,
            media_type="application/json",
        )
    except Exception as e:
        return Response(
            content=json.dumps({"error": {"message": str(e), "type": "proxy_error"}}),
            status_code=500,
            media_type="application/json",
        )


@app.get("/v1/models")
@app.get("/models")
async def models():
    """Stub model list — AgentRouter's /v1/models is also WAF-blocked for non-allowlisted clients."""
    return {
        "object": "list",
        "data": [
            {"id": "claude-opus-4-6",              "object": "model"},
            {"id": "claude-sonnet-4-5-20250514",   "object": "model"},
            {"id": "claude-haiku-4-5",              "object": "model"},
        ],
    }


# ── Entry point ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"AgentRouter proxy  →  {TARGET}")
    print(f"Listening on http://127.0.0.1:{PORT}")
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
