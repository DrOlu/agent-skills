# rmagent-dfir — worked examples

Real commands, real shapes of output. Estate: ws1 = 44.197.31.152 (AWS
Windows Server 2022, WinRM NTLM, creds from the scrt store).

## Scenario 1 — full sweep after a suspicious finding

Input (the operator was told sketch saw a new admin):
```bash
python3 scripts/dfir.py sweep --inventory estate.yaml --witness ws1 \
  --since 24 --case cases/ir-042
```
Output:
```
  ws1  vol: ok
  ws1  conn: ok
  ws1  persist: ok
  ws1  logtriage: ok
  ws1  usn: ok
  ws1  appcompat: ok
  ws1  usbhist: ok
[sweep] 7/7 questions answered — case cases/ir-042
```
Each answer lands in `cases/ir-042/answers/ws1__<question>.json`, and each
collection is appended to `cases/ir-042/chain.jsonl`.

Sample `ws1__vol.json` (trimmed):
```json
{ "skill": "vol", "host": "EC2AMAZ-8NK9FUP", "count": 84,
  "lsass_foreign_modules": 0,
  "suspicious": [ { "pid": 6012, "name": "s.exe",
    "path": "C:\\Users\\svc\\AppData\\Roaming\\s.exe",
    "why": "orphan+user-writable-path", "cmd": "s.exe -b 203.0.113.7:443" } ] }
```

## Scenario 2 — Laya routes the next collection

```bash
python3 scripts/dfir.py scope --case cases/ir-042 \
  --finding "FINDING: orphaned s.exe from AppData with cmd 's.exe -b 203.0.113.7:443'.
COLLECTED SO FAR: vol (orphan process found), conn (established connection to
203.0.113.7:443 owned by s.exe), persist (no drill artifacts), logtriage
(4625 spike from 203.0.113.7), usn (s.exe created 02:14 in Roaming).
HOST CONTEXT: single AWS server, internet-exposed, payment-adjacent."
```
Output:
```
matrix: collect_scope  model: laya-local
  next_collection: ircollect   confidence: 0.86
  full_acquisition: 0.71
  severity: 2                  confidence: 0.91
policy gate (next_collection): ircollect — acquire the binary.
```
Volatility order held: live state first, and now the specific file.

## Scenario 3 — hashed, chunked acquisition

```bash
python3 scripts/dfir.py collect --inventory estate.yaml --witness ws1 \
  --path "C:\\Users\\svc\\AppData\\Roaming\\s.exe" --case cases/ir-042
```
Output:
```json
{ "witness": "ws1", "path": "C:\\Users\\svc\\AppData\\Roaming\\s.exe",
  "size": 18432, "chunks": 1,
  "sha256_file": "9f2b…c41d", "local_copy": "cases/ir-042/collected/ws1__s.exe",
  "mtime_utc": "2026-09-19T02:14:11Z" }
```
Receipt written beside the binary; chain entry appended:
```
  2026-…Z  acquire   ws1  C:\Users\svc\AppData\Roaming\s.exe  9f2b…c41d
```
A path like `C:\x; calc.exe` never reaches the witness:
```
rejected: path fails validation (drive-absolute, no metacharacters)
```

## Scenario 4 — timeline + report

```bash
python3 scripts/dfir.py timeline --case cases/ir-042
python3 scripts/dfir.py report  --case cases/ir-042
```
`timeline.jsonl` (sorted):
```json
{"ts": "2026-09-19T02:14:11Z", "source": "acquired", "kind": "file", "text": "C:\\Users\\svc\\AppData\\Roaming\\s.exe sha256=9f2b…c41d"}
{"ts": "2026-09-19T09:30:00Z", "source": "answer:ws1__logtriage", "kind": "7045", "text": "name=DrillSvc"}
{"ts": "2026-09-19T09:59:00Z", "source": "answer:ws1__vol", "kind": "vol", "text": "pid=1 name=evil.exe"}
```
`IR_REPORT.md` opens with:
```
## Chain of custody
- 9 chained actions — **VERIFIED, hashes intact**
- Court-ready
```
…and closes with the holes and the open actions.

## Scenario 5 — chain tamper test (why the chain matters)

Edit one byte of one journal entry, then:
```bash
python3 scripts/dfir.py chain --case cases/ir-042 --verify
```
Output:
```
chain: 9 entries — CORRUPT: entry 4
```
By policy the case is no longer court-ready. Nothing silent.

## Scenario 6 — offline judgment (air-gapped estate)

No OpenRouter reachable — every example above still runs, because the
decision tier is Laya (421M, offline) and extraction is needle (offline).
Only `scope`-style judgments carry an honest lower confidence; the matrices
flag ESCALATE below 0.5 and the operator reads IR_REPORT.md regardless.

