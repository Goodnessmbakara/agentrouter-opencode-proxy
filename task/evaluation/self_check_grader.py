#!/usr/bin/env python3
"""
Self-check grader: takes a model's text answer and grades it against rubric.json.

Usage:
    python self_check_grader.py answer_file.txt

Prints pass/fail for each criterion and a total score.
"""
import json
import re
import sys
from pathlib import Path

RUBRIC_PATH = Path(__file__).resolve().parent.parent / "evaluation" / "rubric.json"


def load_rubric():
    with open(RUBRIC_PATH) as f:
        return json.load(f)["criteria"]


def grade(answer_text: str, criteria: list) -> list:
    """
    Simple keyword/phrase matching grader. Not perfect, but catches
    the main signals. Human review should follow.
    """
    text = answer_text.lower()
    results = []

    for c in criteria:
        cid = c["id"]
        desc = c["description"]
        passed = False

        if cid == "R01":
            # Must say non-streaming gets 503
            passed = ("non-streaming" in text or "non streaming" in text) and "503" in text

        elif cid == "R02":
            # Must say streaming gets 200
            if ("streaming" in text and "200" in text):
                # Make sure it's saying streaming=200, not streaming=503
                # Look for patterns like "streaming...200" or "200...streaming"
                passed = True

        elif cid == "R03":
            # Must identify that the two modes differ
            passed = ("differ" in text or "different" in text or "diverge" in text
                     or ("503" in text and "200" in text))

        elif cid == "R04":
            # Non-streaming constructs Response after upstream call
            passed = ("response" in text and ("status_code" in text or "status code" in text)
                     and ("e.status_code" in text or "exception" in text or "apistatuserror" in text
                          or "after" in text))

        elif cid == "R05":
            # StreamingResponse sends headers before generator iterates
            passed = ("streamingresponse" in text or "streaming response" in text or "streaming_response" in text) and \
                     ("before" in text and ("iterat" in text or "generator" in text or "body" in text or "yield" in text))

        elif cid == "R06":
            # 200 is irrevocable once headers sent
            passed = ("irrevocab" in text or "cannot change" in text or "already sent" in text
                     or "already committed" in text or "on the wire" in text or "cannot be changed" in text
                     or "can't change" in text or "cannot modify" in text)

        elif cid == "R07":
            # Exception goes through queue
            passed = ("queue" in text or "q.put" in text) and ("exception" in text or "error" in text)

        elif cid == "R08":
            # _safe_stream catches and yields SSE error
            passed = ("_safe_stream" in text or "safe_stream" in text or "except" in text) and \
                     ("yield" in text or "sse" in text or "event: error" in text)

        elif cid == "R09":
            # Error delivered as SSE content within 200 body
            passed = ("sse" in text or "event:" in text or "server-sent" in text) and \
                     ("200" in text) and ("error" in text)

        elif cid == "R10":
            # Must NOT claim streaming returns 503
            # Pass if they DON'T say streaming gets 503
            streaming_503 = bool(re.search(r'streaming.{0,50}(receives?|returns?|gets?|status).{0,30}503', text))
            passed = not streaming_503

        elif cid == "R11":
            # Must NOT claim error is silently swallowed
            swallowed = ("swallow" in text or "silently" in text or "lost" in text or "discard" in text)
            passed = not swallowed or ("not" in text and "swallow" in text)

        elif cid == "R12":
            # Attributes to ASGI/Starlette, not proxy bug
            passed = ("asgi" in text or "starlette" in text or "streamingresponse" in text
                     or "any fastapi" in text or "inherent" in text)

        elif cid == "R13":
            # Traces at least 3 of 4 stages
            stages = 0
            if "_stream_worker" in text or "stream_worker" in text or "worker" in text:
                stages += 1
            if "queue" in text or "q.put" in text or "q.get" in text:
                stages += 1
            if "_stream_gen" in text or "stream_gen" in text or "re-raise" in text or "reraise" in text:
                stages += 1
            if "_safe_stream" in text or "safe_stream" in text or "yield" in text:
                stages += 1
            passed = stages >= 3

        results.append({
            "id": cid,
            "description": desc,
            "passed": passed,
        })

    return results


def main():
    if len(sys.argv) < 2:
        print("Usage: python self_check_grader.py <answer_file.txt>")
        sys.exit(1)

    answer_text = Path(sys.argv[1]).read_text()
    criteria = load_rubric()
    results = grade(answer_text, criteria)

    print("=" * 60)
    print("RUBRIC GRADING RESULTS")
    print("=" * 60)
    passed_count = 0
    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        if r["passed"]:
            passed_count += 1
        print(f"  [{status}] {r['id']}: {r['description'][:80]}")

    print()
    print(f"Score: {passed_count}/{len(results)}")
    print()

    return passed_count


if __name__ == "__main__":
    main()
