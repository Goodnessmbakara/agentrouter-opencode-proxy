# agentrouter-opencode-proxy

A local proxy that lets [OpenCode](https://opencode.ai) (and any Node.js AI SDK client) use [AgentRouter](https://agentrouter.org) as an Anthropic-compatible LLM backend.

## Why this exists

AgentRouter is a Chinese API aggregator that provides cheap or free access to models like `claude-opus-4-6`, GPT-4o, DeepSeek, and others. It's fronted by an **Aliyun WAF that fingerprints TLS handshakes at the connection level** — not just bearer tokens.

Only a small allowlist of clients pass the check:
- Claude Code
- Codex CLI
- Gemini CLI
- RooCode / Kilocode / Qwen Code
- The **Python sync `anthropic` SDK** (which those tools are built on)

Everything else — `curl`, Node.js `fetch`, Python `httpx.AsyncClient`, raw `httpx.Client` — gets:

```
{"error":{"message":"unauthorized client detected, contact support..."}}
```

This proxy runs locally on port `7187`, receives requests from OpenCode's Node.js AI SDK, and re-issues them to AgentRouter using the **Python sync `anthropic` SDK** — which carries the correct TLS fingerprint.

## Root cause research

- [agentrouter-org/docs#21](https://github.com/agentrouter-org/docs/issues/21) — documents the WAF allow-list behaviour
- [anomalyco/opencode#5060](https://github.com/anomalyco/opencode/issues/5060) — OpenCode-specific report
- [yowanda/Reckora#67](https://github.com/yowanda/Reckora/pull/67) — first confirmed fix (sync Anthropic SDK)
- [yowanda/Reckora#69](https://github.com/yowanda/Reckora/pull/69) — confirmed async SDK also blocked; sync-in-thread is required

## Additional quirks discovered during setup

| Issue | Fix |
|---|---|
| WAF also blocks `httpx.AsyncClient` and raw `httpx.Client` | Must use `anthropic.Anthropic` (sync), not `AsyncAnthropic` or bare httpx |
| AgentRouter injects `billing_summary` SSE events | Proxy filters them — OpenCode's Zod parser rejects unknown event types |
| OpenCode sends `thinking: {type: adaptive}` and `output_config` fields | Proxy strips these — AgentRouter's content filter blocks requests containing them |
| OpenCode AI SDK calls `/messages` (no `/v1` prefix) | Proxy mounts on both `/messages` and `/v1/messages` |
| `GET /v1/models` is also WAF-blocked | Proxy returns a local stub model list instead |

## Prerequisites

- Python 3.11+
- An [AgentRouter](https://agentrouter.org) account with an API key (`sk-...` from `agentrouter.org/console/token`)
- [OpenCode](https://opencode.ai) installed

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/Goodnessmbakara/agentrouter-opencode-proxy
cd agentrouter-opencode-proxy
```

### 2. Create the virtualenv and install dependencies

```bash
python3 -m venv .venv
.venv/bin/pip install fastapi "uvicorn[standard]" httpx anthropic
```

### 3. Store your API key

```bash
mkdir -p ~/.config/opencode/api_keys
echo 'sk-YOUR_KEY_HERE' > ~/.config/opencode/api_keys/AGENT_ROUTER_API_KEY
chmod 600 ~/.config/opencode/api_keys/AGENT_ROUTER_API_KEY
```

Or set it as an environment variable instead:

```bash
export AGENTROUTER_API_KEY=sk-YOUR_KEY_HERE
```

### 4. Configure OpenCode

Add this to your `~/.config/opencode/opencode.json`:

```json
{
  "provider": {
    "anthropic": {
      "options": {
        "apiKey": "{file:~/.config/opencode/api_keys/AGENT_ROUTER_API_KEY}",
        "baseURL": "http://localhost:7187"
      },
      "whitelist": [
        "claude-opus-4-6"
      ]
    }
  }
}
```

> **Note:** Only `claude-opus-4-6` had reliable capacity on AgentRouter at the time of writing. Other models return `503 no available channel`. Check the [AgentRouter model list](https://agentrouter.org/models) for current availability and update the whitelist accordingly.

### 5. Start the proxy

```bash
bash start.sh
# or directly:
.venv/bin/python proxy.py
```

You should see:

```
AgentRouter proxy  →  https://agentrouter.org
Listening on http://127.0.0.1:7187
```

### 6. Start OpenCode

Open a new terminal and run OpenCode normally. Select `anthropic/claude-opus-4-6` as your model.

## Auto-start on macOS (optional)

```bash
cat > ~/Library/LaunchAgents/org.agentrouter.proxy.plist << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>org.agentrouter.proxy</string>
  <key>ProgramArguments</key>
  <array>
    <string>$(pwd)/.venv/bin/python</string>
    <string>$(pwd)/proxy.py</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>/tmp/agentrouter-proxy.log</string>
  <key>StandardErrorPath</key>
  <string>/tmp/agentrouter-proxy.log</string>
</dict>
</plist>
EOF

launchctl load ~/Library/LaunchAgents/org.agentrouter.proxy.plist
```

## Testing the proxy directly

```bash
# Non-streaming
curl -s http://localhost:7187/messages \
  -H "content-type: application/json" \
  -d '{"model":"claude-opus-4-6","max_tokens":50,"messages":[{"role":"user","content":"hello"}]}'

# Streaming
curl -s http://localhost:7187/messages \
  -H "content-type: application/json" \
  -d '{"model":"claude-opus-4-6","max_tokens":50,"stream":true,"messages":[{"role":"user","content":"hello"}]}'
```

A successful response means the WAF check passed and the model has capacity.

## Troubleshooting

| Error | Cause | Fix |
|---|---|---|
| `unauthorized client detected` | WAF blocked — not using proxy | Ensure you're pointing OpenCode at `http://localhost:7187`, not agentrouter.org directly |
| `503 no available channel` | Model pool exhausted on agentrouter.org | Try another model or wait and retry |
| `content-blocked` | Non-standard request fields | Proxy strips `thinking` and `output_config` already; if it persists, report an issue |
| `Not Found` from proxy | Wrong path | Proxy handles `/messages` and `/v1/messages` — ensure `baseURL` has no path suffix |
| Port 7187 already in use | Old proxy still running | `lsof -ti :7187 \| xargs kill -9` |
