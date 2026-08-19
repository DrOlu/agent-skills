# Live example — responding to the WS1 brute-force attack

This is the real, end-to-end use of `rmagent-actuate` against the live finding
from the 2026-08-19 session. Everything below was executed against WS1.

## The finding (Phase 0)

`rmagent-windows` hunts and `attest` checks surfaced a sustained brute-force
attack against the Administrator account on WS1:

```
17:19:32 user=ADMINISTRATOR src=95.142.115.12 type=3
17:17:25 user=ADMINISTRATOR src=95.142.115.12 type=3
17:15:11 user=ADMINISTRATOR src=95.142.115.12 type=3
17:13:05 user=ADMINISTRATOR src=95.142.115.12 type=3
# every ~2 minutes, sustained
```

The operator confirmed the IP was not theirs and not any known partner.

## The response (Phase 1)

### 1. Baseline first

```
$ actuate.py snapshot --inventory ~/estate.yaml --witness ws1
[snapshot] ws1:
  tasks=167 services=216 users=12 fw_rules=0
```

The journal now has a "before" picture: 167 tasks, 216 services, 12 users,
zero RMAgent firewall rules.

### 2. Dry-run (the default — nothing changes yet)

```
$ actuate.py block_ip --inventory ~/estate.yaml --witness ws1 \
    --target 95.142.115.12 \
    --reason "sustained 4625 brute-force against Administrator, every ~2min"

[dry-run] block_ip on ws1
  target : 95.142.115.12
  effect : Windows Firewall deny rule for a source IP
  undo   : unblock_ip
  reason : sustained 4625 brute-force against Administrator, every ~2min

  To apply: re-run with --apply
```

The operator reads exactly what will happen: one firewall rule, named after the
IP, reversible with `unblock_ip`.

### 3. Apply

```
$ actuate.py block_ip ... --apply

[apply] block_ip on ws1 target=95.142.115.12
  ok — {'action': 'block_ip', 'ip': '95.142.115.12',
        'rule': 'RMAgent-Block-95.142.115.12', 'status': 'created'}
  journal entry 3  verified=True
  undo later with: actuate.py undo --journal-entry 3 --inventory /Users/olu/estate.yaml
```

`verified=True` means the post-apply check ran: the rule exists and is enabled.
This is not "the command returned zero" — the skill went back and looked.

### 4. Verify with Phase 0

Over the following minutes, `census` on WS1 shows `admin_fail_60s` dropping
toward zero as the blocked source's attempts stop reaching the auth stack.

### 5. The journal tells the whole story

```
$ actuate.py journal

  1 ✓ 2026-08-19T21:48:44Z  ws1   snapshot          (baseline)
  2 · 2026-08-19T21:49:02Z  ws1   block_ip  95.142.115.12  undo=unblock_ip 95.142.115.12
      reason: sustained 4625 brute-force against Administrator, every ~2min
  3 ✓ 2026-08-19T21:49:21Z  ws1   block_ip  95.142.115.12  undo=unblock_ip 95.142.115.12
      reason: sustained 4625 brute-force against Administrator, every ~2min
```

Read aloud in an incident review: *"We took a baseline, we considered blocking
the IP (entry 2, dry-run), we blocked it (entry 3, verified), and here is why."*

### 6. If it had been wrong

```
$ actuate.py undo --journal-entry 3 --inventory ~/estate.yaml

[undo] reversing entry 3: unblock_ip 95.142.115.12 on ws1
  ok — {'action': 'unblock_ip', 'ip': '95.142.115.12',
        'rule': 'RMAgent-Block-95.142.115.12', 'status': 'removed'}
  undone. verified=True
```

(This exact undo path was tested with a second IP — apply, verify, undo, verify
— and worked end to end.)

## What made this safe

- The action was **named** (`block_ip`), not a command — no shell, no injection surface.
- The operator **saw the dry-run** before anything changed.
- The block was **scoped to one IP** on one box — not a subnet, not the fleet.
- The action was **journaled with its reason** — defensible in any review.
- The reversal was **tested before it was needed**.

## Follow-up actions for this incident

1. Block the same IP on WS2 (it targets WS1's exposure, but defence in depth).
2. Audit WS1's Administrator logons for any *successful* auth from an
   unrecognized source (`edges` question, read the source IPs).
3. Restrict WinRM :5985 and SSH :22 to the jump host's address at the AWS
   security group — removes the entire class of attempt.
4. Consider the second observed source (`98.97.76.7`) — verify it's yours
   before deciding whether to block.
