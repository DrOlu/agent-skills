# Parameters — the intake questionnaire

Collect EVERY value below before installing. Mark each as GIVEN (from the
operator) or ASKED (you requested it and got an answer). **Stop and ask** when a
REQUIRED value is absent. Never default a credential, URL, fingerprint, path or
port.

---

## A. Central NATS server (the exchange)

The operator normally provides this. Document all of it.

| # | Parameter | Env var | Required | Notes / how to ask |
|---|---|---|---|---|
| A1 | Server URL(s) | `NATS_URL` | YES | e.g. `tls://nats.example.africa:4222`. Ask: "What is the NATS endpoint (host:port) and is it TLS?" |
| A2 | TLS mode | — | YES | `tls://` (production) vs `nats://` (dev only). If TLS: server CA/hostname needed. |
| A3 | Auth method | `NATS_AUTH` | YES | one of `creds` (JWT+seed file), `nkey` (seed file), `userpass`, `anonymous` (dev only). Ask which. |
| A4 | Credentials file | `NATS_CREDS` | if creds | path to a `.creds` file; keep `0600`, never in git |
| A5 | NKey seed file | `NATS_NKEY` | if nkey | per-agent seed; public key goes in the server config |
| A6 | Account(s) | `NATS_ACCOUNT` | recommended | `LOCAL` (JetStream on) for agents; `REMOTE` for leaf nodes; `SYS` for system |
| A7 | JetStream | — | YES if durable tasks/mailbox | version ≥ 2.10; ask the operator to confirm `jetstream { store_dir: … }` is a persistent path |
| A8 | Monitoring URL | `NATS_MON` | recommended | `http://nats.example.africa:8222` — needed by the doctor and for `jsz`/`connz` checks |
| A9 | WebSocket URL | — | optional | `wss://nats.example.africa:8443` for browser/home agents |
| A10 | Leaf-node acceptor | — | for cross-network | ask whether the central server accepts leaf nodes and on which port |
| A11 | Max payload | — | optional | default 1 MiB; raise only for large file transfer and note the change |
| A12 | Region / residency | — | recommended | data-residency constraints (e.g. Nigeria NDPA, CBN in-country rules) — affects where the server and JetStream store live |

### Central server acceptance checks (run before trusting it)

```bash
nats --server tls://nats.example.africa:4222 --creds "$NATS_CREDS" server check connection
curl -s "$NATS_MON/varz" | jq '{version,jetstream,max_payload,uptime}'
curl -s "$NATS_MON/jsz"  | jq '{api: .api.errors, streams: (.streams|length)}'
```

---

## B. Per-edge (each host that joins the mesh)

| # | Parameter | Env var | Required | Notes |
|---|---|---|---|---|
| B1 | Mesh identity | `GATEWAY_MESH_ID` | YES | `reactorpro/<short-name>`, e.g. `reactorpro/lagos-01`. Fixed once minted. |
| B2 | Gateway token | `LIVEAGENT_GATEWAY_TOKEN` | YES | bearer token for `:3000`; generate strong, keep `0600` |
| B3 | Gateway REST/UI port | — | YES | default `3000`; ask if it collides |
| B4 | Data dir | — | YES | gateway SQLite + identity file location; persistent disk |
| B5 | Peer fingerprints | `MESH_TRUSTED_PEERS` | YES | comma-separated `sha256:<16hex>` of every peer; exchanged out of band |
| B6 | Verify mode | — | YES | `-mesh-verify-mode=require`, `-mesh-trust-on-first-use=false` |
| B7 | Butler skill name | — | YES | `butler.query` / `coronation.query` / `neuralos.query` / custom |
| B8 | Butler service name | — | YES | launchd label / systemd unit / NSSM service name |
| B9 | Service account | — | YES | the OS user the services run as (least privilege; needs read access to the data source) |
| B10 | `NEEDLE_ENGINE_DIR` | `NEEDLE_ENGINE_DIR` | YES | folder holding the engine binary + weights |
| B11 | Engine binary name | — | YES | `needle`/`needle.exe` OR `neural`/`neural.exe` (interchangeable) |
| B12 | Weights file name | — | YES | `needle3.cact` OR `neuralOS.engine` (interchangeable, ~35 MB) |
| B13 | Menu path | — | YES | `needle_menu.json` beside the harness |
| B14 | Data source + creds | — | YES | DSN/host/db/user/password or API endpoint; read-only role strongly preferred |
| B15 | Python runtime | — | YES | path to the interpreter the harness runs under (3.11+); Windows often `C:\Python314\python.exe` |
| B16 | Time sync | — | YES | NTP reachable; envelopes are refused outside the ±5 min clock window |

### Network requirements per edge

- **Outbound only** to `NATS_URL` (and to the central server's monitoring port if
  you use it). No inbound ports for agents. The gateway's `:3000` is usually
  localhost-only (see C4).
- **DNS** resolution for the central server hostname.
- **Bandwidth/latency budget:** a grounded answer costs a few KB plus the
  round trip; measure before promising SLAs (see `references/operate.md`).
- **Intermittent links:** NATS reconnects with backoff automatically; JetStream
  durability covers gaps for the mailbox/task surfaces. Note the expected
  outage pattern (e.g. last-mile outages, generator windows).

---

## C. Policy / operator decisions

| # | Decision | Default recommendation |
|---|---|---|
| C1 | Cross-organisation? | If yes: separate NATS accounts + explicit fingerprint pins + `require` mode on both sides |
| C2 | Allow remote invoke? | `on` for trusted peers only; leave MeshSend off between headless edges |
| C3 | Which skills are exposed? | allowlist exactly the butler skills; never `all` across an org boundary |
| C4 | Expose the gateway REST port? | keep `:3000` bound to localhost/private unless a trusted network requires otherwise |
| C5 | Mailbox (durable, no reply) | `on` when peers are intermittently offline |
| C6 | Task retention | default 7 d; longer only with a storage budget |
| C7 | Secrets handling | credentials live in `0600` files / a secret store, never in service unit files or git |
| C8 | Audit | every write probe appends to the instance audit log; keep it and ship it to central logging |

---

## D. Ask-back protocol

When a value is missing, ask exactly this way — one message, grouped, with the
reason it is needed:

```
To deploy edge <name> I still need:
  1) NATS endpoint + TLS? + auth method (creds/nkey/userpass)
     -> needed to connect the edge to the central exchange
  2) This edge's mesh id and its <n> peer fingerprints
     -> needed to sign and pin trust; without them invoke is refused (3004)
  3) The butler skill name + the data source DSN and its read-only credentials
     -> needed to ground answers; the edge cannot serve without them
  4) Service account, install paths, and NEEDLE_ENGINE_DIR for this host
     -> needed to install the engine and wire reboot-surviving services
```

Never proceed on assumed values; a wrong fingerprint or endpoint produces
failures that look like engine faults but are trust/transport faults.