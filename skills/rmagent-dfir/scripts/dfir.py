#!/usr/bin/env python3
"""
dfir.py — the rmagent-dfir command line. Pull-based, on-device, read-only.

  ask      Run ONE allowlisted DFIR question on a witness.
  sweep    Run every allowlisted DFIR question; chain + record each answer.
  collect  Chunked, SHA256-hashed, read-only acquisition of one file.
  hash     Hash a semicolon-separated list of files on a witness.
  scope    Ask Jev which collection to run next for a finding.
  timeline Build the super-timeline from a case directory.
  chain    Print / verify the case's chain-of-custody journal.
  report   Generate an IR report skeleton from a case directory.

Examples:
  dfir.py ask  --inventory estate.yaml --witness ws1 --question vol --case cases/ir-001
  dfir.py sweep --inventory estate.yaml --witness ws1 --case cases/ir-001
  dfir.py collect --inventory estate.yaml --witness ws1 --path "C:\\Users\\x\\s.exe" --case cases/ir-001
  dfir.py scope --finding "new local admin + scheduled task on ws1" --case cases/ir-001

Non-negotiables enforced here: pull-only (nothing is ever written to the
witness), allowlisted questions, capped answers, witness paths validated
against injection, every acquisition hashed and chained.
"""
from __future__ import annotations
import argparse, base64, hashlib, json, os, re, subprocess, sys, time
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))
import lib  # the dfir grain wrapper over rmagent-core

WIN_PATH = re.compile(r"^[A-Za-z]:\\[^<>:\"/|?\x00-\x1f]*$")
JUNK_TOKENS = {"FRAGMENT", "FRAGMENT:", "ok", "extract", "tool"}
DFIR_QUESTIONS = ["vol", "conn", "persist", "logtriage", "exfil", "usn", "procrun",
                  "recyclebin", "browser", "email", "appcompat", "amcpull", "usbhist",
                  "livewindow"]


def out_json(o):
    print(json.dumps(o, indent=2, default=str))


def load_inv(path):
    import yaml
    return yaml.safe_load(open(path))


def witness(inv, wid):
    for w in inv.get("witnesses", []):
        if w.get("id") == wid:
            return w
    print(f"witness not in inventory: {wid}", file=sys.stderr)
    sys.exit(2)


def chain_record(case: Path, kind: str, **kw):
    # callers may pass sha256=<artifact digest> — renamed before the
    # integrity hash so verification can reproduce the line exactly.
    if "sha256" in kw:
        kw["digest_sha256"] = kw.pop("sha256")
    entry = {"t": __import__("time").strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
             "operator": os.environ.get("USERNAME") or os.environ.get("USER") or "jump-host",
             "kind": kind, **kw}
    line = json.dumps(entry, sort_keys=True)
    entry["sha256"] = hashlib.sha256(line.encode()).hexdigest()
    with open(case / "chain.jsonl", "a") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")
    return entry


def valid_windows_path(p: str) -> bool:
    return bool(WIN_PATH.match(p)) and len(p) <= 260 and ";" not in p and "`" not in p and "$" not in p and "&" not in p and "'" not in p


# ---------------------------------------------------------------- commands
def cmd_ask(a):
    inv = load_inv(a.inventory)
    row = witness(inv, a.witness)
    to = 45 if a.question == "livewindow" else 25
    r = lib.ask(row, a.question, since_hours=a.since, limit=a.limit, timeout=to)
    if a.case:
        cdir = Path(a.case); (cdir / "answers").mkdir(parents=True, exist_ok=True)
        with open(cdir / "answers" / f"{a.witness}__{a.question}.json", "w") as f:
            json.dump(r.get("data", r), f, indent=1, default=str)
        chain_record(cdir, "collect", witness=a.witness, question=a.question,
                     sha256=hashlib.sha256(json.dumps(r.get("data", r), sort_keys=True, default=str).encode()).hexdigest(),
                     answer_file=f"answers/{a.witness}__{a.question}.json")
    out_json(r.get("data", r))


