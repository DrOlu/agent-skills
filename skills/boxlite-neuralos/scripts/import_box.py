#!/usr/bin/env python3
"""Import a .boxlite archive as a named box (portability, no registry).

usage: import_box.py --archive ~/archives/tpl.boxlite --name neuralos-template
"""
import argparse
import asyncio

import boxlite


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--archive", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--untrusted", action="store_true")
    a = ap.parse_args()

    rt = boxlite.Boxlite.default()
    got = await rt.import_box(a.archive, name=a.name, untrusted=a.untrusted)
    box = got[0] if isinstance(got, tuple) else got
    print(f"[import] {a.archive} -> box '{a.name}' (id {box.id})")


if __name__ == "__main__":
    asyncio.run(main())
