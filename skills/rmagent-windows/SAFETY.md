# SAFETY — read before you knock

This skill runs remote commands on production Windows servers. The guardrails below are enforced in code where possible and by discipline everywhere else. Break one and you have rebuilt the warehouse, or become the worm.

## The allowlist is the contract

`ask()` accepts only `attest`, `sketch`, `edges`, `explain`. `actuate` is refused outright:

```python
if skill == "actuate":
    return {"ok": False, "error": "actuate is off in Phase 0 (watch only)", "hole": ...}
```

There is no god-shell. There is no `run_any`. There is no CIM second door. If you need to isolate a host, that is EDR + a human, not RMAgent.

## Caps that stop you becoming a lake

| Cap | Value | Enforced |
|---|---|---|
| Max pull per answer | 32 KB | `lib._cap()` — oversized → hole, not stored |
| Ask timeout | 25 s | `ASK_TIMEOUT_SEC` |
| Explain timeout | 15 min | `EXPLAIN_TIMEOUT_SEC` |
| Census concurrency | 3 | `MAX_CONCURRENT_ATTEND` (BoundedPool) |
| Hunt concurrency | 2 | `MAX_CONCURRENT` |
| Walk depth / fan-out | 8 / 3 | constants; honour in Hunter |
| Cooldown per identity | 5 min | `COOLDOWN_SEC` |

## Credentials

- Env (`RMAgent_<ID>_USER` / `RMAgent_<ID>_PASS`) or `~/.rmagent/creds.json` (mode 600).
- **Never** in the inventory file, the case folder, a slide, or a commit.
- `creds_for()` resolves them without printing. If absent, it errors loudly rather than prompting inline.
- `chmod 600 ~/.rmagent/creds.json` (macOS/Linux) or restrict via Windows ACL (Windows) — only the jump-host user may read it. Add `~/.rmagent/` to `.gitignore`.

## Holes, not silence

A silent host is `{asked, empty, why}`. Do not tight-retry — you risk an account lockout and you look like the attacker. One ask, 25 s, write the hole. Two missed attests (across runs) = Critical.

## Estate boundary

Only WS1/WS2 (or boxes the operator is authorised to administer). A box you do not run — NIBSS, a partner, a scheme, an unmanaged phone — is a **hole**, not a witness. Do not invent a witness because an API or a port exists.

## What is off the table in Phase 0

- Isolate / disable / revoke (no `actuate`).
- Copying `Security.evtx` or any full log dump home.
- A pool of 20, or a second unmanaged door beside WinRM.
- Inventing a parent/hop when a witness is silent.
- Pretending a partner box is on your map.

## If the jump host is stolen

A stolen jump host is itself a case. Every door-opening `ask()` is recorded to `asks.jsonl` on the case — so the walk is visible after the fact. Rotate `RMAgent_*_PASS` immediately and open a case against the jump host itself.
