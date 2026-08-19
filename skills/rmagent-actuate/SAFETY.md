# SAFETY — rmagent-actuate

This is the skill that changes hosts. Read this before running anything with `--apply`.

## The safety case in one line

Every action is **named** (allowlist), **shown** (dry-run default), **journaled**
(with its undo), and **verified** (post-apply check). If any of those four is
missing, the skill refuses to run.

## Why each gate exists

| Gate | What it prevents |
|---|---|
| Allowlist (`ACTIONS` dict) | Arbitrary command execution. There is no passthrough — a typo'd action name is a CLI error, not a shell. |
| `--dry-run` default | An agent (or a tired human) running something destructive by accident. You must type `--apply` to mutate. |
| `--reason` required | Unexplained actions. The journal is the audit trail; an entry without a reason is an entry you can't defend in a review. |
| Journal + undo spec | "We did something and can't remember what." Every applied entry records how to reverse itself. |
| Post-apply verify | Silent failures. `block_ip` that didn't actually create the rule is worse than no rule — you *think* you're protected. |
| `snapshot` habit | Acting without a baseline. The journal always has a "before" picture. |

## What is deliberately NOT in the allowlist

- **No account deletion.** `disable_user` disables. Deletion destroys forensic
  evidence and cannot be undone. If you need the account gone, do it manually,
  deliberately, after forensics.
- **No log clearing or modification.** Nothing in this skill touches event logs.
  Clearing logs is the attacker's move (1102); it will never be ours.
- **No host isolation / network disconnect.** That's the EDR's job, and doing it
  from a pull-based agent risks locking yourself out. If you need isolation,
  use the EDR or the hypervisor console.
- **No registry edits, no service deletion, no file deletion.** `stop_service`
  stops and disables — the service object remains. `quarantine_file` adds a
  deny ACL — the file remains. Everything stays reversible.
- **No scheduled-task creation.** Deleting tasks is a response; creating them is
  persistence, and this skill must never look like the thing it hunts.

## The kill_process exception

`kill_process` cannot be undone — a killed process stays killed. It is in the
allowlist anyway because a live malicious process is an emergency where
irreversibility is the point. The mitigation: the payload captures the process
**name, owner, and full command line** into the journal *before* it kills, so the
evidence survives the action. Read the journal entry, not the process.

## Blast-radius rules

- One witness, one target, one action per invocation. No batch modes, no
  "apply to all boxes." If three boxes need the same block, that's three
  deliberate commands.
- Targets are specific: an IP, not a subnet; a user, not a group; a service
  name, not a wildcard.
- `block_ip` creates a rule named `RMAgent-Block-<ip>` — only rules with that
  prefix are ever removed by `unblock_ip`. The skill cannot delete firewall
  rules it didn't create.

## If something goes wrong

1. `actuate.py journal` — see exactly what was done, in order.
2. `actuate.py undo --journal-entry N --inventory ...` — reverse it.
3. If the undo fails, the journal entry has the `result_detail` (task XML, WMI
   query, process cmdline) to reconstruct manually.
4. The journal is append-only. Nothing is ever erased. Even a mistake leaves
   its full story.

## Authorised use only

Same estate rule as Phase 0: boxes you administer, in the inventory. Running
this against a partner's box, production you don't own, or anything you can't
defend in an incident review is a misuse of the skill, not a clever use.
