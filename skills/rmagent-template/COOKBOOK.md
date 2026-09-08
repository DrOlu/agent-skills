# Domain cookbook — grain, sensor, questions, holes

One grain per skill. Specialize from this table; do not merge planes.

## Family map (what already exists)

| Skill | Plane | Grain | Sensor | Door |
|---|---|---|---|---|
| rmagent-so / windows | SecOps | principal + LogonId | Security, Sysmon | winrm |
| rmagent-linux | SecOps | root / sudoers | journald, sshd | ssh |
| rmagent-fr | Reliability | ticket | (joins others) | n/a |
| rmagent-at | App / sysops | request-ish | ETW AutoLogger | winrm |
| rmagent-ao | AgentOps | host, agent, session | proc + transcripts + APIs | ssh/winrm |
| rmagent-iso | Payments | STAN+RRN | SPAN → JSONL ring | ring |
| rmagent-redteam | Purple | drill artifact | stages so-signals | winrm |

## Starters for new planes

### NetOps — `rmagent-net`

- **Sentence:** Follow one `circuit_id` (or 5-tuple window) across PE routers
  without a NetFlow warehouse.
- **Sensor:** SNMP GET of a **fixed OID list**; syslog JSONL circular ring on
  the collector you run. ERSPAN only if decoded to flow records then discarded.
- **Questions:** `netattest`, `netfail`, `netedges` (capped talkers),
  `netbaseline` (n≥30), optional `nethops` from existing telemetry.
- **Holes:** SNMP timeout = blind; no SPAN on that VLAN; encrypted control
  plane you do not terminate.
- **Must not:** `tcpdump -w`, campus CAM table, ping floods, DPI lake.
- **Side tape:** `rmagent-so` if the box was compromised; `netops` skill for
  how to plant SPAN.

### DevOps / platform — `rmagent-plat`

- **Sentence:** Follow one `deploy_id` / git sha across the cluster you
  administer without a log warehouse.
- **Sensor:** kube API allowlisted GETs; systemd unit files; CI runner
  artifacts **on disk you own**.
- **Questions:** `platattest` (API + NotReady), `platsketch` (CrashLoop,
  ImagePullBackoff, new ClusterRoleBinding), `plattrace` (one ReplicaSet),
  `platfail`, `platdrift`.
- **Holes:** no kubeconfig; RBAC cannot list events; secrets-only namespaces.
- **Must not:** `kubectl logs -A`, etcd snapshot home, helm values with secrets.

### Datacenter / sysops — `rmagent-dc`

- **Sentence:** Follow one `asset_tag` across BMC/PDU without an SEL lake.
- **Sensor:** Redfish/IPMI **GET allowlist**; PDU SNMP; SMART parsed.
- **Questions:** `dcatest` (power, inlet, PSU redundancy), `dcfail`
  (predictive, lost redundancy), `dcbaseline` (temp p95).
- **Holes:** BMC unreachable; vendor Redfish subset; no read community.
- **Must not:** firmware flash, locate-LED as a toy, full SEL export.

### MLOps — `rmagent-ml`

- **Sentence:** Follow one `job_id` on GPU nodes without a metrics warehouse.
- **Sensor:** scheduler API; `nvidia-smi -q` parsed; artifact **mtimes**
  (not weights).
- **Questions:** `mlattest`, `mlslow` (step vs baseline), `mlfail` (OOM if
  already in the job log), `mldrift` (new model files).
- **Holes:** MIG partitions you cannot see; job log rotated.
- **Must not:** `.pt` / `.safetensors` copy, dataset dump, wandb export.

### AIOps — not a sensor skill

Do **not** create `rmagent-aiops` that slurps everything into a model.
AIOps here = `thinker.py` over **census history** (cliffs, silence,
z-score, n≥30). Attach thinker to so/iso/net — do not add a 15th lake.

### CloudOps — `rmagent-cloud` (careful)

- Grain: `(account_id, resource_arn)` you **tenant**.
- Sensor: CloudTrail / Activity log **already in the account**, pulled
  capped (LookupEvents with a filter), never org-wide dump.
- Hole: account you do not own; GovCloud without creds.
- Must not: become CloudTrail Lake with extra steps.

### DatabaseOps — `rmagent-db`

- Grain: `(wait_event, session_id, query_id)` — **never** bind parameters
  with PII.
- Sensor: `pg_stat_activity` / SQL Server DMVs **allowlisted columns**.
- Questions: `dbattest` (connections, oldest xact), `dbslow` (wait ≥ X),
  `dbfail` (blocked, rollback).
- Must not: `SELECT * FROM customers`, full plan cache dump.

### IdentityOps (beyond Windows) — `rmagent-id`

- Grain: `(idp, subject, session_id)`.
- Sensor: IdP audit API you tenant, capped.
- Hole: SaaS you do not tenant.
- Must not: hash dumps, refresh tokens in cases.

## Pairing (side tape)

When hop math says “the box was slow,” add the **host** skill, do not
extend the grain:

| Localized hop | Side tape |
|---|---|
| Windows process / TCP | rmagent-at, rmagent-so |
| Linux load / new unit | rmagent-linux |
| Ticket / investigation | rmagent-fr case |
| LLM child processes | rmagent-ao |
| ISO STAN | rmagent-iso |
| Circuit / BGP | rmagent-net (clone) |

## Naming

```
rmagent-<short-plane>
```

Examples: `rmagent-net`, `rmagent-plat`, `rmagent-dc`, `rmagent-ml`,
`rmagent-db`. Do not `rmagent-observability-platform-v2`.
