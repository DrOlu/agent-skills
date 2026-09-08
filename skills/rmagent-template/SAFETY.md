# SAFETY — what every rmagent skill inherits

## Estate

Only boxes, taps, BMCs, clusters, and accounts the operator **administers**.
Partner, scheme, SaaS you do not tenant, phone, NIBSS → **hole**, not a
witness.

## Confirm flags

- Watch questions: no `--confirm` (they are read-only).
- Ring **setup** / AutoLogger / analytic logs: dry-run default, `--apply`.
- Red-team **stage**: `--confirm` required. Prefixed artifacts. `clean` exists.
- Actuate: not in this family of skills.

## Never

- Print credentials, PAN, PIN, API key values, prompt bodies, track2.
- Tight-retry a silent host.
- `scp` home evtx / pcap / journal / ETL.
- Disable EDR, auditd, Sysmon “to see better.”
- MITM a TLS link you do not terminate as a broker you own.
- Install a persistent agent “just this once.”

## Telegram / chat

Summaries only. No case dumps, no secrets, no event bodies.

## Drill artifacts

Prefix `RMAgentDrill_`. Benign payloads. Reversible. Coordinate with SOC if
EDR will fire — that is a feature.
