#!/usr/bin/env python3
"""Keeper: hold a BoxLite box up (mechanism 1 of 3).

BoxLite auto-stops non-detached boxes when the owning client exits. This
holder keeps one up. NOTE: it holds the runtime lock on BOXLITE_HOME, so no
other SDK process can use the same home until this exits — prefer
detach=True (creation-time) or `boxlite serve` for multi-client setups.

usage: keeper.py [--box chinook-1gb] [--stop-file ~/boxlite-lab/keeper.stop]
Run under nohup; create the stop file to shut the box down and exit.
"""
import argparse
import asyncio
import os
import time

import boxlite


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--box", default="chinook-1gb")
    ap.add_argument("--stop-file", default=os.path.expanduser("~/boxlite-lab/keeper.stop"))
    ap.add_argument("--poll", type=int, default=5, help="stop-file check interval (s)")
    ap.add_argument("--log-every", type=int, default=600, help="keepalive log interval (s)")
    a = ap.parse_args()

    rt = boxlite.Boxlite.default()
    box = await rt.get(a.box)
    await box.start()
    print(f"[keeper] {a.box} up — holding. Create {a.stop_file} to stop.", flush=True)

    last_log = time.time()
    try:
        while True:
            if os.path.exists(a.stop_file):
                print("[keeper] stop file found — shutting box down.", flush=True)
                os.remove(a.stop_file)
                await box.stop()
                print("[keeper] box stopped; keeper exiting.", flush=True)
                return
            if time.time() - last_log >= a.log_every:
                print(f"[keeper] alive {time.strftime('%H:%M:%S')}", flush=True)
                last_log = time.time()
            await asyncio.sleep(a.poll)
    finally:
        print("[keeper] exiting.", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
