# rmagent-iso worked examples

These use the **fixture rings**, not a live SPAN. Same questions, same JSON
shape as production.

```bash
cd /Users/olu/.agents/skills/rmagent-iso/scripts
python3 generate_fixture.py --out ../examples/rings
```

Fixture incidents:

| STAN | RRN | What |
|---|---|---|
| 123456 | 123456789012 | Slow Finacle (~2.4 s on D), RC=00, **no EJ** → DWD candidate |
| 654321 | 654321000001 | Timeout: 0200 on both taps, no 0210. `last_seen=cba_0200` |
| 111222 | 111222000051 | Decline RC=51, hops complete |
| 100000–100039 | … | 40 healthy withdrawals with EJ completion (baseline n≥30) |

PAN packed in the lab is `5060990012345678`. It **must not** appear in any ring
or answer — only `506099******5678`.

---

## 0. Can the taps see? (`txnattest`)

```bash
python3 hunt.py attest --rings ../examples/rings
```

Expect `blind_check: "ok"` on `tap-fep-acq` and `tap-fep-cba`. If either is
`BLIND`, do not trust `txnslow` / `txnfail` emptiness.

Standing rule (same as rmagent-so): **empty is not clean while blind.**

---

## 1. “Was the delay at the ATM, the switch, or Finacle?”

Ticket: customer waited ~3 s at ATM00001, cash eventually? disputed.

```bash
python3 hunt.py hops --rings ../examples/rings --stan 123456 --rrn 123456789012
```

What you should see:

- `B_req.ms` ≈ 25 ms — Postilion inbound is fine
- `D.ms` ≈ 2375 ms — **Finacle inferred wait**
- `B_resp.ms` ≈ 30 ms — Postilion outbound is fine
- `slowest_hop.hop` = `"D"`
- `A.hole` = true — we did not time the terminal itself
- `timeout` = false, `rc` = `"00"`

**One-sentence RCA:** delay is Segment D (Finacle interface time), not
Postilion switching and not (provably) the ATM.

Side tape if D is *also* a host incident:

```text
rmagent-linux  attest/sketch on the Finacle box   — load, new units
rmagent-so     attest on Postilion Windows        — is the FEP even sighted?
rmagent-at     appslow/appnet on Postilion        — process wedged / no TCP?
rmagent-fr     case.py open --ticket STAN-123456-RRN-123456789012
```

---

## 2. Timeout / likely reversal (debit may have posted)

```bash
python3 hunt.py trace --rings ../examples/rings --stan 654321 --rrn 654321000001
```

Expect:

- `timeout: true`
- `last_seen: "cba_0200"` — Finacle **received** the 0200; no 0210 on either tap
- `total_seen_ms: null`
- hops `D` and `B_resp` are holes (`missing-message`)

Localization: **not** “network to Postilion” (acq 0200 and cba 0200 both exist).
The hole starts **after Finacle ingress**. Channel vs core argument ends here
unless Finacle traces (out of scope, optional host pull) contradict.

`txnfail` lists this under `timeouts[]`.

---

## 3. Debit-without-dispense candidate

```bash
python3 hunt.py fail --rings ../examples/rings
```

STAN 123456 is in `debit_without_dispense_candidates` because:

1. EJ ring **is sighted** (40 other completions exist), and
2. this STAN has RC=00 at FEP and **no** EJ row.

Healthy STANs 100000–100039 are **not** listed.

If you delete `tap-term-ej.jsonl` and re-run, DWD list goes empty and the
note becomes “Segment A is a hole” — we refuse to call every approval a DWD.

**Not proof of no-cash.** Chargeback still needs ATM EJ / video. This skill
narrows the hop; it does not replace the journal.

---

## 4. Decline (not a timeout)

```bash
python3 hunt.py trace --rings ../examples/rings --stan 111222 --rrn 111222000051
```

`rc: "51"`, hops complete, `timeout: false`. Switch and Finacle answered;
this is a business decline, not a missing 0210.

---

## 5. What is “slow”? (`txnslow` + `txnbaseline`)

```bash
python3 hunt.py slow     --rings ../examples/rings --threshold-ms 800
python3 hunt.py baseline --rings ../examples/rings
```

`txnslow` returns 123456 first (`total_seen_ms` ≈ 2430).

`txnbaseline` needs **n ≥ 30** or it is a hole. Fixture has 40+ complete
journeys; D p50 should be well under 500 ms, so 2375 ms is not “normal”.

There is no ML warehouse. Percentiles + a hard floor. Same constitution as
the rmagent thinker.

---

## 6. Unknown STAN is a hole, not a clean bill

```bash
python3 hunt.py trace --rings ../examples/rings --stan 000000 --rrn 999999999999
```

`hole: true`, `reason: not-in-ring` — retention-boundary or never seen.

---

## 7. Ingest from tshark (lab)

Pack one message, pretend tshark emitted it:

```bash
python3 - <<'PY'
from decode import pack_financial
b = pack_financial(mti="0200", stan="777777", rrn="777777000001",
                   pan="5060990012345678", amount="000000001000", tid="ATM9")
print("1.0\t10.10.1.10\t5000\t10.10.2.20\t5000\t" + b.hex())
PY
# pipe that line to:
# python3 ingest.py --tap tap-fep-acq --ring /tmp/tap-fep-acq.jsonl
```

Then `grep 5060990012345678 /tmp/tap-fep-acq.jsonl` must be empty.

---

## 8. What NOT to run as “the use case”

| Command | Why it is the wrong plane |
|---|---|
| rmagent-so `edges` / `attackmap` | identity, not ISO |
| rmagent-at `appslow` alone | HTTP.sys/.NET, not MTI 0200 |
| rmagent-fr `hunt.py` without a tap | ticket tape of the investigation, no hop ms |
| `tcpdump -w /data/all.pcap` forever | a lake; this skill forbids it |

Use those **beside** a STAN pull when the hop math says “Finacle waited” and
you need to know if the box was in a reboot, blind, or under incident.
