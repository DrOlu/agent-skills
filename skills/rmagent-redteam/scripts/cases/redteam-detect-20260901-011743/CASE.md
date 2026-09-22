# Case redteam-detect-20260901-011743

Track: ['Administrator', 'SYSTEM']
Window: 1h

## Hops

- 01 ws1 · edges → {'plane': 'endpoint', 'witness': 'ws1', 'skill': 'edges', 'logons': 8, 'explicit_creds': 0, 'special_privs': 0, 'conns': 0, 't': '2026-09-01T00:18:22.4238285Z'}
- 01 ws1 · explain → {'plane': 'endpoint', 'witness': 'ws1', 'skill': 'explain', 'group_changes': 3, 'service_events': 3, 'task_events': 3, 'wmi_subscriptions': 1, 'audit_cleared': 0, 'proc_spawns': 20, 'lolbin_spawns': 20, 't': '2026-09-01T00:18:27.9711816Z'}
- 01 ws1 · pslogs → {'plane': 'endpoint', 'witness': 'ws1', 'skill': 'pslogs', 'blocks': 8, 't': '2026-09-01T00:18:32.8420290Z'}
- 01 ws1 · kernring → {'plane': 'endpoint', 'witness': 'ws1', 'skill': 'kernring', 'procs': 0, 'burst_seconds': 10, 'sysmon_status': 'Sysmon64=Running', 't': '2026-09-01T00:18:47.7431429Z'}
- 01 ws1 · attackmap → {'plane': 'endpoint', 'witness': 'ws1', 'skill': 'attackmap', 'checked': 13, 'found': 2, 't': '2026-09-01T00:18:54.1228753Z'}
- 02 ws2 · edges → {'plane': 'data', 'witness': 'ws2', 'skill': 'edges', 'logons': 8, 'explicit_creds': 0, 'special_privs': 0, 'conns': 0, 't': '2026-09-01T00:19:13.4309440Z'}
- 02 ws2 · explain → {'plane': 'data', 'witness': 'ws2', 'skill': 'explain', 'group_changes': 3, 'service_events': 3, 'task_events': 3, 'wmi_subscriptions': 1, 'audit_cleared': 0, 'proc_spawns': 20, 'lolbin_spawns': 20, 't': '2026-09-01T00:19:18.8395854Z'}
- 02 ws2 · pslogs → {'plane': 'data', 'witness': 'ws2', 'skill': 'pslogs', 'blocks': 8, 't': '2026-09-01T00:19:25.1860515Z'}
- 02 ws2 · kernring → {'plane': 'data', 'witness': 'ws2', 'skill': 'kernring', 'procs': 0, 'burst_seconds': 10, 'sysmon_status': 'Sysmon=Running', 't': '2026-09-01T00:19:41.5050852Z'}
- 02 ws2 · attackmap → {'plane': 'data', 'witness': 'ws2', 'skill': 'attackmap', 'checked': 13, 'found': 2, 't': '2026-09-01T00:19:47.3978594Z'}

## Holes

(none — every door answered)