def cmd_sweep(a):
    inv = load_inv(a.inventory)
    row = witness(inv, a.witness)
    cdir = Path(a.case); (cdir / "answers").mkdir(parents=True, exist_ok=True)
    results = {}
    for q in DFIR_QUESTIONS:
        to = 45 if q == "livewindow" else 25
        r = lib.ask(row, q, since_hours=a.since, limit=a.limit, timeout=to)
        ok = bool(r.get("ok"))
        results[q] = "ok" if ok else f"hole: {str(r.get('error') or r.get('hole', {}).get('why', ''))[:80]}"
        with open(cdir / "answers" / f"{a.witness}__{q}.json", "w") as f:
            json.dump(r.get("data", r), f, indent=1, default=str)
        chain_record(cdir, "collect", witness=a.witness, question=q,
                     sha256=hashlib.sha256(json.dumps(r.get("data", r), sort_keys=True, default=str).encode()).hexdigest(),
                     answer_file=f"answers/{a.witness}__{q}.json")
        print(f"  {a.witness}  {q}: {results[q]}")
    print(f"[sweep] {sum(1 for v in results.values() if v == 'ok')}/{len(DFIR_QUESTIONS)} questions answered — case {cdir}")


def cmd_collect(a):
    # zsh double quotes do not collapse \\\\ before ordinary chars — normalize
    a.path = re.sub(r"\\\\{2,}", "\\\\", a.path)
    inv = load_inv(a.inventory)
    row = witness(inv, a.witness)
    if not valid_windows_path(a.path):
        print("rejected: path fails validation (drive-absolute, no metacharacters)", file=sys.stderr)
        sys.exit(2)
    creds = lib.creds_for(row) if hasattr(lib, "creds_for") else None
    import winrm
    endpoint = row.get("endpoint") or f"http://{row['address']}:5985/wsman"
    sess = winrm.Session(endpoint, auth=(creds["user"], creds["password"]),
                         transport=row.get("transport") or "ntlm")
    payload = (SKILL_DIR / "scripts" / "questions" / "windows" / "ircollect.ps1").read_text()
    # param() must be the first statement in a PowerShell script — strip it and
    # set the variables first instead.
    payload = "\n".join(l for l in payload.splitlines() if not l.startswith("param("))
    cdir = Path(a.case); (cdir / "collected").mkdir(parents=True, exist_ok=True)
    fname = os.path.basename(a.path.replace("\\", "/"))
    body = b""
    meta = None
    chunk = a.chunk
    while True:
        qpath = a.path.replace("'", "''")
        setup = f"$Path = '{qpath}'; $Chunk = {chunk}; $ChunkSize = 24576" + chr(10)
        code = setup + payload
        r = sess.run_ps(code)
        if r.status_code != 0:
            print('STATUS', r.status_code, file=sys.stderr)
            print('STDOUT:', r.std_out.decode(errors='replace')[:600], file=sys.stderr)
            print('STDERR:', r.std_err.decode(errors='replace')[:600], file=sys.stderr)
            sys.exit(1)
        _out = r.std_out.decode(errors="replace")
        d = json.loads(_out[_out.index("{"):_out.rindex("}") + 1])
        if not d.get("ok"):
            print("witness refused:", d.get("error"), file=sys.stderr); sys.exit(1)
        meta = d
        body += base64.b64decode(d["data"])
        if hashlib.sha256(base64.b64decode(d["data"])).hexdigest() != d["sha256_chunk"]:
            print(f"chunk {chunk} hash mismatch — acquisition aborted, nothing trusted", file=sys.stderr)
            sys.exit(1)
        chunk += 1
        if chunk >= d["chunks"]:
            break
    fsha = hashlib.sha256(body).hexdigest()
    if fsha != meta["sha256_file"]:
        print("FULL-FILE hash mismatch — acquisition aborted, nothing trusted", file=sys.stderr)
        sys.exit(1)
    out = cdir / "collected" / f"{a.witness}__{fname}"
    out.write_bytes(body)
    receipt = {"witness": a.witness, "path": a.path, "size": meta["size"], "chunks": meta["chunks"],
               "sha256_file": meta["sha256_file"], "local_copy": str(out), "mtime_utc": meta["mtime"]}
    (cdir / "collected" / f"{a.witness}__{fname}.receipt.json").write_text(json.dumps(receipt, indent=1))
    chain_record(cdir, "acquire", witness=a.witness, path=a.path,
                 sha256=meta["sha256_file"], size=meta["size"], chunks=meta["chunks"])
    print(json.dumps(receipt, indent=1))


