#!/usr/bin/env python3
"""
Test harness: captures the exact HTTP status code and body content
the downstream client receives when upstream returns 503.

Starts mock_upstream.py on port 9000, starts proxy.py on port 7187
(pointed at the mock), then sends both a streaming and non-streaming
request and prints the results.

Run:
    .venv/bin/python task/environment/test_harness.py
"""
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PYTHON = str(REPO_ROOT / ".venv" / "bin" / "python")

MOCK_PORT = 9000
PROXY_PORT = 7187
PROXY_URL = f"http://127.0.0.1:{PROXY_PORT}"

REQUEST_BODY = {
    "model": "claude-opus-4-6",
    "max_tokens": 50,
    "messages": [{"role": "user", "content": "hello"}],
}


def wait_for_port(port, host="127.0.0.1", timeout=10):
    """Block until a TCP connection succeeds on host:port."""
    import socket
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except OSError:
            time.sleep(0.2)
    raise TimeoutError(f"Port {port} not open after {timeout}s")


def main():
    procs = []
    try:
        # 1. Start mock upstream
        print("=" * 60)
        print("STEP 1: Starting mock upstream on port", MOCK_PORT)
        print("=" * 60)
        mock = subprocess.Popen(
            [PYTHON, str(REPO_ROOT / "task" / "environment" / "mock_upstream.py")],
            env={**os.environ},
            stderr=subprocess.PIPE,
        )
        procs.append(mock)
        wait_for_port(MOCK_PORT)
        print("  Mock upstream is ready.\n")

        # 2. Start proxy pointed at mock
        print("=" * 60)
        print("STEP 2: Starting proxy on port", PROXY_PORT, "-> mock upstream")
        print("=" * 60)
        proxy_env = {
            **os.environ,
            "AGENTROUTER_API_KEY": "sk-test-dummy-key-for-offline",
        }
        proxy = subprocess.Popen(
            [PYTHON, "-c", f"""
import sys
sys.path.insert(0, '{REPO_ROOT}')

# Patch TARGET before importing app
import proxy as p
p.TARGET = 'http://127.0.0.1:{MOCK_PORT}'
# Force re-creation of client with patched target
p._anthropic_client = None

import uvicorn
uvicorn.run(p.app, host='127.0.0.1', port={PROXY_PORT}, log_level='warning')
"""],
            env=proxy_env,
            stderr=subprocess.PIPE,
        )
        procs.append(proxy)
        wait_for_port(PROXY_PORT)
        print("  Proxy is ready.\n")

        # 3. Non-streaming request
        print("=" * 60)
        print("TEST A: Non-streaming request")
        print("=" * 60)
        body_a = {**REQUEST_BODY, "stream": False}
        resp_a = httpx.post(
            f"{PROXY_URL}/messages",
            json=body_a,
            timeout=15,
        )
        print(f"  HTTP status code:  {resp_a.status_code}")
        print(f"  Content-Type:      {resp_a.headers.get('content-type', '(none)')}")
        print(f"  Body (first 500):  {resp_a.text[:500]}")
        print()

        # 4. Streaming request
        print("=" * 60)
        print("TEST B: Streaming request")
        print("=" * 60)
        body_b = {**REQUEST_BODY, "stream": True}
        with httpx.stream(
            "POST",
            f"{PROXY_URL}/messages",
            json=body_b,
            timeout=15,
        ) as resp_b:
            print(f"  HTTP status code:  {resp_b.status_code}")
            print(f"  Content-Type:      {resp_b.headers.get('content-type', '(none)')}")
            print(f"  Headers sent to client BEFORE any body bytes:")
            for k, v in resp_b.headers.items():
                print(f"    {k}: {v}")
            print()

            print("  SSE body content:")
            full_body = b""
            for chunk in resp_b.iter_bytes():
                full_body += chunk
            body_text = full_body.decode("utf-8", errors="replace")
            print(f"  {body_text}")
        print()

        # 5. Summary
        print("=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print(f"  Non-streaming: HTTP {resp_a.status_code}")
        print(f"  Streaming:     HTTP {resp_b.status_code}")
        print()
        if resp_a.status_code != resp_b.status_code:
            print("  >>> STATUS CODES DIFFER <<<")
            print(f"  Non-streaming gets the real upstream error code ({resp_a.status_code}).")
            print(f"  Streaming always gets {resp_b.status_code} because headers are")
            print("  committed before the generator runs.")
        else:
            print("  Status codes match (unexpected for this test).")

    finally:
        for p in procs:
            try:
                p.send_signal(signal.SIGTERM)
                p.wait(timeout=3)
            except Exception:
                p.kill()


if __name__ == "__main__":
    main()