## Scenario 7 — exfiltration surface (`exfil`)

A user is suspected of staging files before resignation:
```bash
python3 scripts/dfir.py ask --inventory estate.yaml --witness ws2 \
  --question exfil --since 336 --case cases/ir-043
```
Returns, within the 336-hour window: every zip/7z/rar/tar/gz under Desktop/
Documents/Downloads with size + mtime, cloud-sync roots present per user
(OneDrive/Dropbox/Google Drive/pCloud/Box with shallow item counts), SMB
sessions with client + user + open-file counts, and the last RDP connect/
disconnect events. On a server with no interactive users this returns mostly
empty lists — that is a clean answer, not a hole (the SMB section still speaks).

## Scenario 8 — browser deep-dive (discovery on-box, parsing OFFLINE)

```bash
python3 scripts/dfir.py ask --inventory estate.yaml --witness ws1 --question browser --case cases/ir-044
# → which browsers/profiles exist, with History/Bookmarks/Web Data sizes + mtimes
python3 scripts/dfir.py collect --inventory estate.yaml --witness ws1 \
  --path "C:\\Users\\a\\AppData\\Local\\Google\\Chrome\\User Data\\Default\\History" --case cases/ir-044
python3 scripts/browser_parse.py cases/ir-044/collected/ws1__History --out cases/ir-044/browser.json
```
The witness only ever answers "what exists". Top-300 URLs + downloads are
parsed from the hashed copy on the jump host (`mode=ro&immutable=1` — frozen
evidence, no journal replay). Firefox `places.sqlite` is auto-detected by name.

## Scenario 9 — deleted evidence (`recyclebin`, `procrun`, `amcpull`)

```bash
python3 scripts/dfir.py ask --inventory estate.yaml --witness ws2 --question recyclebin --case cases/ir-045
# → $I records parsed on-box: original path, size, deletion time (UTC), per SID
python3 scripts/dfir.py ask --inventory estate.yaml --witness ws2 --question procrun --case cases/ir-045
# → most-recent Prefetch runs; certutil/bitsadmin/mshta/... flagged as lolbin
python3 scripts/dfir.py ask --inventory estate.yaml --witness ws2 --question amcpull --case cases/ir-045
# → Amcache.hve size/mtime/SHA256/readability — the pull decision is the operator's
python3 scripts/dfir.py collect --inventory estate.yaml --witness ws2 \
  --path "C:\\Windows\\appcompat\\Programs\\Amcache.hve" --case cases/ir-045
python3 scripts/amcache_parse.py cases/ir-045/collected/ws2__Amcache.hve --out cases/ir-045/amcache.json
# → InventoryApplicationFile entries (path/publisher/version) + FileOrKey first-run times
```
An empty Prefetch dir on a workstation is itself reported as a signal; an
unknown Amcache `f`-value layout yields version + embedded strings — holes,
never guessed fields.

## Scenario 10 — the live window (`livewindow`)

A cradle ran and died between sweeps — the Security log never saw it. Open a
15-second live tap on the PowerShell provider and catch the next one:
```bash
python3 scripts/dfir.py ask --inventory estate.yaml --witness ws1 \
  --question livewindow --case cases/ir-046
```
Output, in one answer:
- `events_seen` / `events` — every PowerShell-provider event during the 15s
  window (id, time, level, capped message), each flagged when its message
  matches a hunt pattern (`iex`, `downloadstring`, `-enc`, `frombase64`,
  `net.webclient`, …)
- `carve_out` — the write carve-out, disclosed in-band: the temp `.etl` path,
  bytes written, whether the file was removed, whether the trace session
  stopped cleanly, and how many stale `rwLW*` sessions were reaped first

```
carve_out: { temp_file: C:\Users\A~\AppData\Local\Temp\rwLW9f3c1a.etl,
             bytes_written: 1163264, removed: true, session_stopped: true, stale_stopped: 0 }
carve_note: WRITE CARVE-OUT: one .etl trace file in $env:TEMP during a 15s
            window, then deleted; trace session stopped in-band; ...
```

This is the ONE question in the family that writes anything to the witness —
a single self-cleaning temp file, bounded by the ask itself, disclosed in the
answer, and enforced by the test suite. If `removed` is false, treat it as a
hole and go collect the file by hand. Re-run it in a sweep and it runs last:
by the time the sweep reaches it, anything that tripped during collection
walks right into the window.

## What this skill will NOT do

- Write to, clean, or quarantine anything on the witness (that's
  rmagent-actuate, with its own gates).
- Acquire full memory (no agent, no driver — `vol` gives indicators).
- Answer unlisted questions, accept unvalidated paths, or trust an unhashed
  artifact. Holes instead of guesses — always.
