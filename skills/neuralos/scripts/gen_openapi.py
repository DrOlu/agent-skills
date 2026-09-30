#!/usr/bin/env python3
"""OpenAPI + MCP generation from needle_menu.json.

Every probe becomes a typed operation — so ANY agent runtime (Claude, Cursor,
MCP hosts, OpenAPI clients) can call the instance's probes directly without
the 121M selector.

usage: gen_openapi.py <needle_menu.json> [--agent NAME] [--title T]
writes: openapi.json, mcp.json
"""
import argparse
import json
import sys


def param_schema(spec):
    """Menu param spec -> JSON-schema-ish param spec."""
    out = {"type": spec.get("type", "string")}
    for k in ("enum", "pattern", "minimum", "maximum", "description"):
        if k in spec:
            out[k] = spec[k]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("menu")
    ap.add_argument("--agent", default="neuralos-instance")
    ap.add_argument("--title", default=None)
    a = ap.parse_args()

    menu = json.load(open(a.menu, encoding="utf-8"))
    title = a.title or f"{a.agent} — neuralOS probes"

    paths = {}
    tools = []
    for probe in menu:
        name = probe["name"]
        params = probe.get("parameters") or {}
        props = params.get("properties") or {}
        required = params.get("required") or []
        paths[f"/probes/{name}"] = {
            "post": {
                "operationId": name,
                "summary": probe.get("description", name),
                "tags": ["probes"],
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {
                        "schema": {
                            "type": "object",
                            "properties": {k: param_schema(v) for k, v in props.items()},
                            **({"required": required} if required else {}),
                        }}}},
                "responses": {"200": {"description": "probe result envelope"}}}}
        tools.append({"name": name,
                      "description": probe.get("description", name),
                      "inputSchema": {
                          "type": "object",
                          "properties": {k: param_schema(v) for k, v in props.items()},
                          **({"required": required} if required else {})}})

    openapi = {
        "openapi": "3.1.0",
        "info": {"title": title, "version": "1.0.0",
                 "description": f"{len(menu)} neuralOS probes as typed operations "
                                f"(generated from needle_menu.json)"},
        "paths": paths,
    }
    mcp = {"mcp_version": "1.0", "server": {"name": a.agent},
           "tools": tools}

    json.dump(openapi, open("openapi.json", "w"), indent=2, ensure_ascii=False)
    json.dump(mcp, open("mcp.json", "w"), indent=2, ensure_ascii=False)
    print(f"wrote openapi.json ({len(paths)} operations) and "
          f"mcp.json ({len(tools)} tools)")


if __name__ == "__main__":
    main()