def cmd_hash(a):
    a.paths = re.sub(r"\\\\{2,}", "\\\\", a.paths)
    inv = load_inv(a.inventory)
    row = witness(inv, a.witness)
    if ";" in a.paths and any(not valid_windows_path(p) for p in a.paths.split(";") if p.strip()):
        print("rejected: a path fails validation", file=sys.stderr); sys.exit(2)
    creds = lib.creds_for(row) if hasattr(lib, "creds_for") else None
    import winrm
    endpoint = row.get("endpoint") or f"http://{row['address']}:5985/wsman"
    sess = winrm.Session(endpoint, auth=(creds["user"], creds["password"]),
                         transport=row.get("transport") or "ntlm")
    payload = (SKILL_DIR / "scripts" / "questions" / "windows" / "irhash.ps1").read_text()
    qlist = a.paths.replace("'", "''")
    setup = f"$List = '{qlist}'" + chr(10)
    code = setup + payload
    r = sess.run_ps(code)
    if r.status_code != 0:
        print(r.std_err.decode()[:400], file=sys.stderr); sys.exit(1)
    _out = r.std_out.decode()
    d = json.loads(_out[_out.index("{"):_out.rindex("}")+1])
    cdir = Path(a.case) if a.case else None
    if cdir:
        (cdir / "collected").mkdir(parents=True, exist_ok=True)
        (cdir / "collected" / f"{a.witness}__hashes.json").write_text(json.dumps(d, indent=1))
        for f in d.get("files", []):
            if f.get("sha256"):
                chain_record(cdir, "hash", witness=a.witness, path=f["path"], sha256=f["sha256"])
    out_json(d)


def cmd_scope(a):
    args = [sys.executable, str(SKILL_DIR / "scripts" / "laya_decide.py"), "collect_scope",
            "--state", a.finding + (f" Case dir: {a.case}." if a.case else "")]
    if a.raw:
        args.append("--raw")
    r = subprocess.run(args, capture_output=True, text=True)
    sys.stdout.write(r.stdout or r.stderr)
    sys.exit(r.returncode)


def cmd_timeline(a):
    sys.path.insert(0, str(SKILL_DIR / "scripts"))
    import timeline
    rows = timeline.build(Path(a.case), out=a.out)
    print(f"[timeline] {len(rows)} records written")


def cmd_chain(a):
    cdir = Path(a.case)
    p = cdir / "chain.jsonl"
    if a.verify:
        ok, n, bad = verify_chain(p)
        print(f"chain: {n} entries — {'VERIFIED (all hashes intact)' if ok else 'CORRUPT: ' + ', '.join(bad)}")
        sys.exit(0 if ok else 1)
    if not p.exists():
        print("(empty chain)"); return
    for line in open(p):
        e = json.loads(line)
        print(f"  {e['t']}  {e['kind']:8}  {e.get('witness','')}  {e.get('question') or e.get('path') or e.get('file','')}  {e['sha256'][:12]}")


def cmd_report(a):
    sys.path.insert(0, str(SKILL_DIR / "scripts"))
    import report
    report.generate(Path(a.case))


def verify_chain(p: Path):
    if not p.exists():
        return True, 0, []
    n, bad = 0, []
    for line in open(p):
        e = json.loads(line)
        h = e.pop("sha256", None)
        n += 1
        if hashlib.sha256(json.dumps(e, sort_keys=True).encode()).hexdigest() != h:
            bad.append(f"entry {n}")
    return not bad, n, bad


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    def common(p, case=True):
        p.add_argument("--inventory", required=True)
        p.add_argument("--witness", required=True)
        if case:
            p.add_argument("--case", default="cases/ir")
    p1 = sub.add_parser("ask"); common(p1)
    p1.add_argument("--question", required=True, choices=DFIR_QUESTIONS)
    p1.add_argument("--since", type=float, default=24.0)
    p1.add_argument("--limit", type=int, default=50)
    p2 = sub.add_parser("sweep"); common(p2)
    p2.add_argument("--since", type=float, default=24.0)
    p2.add_argument("--limit", type=int, default=50)
    p3 = sub.add_parser("collect"); common(p3)
    p3.add_argument("--path", required=True)
    p3.add_argument("--chunk", type=int, default=0)
    p4 = sub.add_parser("hash"); common(p4)
    p4.add_argument("--paths", required=True, help="semicolon-separated file list")
    p5 = sub.add_parser("scope"); p5.add_argument("--finding", required=True)
    p5.add_argument("--case", default="cases/ir"); p5.add_argument("--raw", action="store_true")
    p6 = sub.add_parser("timeline"); p6.add_argument("--case", required=True)
    p6.add_argument("--out", default=None)
    p7 = sub.add_parser("chain"); p7.add_argument("--case", required=True)
    p7.add_argument("--verify", action="store_true")
    p8 = sub.add_parser("report"); p8.add_argument("--case", required=True)
    a = ap.parse_args()
    {"ask": cmd_ask, "sweep": cmd_sweep, "collect": cmd_collect, "hash": cmd_hash,
     "scope": cmd_scope, "timeline": cmd_timeline, "chain": cmd_chain, "report": cmd_report}[a.cmd](a)


if __name__ == "__main__":
    main()
