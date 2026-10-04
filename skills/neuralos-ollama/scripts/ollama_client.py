#!/usr/bin/env python3
"""Shared Ollama client for neuralOS-ollama.

Contract:
- think is DISABLED by default (pass think=True only deliberately)
- format/schema calls are guaranteed-valid JSON by construction
- models that reject the think flag (HTTP 400) are retried without it
"""
import json
import os
import time
import urllib.error
import urllib.request

OLLAMA_URL = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
DEFAULT_MODEL = os.environ.get("NEURALOS_OLLAMA_MODEL", "qwen3.5:9b")


def _post(url, payload, timeout):
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body,
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode()), time.time() - t0


def chat(model=None, messages=None, schema=None, temperature=0,
         num_predict=None, think=False, seed=None, timeout=300):
    """POST /api/chat with think disabled. schema (JSON schema dict) turns on
    Ollama structured outputs (grammar-constrained)."""
    payload = {"model": model or DEFAULT_MODEL,
               "messages": messages or [],
               "stream": False,
               "think": bool(think),
               "options": {"temperature": temperature}}
    if schema is not None:
        payload["format"] = schema
    if num_predict:
        payload["options"]["num_predict"] = num_predict
    if seed is not None:
        payload["options"]["seed"] = seed
    try:
        return _post(f"{OLLAMA_URL}/api/chat", payload, timeout)
    except urllib.error.HTTPError as e:
        if e.code == 400 and "think" in payload:
            # model template rejects the flag (e.g. some r1 distills)
            payload.pop("think")
            return _post(f"{OLLAMA_URL}/api/chat", payload, timeout)
        raise


def constrained_pick(question, candidates, descriptions=None,
                     arg_properties=None, model=None, timeout=300):
    """Grammar-constrained tool pick. candidates: list of probe names.
    Returns (pick_dict, wall_seconds). pick_dict always contains 'probe';
    'none_of_these' means the model found no fitting candidate — treat as
    an honest refusal and log it to the gap queue."""
    candidates = list(candidates) + ["none_of_these"]
    props = {"probe": {"type": "string", "enum": candidates}}
    for k, spec in (arg_properties or {}).items():
        props[k] = spec
    schema = {"type": "object", "properties": props,
              "required": ["probe"]}
    lines = [f"- {n}: {(descriptions or {}).get(n, '')}".rstrip()
             for n in candidates if n != "none_of_these"]
    lines.append("- none_of_these: pick when no tool truly answers the question")
    system = ("You route questions to the right tool. Tools:\n"
              + "\n".join(lines)
              + "\nFill any arguments the question provides. If no tool truly "
                "fits, pick none_of_these. Respond with JSON only.")
    out, wall = chat(model=model,
                     messages=[{"role": "system", "content": system},
                               {"role": "user", "content": question}],
                     schema=schema, timeout=timeout)
    try:
        return json.loads(out["message"]["content"]), wall
    except (KeyError, json.JSONDecodeError):
        return {"probe": "none_of_these", "_unparseable": True}, wall


def generate(model=None, prompt=None, num_predict=512, think=False,
             temperature=0, timeout=600):
    """Plain text generation via /api/chat (think disabled by default)."""
    out, wall = chat(model=model,
                     messages=[{"role": "user", "content": prompt or ""}],
                     num_predict=num_predict, think=think,
                     temperature=temperature, timeout=timeout)
    return out.get("message", {}).get("content", ""), wall
