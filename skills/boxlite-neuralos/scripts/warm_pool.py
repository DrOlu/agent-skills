#!/usr/bin/env python3
"""Warm-pool manager for BoxLite — keep N clones of a template ready.

usage: warm_pool.py --template neuralos-template [--size 3] [--prefix job]
                    [--serve-url http://localhost:8100 --api-key KEY]
Dispenses a warm box (prints its name), refills the pool. Boxes are CoW
clones — near-instant, and share the template's base disk.
"""
import argparse
import asyncio
import json
import time

import boxlite


async def pool(rt, template, prefix, size):
    boxes = await rt.list_info()
    by_name = {getattr(b, "name", ""): b for b in boxes}
    warm = [n for n in sorted(by_name)
            if n.startswith(prefix + "-") and
            (by_name[n].status if isinstance(by_name[n].status, str)
             else getattr(by_name[n], "state", "")) in ("stopped", "standby",
                                                        "") or True]
    return [n for n in warm]


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", default="neuralos-template")
    ap.add_argument("--size", type=int, default=3)
    ap.add_argument("--prefix", default="job")
    ap.add_argument("--serve-url", help="drive a remote boxlite serve")
    ap.add_argument("--api-key")
    ap.add_argument("--dispense", action="store_true",
                    help="print the name of one warm box and keep it running")
    a = ap.parse_args()

    if a.serve_url:
        rt = boxlite.Boxlite.rest(boxlite.BoxliteRestOptions(
            url=a.serve_url,
            credential=boxlite.ApiKeyCredential(a.api_key) if a.api_key else None))
    else:
        rt = boxlite.Boxlite.default()

    infos = await rt.list_info()
    names = [getattr(i, "name", "") for i in infos]
    pool_boxes = sorted(n for n in names if n.startswith(a.prefix + "-"))

    if a.dispense:
        if pool_boxes:
            print(pool_boxes[0])
            return
        box = await rt.get_or_create(
            boxlite.BoxOptions(image="python:3.12-slim", auto_delete=0),
            name=f"{a.prefix}-{int(time.time())}")
        print(box.id if not isinstance(box, tuple) else box[0].id)
        return

    # refill: clone the template until we have --size warm clones
    tpl = await rt.get(a.template)
    missing = a.size - len(pool_boxes)
    for i in range(max(0, missing)):
        nm = f"{a.prefix}-{int(time.time())}-{i}"
        await tpl.clone_box(name=nm)
        print(f"[pool] cloned -> {nm}")
    print(f"[pool] {len(pool_boxes) + max(0, missing)} warm boxes ready "
          f"(template: {a.template})")


if __name__ == "__main__":
    asyncio.run(main())
