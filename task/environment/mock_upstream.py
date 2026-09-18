#!/usr/bin/env python3
"""
Mock upstream server that simulates AgentRouter responses.

Runs on 127.0.0.1:9000. Returns HTTP 503 with the standard
"no available channel" error body for all POST /v1/messages requests.

Used to reproduce proxy behavior offline without touching agentrouter.org.
"""
import json
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler


ERROR_BODY = json.dumps({
    "type": "error",
    "error": {
        "type": "not_found_error",
        "message": "no available channel",
    },
}).encode()


class MockHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        # Read and discard the request body
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)

        # Always return 503 to simulate capacity exhaustion
        self.send_response(503)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(ERROR_BODY)))
        self.end_headers()
        self.wfile.write(ERROR_BODY)

    def log_message(self, fmt, *args):
        # Quieter output: only show to stderr
        print(f"[mock-upstream] {fmt % args}", file=sys.stderr)


def main(port=9000):
    server = HTTPServer(("127.0.0.1", port), MockHandler)
    print(f"[mock-upstream] Listening on http://127.0.0.1:{port}", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
