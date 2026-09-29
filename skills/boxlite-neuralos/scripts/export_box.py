#!/usr/bin/env python3
"""Export a BoxLite box to a portable .boxlite archive (no registry needed).

usage: export_box.py --name neuralos-template --dest ~/archives/tpl.boxlite
"""
import argparse
import asyncio

import boxlite


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--dest", required=True)
    a = ap.parse_args()

    rt = boxlite.Boxlite.default()
    box = await rt.get(a.name)
    await box.export(dest=a.dest)
    import os
    size = os.path.getsize(a.dest) if os.path.exists(a.dest) else -1
    print(f"[export] {a.name} -> {a.dest} ({size/1e6:.1f} MB)")
    print("import elsewhere with: import_box.py --archive <file> --name <name>")


if __name__ == "__main__":
    asyncio.run(main())
