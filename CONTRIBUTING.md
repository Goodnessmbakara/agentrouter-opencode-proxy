# Contributing

This project is a community effort. If you find something that works better, breaks in a new way, or could be improved — open an issue or PR.

## Areas where contributions are most welcome

### New client configs
If you get the proxy working with a client not listed in the README (Zed, Aider, LangChain.js, a custom app, etc.), add a setup snippet to the README and the agent prompt.

### Model availability
AgentRouter's model pool changes over time. If you find a model that has reliable capacity (or one that was listed but no longer works), open an issue or update the whitelist note in the README.

### WAF changes
AgentRouter's Aliyun WAF has been updated before — the async/sync distinction was discovered live. If you see `unauthorized client detected` coming back despite using this proxy, open an issue with:
- The exact error response body
- Which client you're using
- Whether curl directly to `agentrouter.org/v1/messages` with `x-api-key` also fails

### Proxy improvements
The proxy (`proxy.py`) is intentionally small. Known improvement areas:
- **Request timeout** — if agentrouter.org hangs, the proxy thread blocks indefinitely. A per-request timeout with clean error response would help.
- **Model list** — `/v1/models` currently returns a hardcoded stub because the real endpoint is WAF-blocked. A periodic background probe using the sync SDK could keep this fresh.
- **Additional SSE event filtering** — if AgentRouter injects new non-standard event types that break clients, they should be added to `SKIP_EVENTS` in `_stream_worker`.
- **Windows support** — `start.sh` is bash only. A `start.bat` or `start.ps1` would help Windows users.

### Better agent setup prompt
The prompt in `AGENT_SETUP_PROMPT.md` was written for OpenCode. If you use it with Claude Code, Cursor, or another agent and something doesn't translate cleanly, improve the relevant step and open a PR.

## How to contribute

1. Fork the repo
2. Make your change
3. Open a PR with a short description of what you changed and why

No formal review process — if it's clearly correct and doesn't break the happy path, it'll be merged.

## Reporting issues

Open a GitHub issue. Include:
- Which client you're using
- The full error message (from the proxy log at `/tmp/agentrouter-proxy.log` and from the client)
- Whether the direct SDK test passes:
  ```bash
  cd ~/.config/opencode/agentrouter-proxy
  .venv/bin/python -c "
  import anthropic
  c = anthropic.Anthropic(api_key='YOUR_KEY', base_url='https://agentrouter.org')
  r = c.messages.create(model='claude-opus-4-6', max_tokens=20, messages=[{'role':'user','content':'hi'}])
  print(r.content[0].text)
  "
  ```
  If this fails, the issue is upstream (AgentRouter's WAF or pool). If it passes but the proxy fails, the issue is in the proxy.
