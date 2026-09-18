# Answer

## Conclusion

The non-streaming client receives HTTP 503. The streaming client receives HTTP 200. The same upstream error produces different HTTP status codes depending on the request mode.

## Mechanism

### Non-streaming path

When `stream` is false, the route handler at line 196 calls `_client().messages.create(**kw)` inside `asyncio.to_thread`. The Anthropic SDK raises `anthropic.APIStatusError` with `status_code=503`. The `except` block at line 201 catches it and constructs a new `Response` object with `status_code=e.status_code` (503). This `Response` is returned to FastAPI, which sends both the 503 status and the JSON error body to the client in a single `http.response.start` + `http.response.body` sequence. The status code faithfully reflects the upstream error.

### Streaming path

When `stream` is true, the route handler at line 174 enters the streaming branch. It constructs a `StreamingResponse` wrapping the `_safe_stream()` async generator and returns it at line 188. At this point, the generator has not executed a single iteration.

FastAPI passes this `StreamingResponse` to the ASGI server (uvicorn). The ASGI server calls `StreamingResponse.stream_response()`, which is defined in Starlette's `responses.py`. The first thing `stream_response` does is send the `http.response.start` ASGI event containing the status code (200) and response headers (`text/event-stream`, `cache-control: no-cache`, etc.) to the client. This happens before the `async for chunk in self.body_iterator` loop begins.

Only after the 200 and headers are committed does the ASGI server start iterating the generator. `_safe_stream()` calls `_stream_gen(kw)`, which spawns `_stream_worker` in a background thread. The worker calls `_client().messages.with_streaming_response.create(**kw)`, which raises `anthropic.APIStatusError` because upstream returned 503. The exception is placed into the queue at line 136. `_stream_gen` retrieves it from the queue at line 149 and re-raises it. `_safe_stream` catches it at line 181 and yields a synthetic SSE frame:

```
event: error
data: {"type": "error", "error": {"type": "api_error", "message": "..."}}
```

This SSE frame is sent as body content inside the already-open HTTP 200 response. The client receives the error information, but only as stream content, not as an HTTP-level status code.

### The divergence point

The divergence occurs because of how Starlette's `StreamingResponse` works. It does not inspect or wait for the generator before committing the HTTP status. The `stream_response` method unconditionally sends `http.response.start` with status 200 and then begins iterating. There is no mechanism to "peek" at the first chunk and retroactively change the status code. Once headers are on the wire, they cannot be modified under HTTP/1.1.

In contrast, the non-streaming path constructs a complete `Response` object (with the correct status code) only after the upstream call finishes, so the error code is known before any bytes are sent.

## Boundaries

This behavior is a property of the ASGI protocol and Starlette's `StreamingResponse`, not a bug specific to this proxy. Any FastAPI application that returns a `StreamingResponse` wrapping a generator that might fail will exhibit the same pattern: the client sees HTTP 200 regardless of what happens inside the generator.

The proxy's `_safe_stream` wrapper at lines 177-186 is a mitigation, not a fix. It ensures the error information reaches the client as SSE content rather than crashing the stream silently. But it cannot change the HTTP status code because that ship has sailed before the generator runs.

## Verification

Run the test harness with a local mock upstream that returns 503:

```
Non-streaming: HTTP 503
  Content-Type: application/json
  Body: {"type": "error", "error": {"type": "not_found_error", "message": "no available channel"}}

Streaming: HTTP 200
  Content-Type: text/event-stream; charset=utf-8
  Headers committed before body:
    cache-control: no-cache
    x-accel-buffering: no
    transfer-encoding: chunked
  SSE body:
    event: error
    data: {"type": "error", "error": {"type": "api_error", "message": "..."}}
```

The non-streaming path returns the upstream status code (503) directly. The streaming path returns 200 with the error encoded as an SSE event inside the response body.
