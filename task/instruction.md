# Streaming Error Status Code

## Repository

`Goodnessmbakara/agentrouter-opencode-proxy` at commit `336bd4ec797c2f4de9fbf63c4e58bbd1de9cd230`.

This is a local reverse proxy that sits between AI coding clients (OpenCode, Claude Code, Cursor, etc.) and AgentRouter, a third-party LLM API aggregator. The proxy receives Anthropic-format HTTP requests from downstream clients, translates them, and forwards them upstream using the Python sync Anthropic SDK. It supports both streaming (SSE) and non-streaming request modes.

The key files are:
- `proxy.py` (233 lines): the entire proxy, including route handlers, streaming worker, and response translation.
- `pyproject.toml`: dependency declarations.

## Scenario

You are debugging a client application that sends requests through this proxy. During a period of high demand, the upstream API (AgentRouter) is returning HTTP 503 errors with the body:

```json
{"type": "error", "error": {"type": "not_found_error", "message": "no available channel"}}
```

Your client application sends two types of requests through the proxy:
1. A **non-streaming** POST to `/messages` with `"stream": false`
2. A **streaming** POST to `/messages` with `"stream": true`

Both hit the same upstream 503.

## Question

For each request type (non-streaming and streaming), what HTTP status code does the downstream client actually receive from the proxy? Explain the mechanism that produces each status code, tracing the path from the upstream 503 through the proxy code to the downstream response. If the status codes differ between the two modes, explain precisely when and why the divergence occurs.
