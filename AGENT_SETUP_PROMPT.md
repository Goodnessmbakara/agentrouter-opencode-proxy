# AgentRouter + OpenCode — One-Shot Setup Prompt

Paste the block below into OpenCode (or any AI coding agent) to set up and verify the AgentRouter proxy automatically.

---

```
I need you to set up the AgentRouter proxy so OpenCode can use agentrouter.org as an LLM provider.
Follow every step below and confirm each one works before moving on.

## Background
AgentRouter (agentrouter.org) is fronted by an Aliyun WAF that blocks requests by TLS fingerprint.
Only the Python sync `anthropic` SDK passes the check. We run a local FastAPI proxy on port 7187
that re-issues requests using that SDK so OpenCode's Node.js AI SDK can use AgentRouter.

## Step 1 — Prerequisites check
- Confirm Python 3.11+ is available: `python3 --version`
- Confirm git is available: `git --version`
- If either is missing, install it and stop here to let the user know.

## Step 2 — Clone the proxy repo
```bash
git clone https://github.com/Goodnessmbakara/agentrouter-opencode-proxy ~/.config/opencode/agentrouter-proxy
```
If the directory already exists, run `git -C ~/.config/opencode/agentrouter-proxy pull` instead.

## Step 3 — Create the virtualenv and install dependencies
```bash
cd ~/.config/opencode/agentrouter-proxy
python3 -m venv .venv
.venv/bin/pip install -q fastapi "uvicorn[standard]" httpx anthropic
```
Confirm all four packages installed without errors.

## Step 4 — Store the API key securely
- Ask the user: "Please paste your AgentRouter API key (from agentrouter.org/console/token):"
- Store it:
```bash
mkdir -p ~/.config/opencode/api_keys
echo 'PASTE_KEY_HERE' > ~/.config/opencode/api_keys/AGENT_ROUTER_API_KEY
chmod 600 ~/.config/opencode/api_keys/AGENT_ROUTER_API_KEY
```
- Confirm the file exists and is not empty.

## Step 5 — Update opencode.json
Read the current ~/.config/opencode/opencode.json and add (or merge) this provider block:
```json
"anthropic": {
  "options": {
    "apiKey": "{file:~/.config/opencode/api_keys/AGENT_ROUTER_API_KEY}",
    "baseURL": "http://localhost:7187"
  },
  "whitelist": [
    "claude-opus-4-6"
  ]
}
```
Preserve all existing config. Validate the JSON is still valid after editing.

## Step 6 — Start the proxy
```bash
lsof -ti :7187 | xargs kill -9 2>/dev/null || true
nohup ~/.config/opencode/agentrouter-proxy/.venv/bin/python \
  ~/.config/opencode/agentrouter-proxy/proxy.py \
  > /tmp/agentrouter-proxy.log 2>&1 &
sleep 3
```
Confirm the proxy is listening: `curl -s --max-time 3 http://localhost:7187/models`
Expected: a JSON object with a `data` array of model IDs.

## Step 7 — Test end-to-end (non-streaming)
Run:
```bash
curl -s --max-time 20 http://localhost:7187/messages \
  -H "content-type: application/json" \
  -d '{"model":"claude-opus-4-6","max_tokens":30,"messages":[{"role":"user","content":"say hello"}]}'
```
Expected: a JSON response with `content[0].text` containing a greeting.
If you get `503 no available channel`: the WAF passed but the model pool is exhausted — try again in a few minutes.
If you get `unauthorized client detected`: the proxy is not running or something bypassed it — recheck Step 6.

## Step 8 — Test end-to-end (streaming)
Run:
```bash
curl -s --max-time 20 http://localhost:7187/messages \
  -H "content-type: application/json" \
  -d '{"model":"claude-opus-4-6","max_tokens":30,"stream":true,"messages":[{"role":"user","content":"say hello"}]}' \
  | grep '^data:' | head -5
```
Expected: several `data: {"type":"content_block_delta",...}` lines.
Confirm NO `billing_summary` event appears in the output (the proxy should have stripped it).

## Step 9 — Report results
Summarise:
- Python version found
- Proxy PID and port
- Non-streaming test result (first 60 chars of the reply text)
- Streaming test result (number of delta events received)
- Any errors encountered and how they were resolved

If all tests pass, tell the user: "Proxy is running. Restart OpenCode and select anthropic/claude-opus-4-6."
```
