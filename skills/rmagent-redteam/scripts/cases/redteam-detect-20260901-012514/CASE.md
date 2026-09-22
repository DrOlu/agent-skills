# Case redteam-detect-20260901-012514

Track: ['Administrator', 'SYSTEM']
Window: 1h

## Hops

- 01 ws1 · edges → {'plane': 'endpoint', 'witness': 'ws1', 'skill': 'edges', 'logons': 8, 'explicit_creds': 0, 'special_privs': 0, 'conns': 0, 't': '2026-09-01T00:25:53.3563543Z'}
- 01 ws1 · explain → {'plane': 'endpoint', 'witness': 'ws1', 'skill': 'explain', 'group_changes': 3, 'service_events': 3, 'task_events': 3, 'wmi_subscriptions': 1, 'audit_cleared': 0, 'proc_spawns': 20, 'lolbin_spawns': 20, 't': '2026-09-01T00:25:57.5395630Z'}
- 01 ws1 · pslogs → {'plane': 'endpoint', 'witness': 'ws1', 'skill': 'pslogs', 'blocks': 8, 't': '2026-09-01T00:26:01.5805125Z'}
- 01 ws1 · kernring → {'plane': 'endpoint', 'witness': 'ws1', 'skill': 'kernring', 'procs': 0, 'burst_seconds': 10, 'sysmon_status': 'Sysmon64=Running', 't': '2026-09-01T00:26:15.4661566Z'}
- 01 ws1 · attackmap → {'plane': 'endpoint', 'witness': 'ws1', 'skill': 'attackmap', 'checked': 13, 'found': 1, 't': '2026-09-01T00:26:19.7723929Z'}
- 02 ws2 · edges → {'plane': 'data', 'witness': 'ws2', 'skill': 'edges', 'logons': 8, 'explicit_creds': 0, 'special_privs': 0, 'conns': 0, 't': '2026-09-01T00:26:33.8586928Z'}
- 02 ws2 · explain → {'plane': 'data', 'witness': 'ws2', 'skill': 'explain', 'group_changes': 3, 'service_events': 3, 'task_events': 3, 'wmi_subscriptions': 1, 'audit_cleared': 0, 'proc_spawns': 20, 'lolbin_spawns': 20, 't': '2026-09-01T00:26:38.5261550Z'}
- 02 ws2 · pslogs → {'plane': 'data', 'witness': 'ws2', 'skill': 'pslogs', 'blocks': 8, 't': '2026-09-01T00:26:42.5600373Z'}
- 02 ws2 · kernring → {'plane': 'data', 'witness': 'ws2', 'skill': 'kernring', 'procs': 0, 'burst_seconds': 10, 'sysmon_status': 'Sysmon=Running', 't': '2026-09-01T00:26:56.4635854Z'}
- 02 ws2 · attackmap → {'plane': 'data', 'witness': 'ws2', 'skill': 'attackmap', 'checked': 13, 'found': 1, 't': '2026-09-01T00:27:01.0731792Z'}

## Holes

(none — every door answered)