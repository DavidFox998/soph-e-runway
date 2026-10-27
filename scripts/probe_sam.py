#!/usr/bin/env python3
"""SAM 3.1 probe: one image, one request variant per run.

Prints the HTTP status, the response's event/key SHAPES and the SAM
text lane's token structure — shapes, never verdicts. Saves the raw
response to artifacts/probe_<variant>_<ts>.json. Exit 0 on 2xx.

Usage:
  META_API_KEY=... python3 scripts/probe_sam.py --variant A --image-url URL
  META_API_KEY=... python3 scripts/probe_sam.py --variant B --image assets/probe_kettle.jpg

Variants:
  A  input_image with a fetchable image_url
  B  input_image with a base64 data URL

The facts this probe tests are written down in
docs/sam-3.1-call-shape.md (read it first — that is the invariant).
Stdlib only.
"""
import argparse
import base64
import json
import os
import sys
import time
import urllib.request

API = "https://api.meta.ai/v1/responses"
PHRASE = "gooseneck kettle"


def shape_walk(obj, depth=0, max_depth=4):
    pad = "  " * depth
    if isinstance(obj, dict):
        print(f"{pad}object keys={sorted(obj.keys())}")
        if depth < max_depth:
            for k in sorted(obj.keys()):
                print(f"{pad} {k}:")
                shape_walk(obj[k], depth + 1, max_depth)
    elif isinstance(obj, list):
        print(f"{pad}list len={len(obj)}")
        if obj and depth < max_depth:
            shape_walk(obj[0], depth + 1, max_depth)
    elif isinstance(obj, str):
        print(f"{pad}str len={len(obj)}")
    else:
        print(f"{pad}{type(obj).__name__}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", choices=["A", "B"], required=True)
    ap.add_argument("--image-url", default=None)
    ap.add_argument("--image", default=None)
    ap.add_argument("--phrase", default=PHRASE)
    args = ap.parse_args()

    key = os.environ.get("META_API_KEY")
    if not key:
        print("META_API_KEY is not set", file=sys.stderr)
        return 2

    if args.variant == "A":
        if not args.image_url:
            print("variant A needs --image-url", file=sys.stderr)
            return 2
        image_part = {"type": "input_image", "image_url": args.image_url}
    else:
        if not args.image:
            print("variant B needs --image", file=sys.stderr)
            return 2
        with open(args.image, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        image_part = {
            "type": "input_image",
            "image_url": f"data:image/jpeg;base64,{b64}",
        }

    body = {
        "model": "sam-3.1",
        "input": [{
            "type": "message", "role": "user",
            "content": [
                {"type": "input_text", "text": args.phrase},
                image_part,
            ],
        }],
        "stream": True,
        "metadata": {"include_confidence": "true"},
    }
    req = urllib.request.Request(API, method="POST")
    req.add_header("Authorization", f"Bearer {key}")
    req.add_header("Content-Type", "application/json")
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    artifact = {"variant": args.variant, "phrase": args.phrase,
                "request_meta": {"model": "sam-3.1", "stream": True}}

    try:
        with urllib.request.urlopen(
            req, data=json.dumps(body).encode(), timeout=180
        ) as resp:
            status = resp.status
            raw = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        status = e.code
        raw = e.read().decode("utf-8", "replace")
        artifact["error_body"] = raw[:20000]
        os.makedirs("artifacts", exist_ok=True)
        path = f"artifacts/probe_{args.variant}_{ts}.json"
        with open(path, "w") as f:
            json.dump(artifact, f, indent=2)
        print(f"HTTP {status} (error) — artifact: {path}")
        print(raw[:2000])
        return 1

    artifact["raw_stream"] = raw[:200000]
    os.makedirs("artifacts", exist_ok=True)
    path = f"artifacts/probe_{args.variant}_{ts}.json"
    with open(path, "w") as f:
        json.dump(artifact, f, indent=2)

    print(f"HTTP {status} — artifact: {path}")
    events = []
    text_parts = []
    for line in raw.splitlines():
        if line.startswith("data:"):
            try:
                ev = json.loads(line[5:].strip())
            except ValueError:
                continue
            events.append(ev)
            if ev.get("type") == "response.output_text.delta":
                text_parts.append(ev.get("delta", ""))
            if ev.get("type") == "response.output_text.done":
                text_parts = [ev.get("text", "")]
    print(f"stream events: {len(events)}")
    seen = {}
    for ev in events:
        seen[ev.get("type")] = seen.get(ev.get("type"), 0) + 1
    print("event types:", json.dumps(seen, indent=2))
    if events:
        print("first event shape:")
        shape_walk(events[0])
    text = "".join(text_parts)
    print(f"output_text chars: {len(text)}")
    if text:
        first = text.splitlines()[0]
        print(f"first line chars: {len(first)}")
        print("first line token counts:",
              {"box": first.count("<|box;"), "mask": first.count("<|mask;")})
    return 0


if __name__ == "__main__":
    sys.exit(main())
