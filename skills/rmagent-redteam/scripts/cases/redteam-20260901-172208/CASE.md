# Case redteam-20260901-172208

Track: ['Administrator', 'SYSTEM']
Window: 1h

## Hops

- 01 ws1 · edges → {'plane': 'endpoint', 'witness': 'ws1', 'skill': 'edges', 'logons': 8, 'explicit_creds': 0, 'special_privs': 0, 'conns': 0, 't': '2026-09-01T16:22:47.2647600Z'}
- 01 ws1 · explain → {'plane': 'endpoint', 'witness': 'ws1', 'skill': 'explain', 'group_changes': 3, 'service_events': 3, 'task_events': 3, 'wmi_subscriptions': 0, 'audit_cleared': 0, 'proc_spawns': 20, 'lolbin_spawns': 20, 't': '2026-09-01T16:22:50.8121422Z'}
- 01 ws1 · pslogs → {'plane': 'endpoint', 'witness': 'ws1', 'skill': 'pslogs', 'blocks': 8, 't': '2026-09-01T16:22:54.5172988Z'}
- 01 ws1 · kernring → {'plane': 'endpoint', 'witness': 'ws1', 'skill': 'kernring', 'procs': 0, 'burst_seconds': 10, 'sysmon_status': 'Sysmon64=Running', 't': '2026-09-01T16:23:07.7626916Z'}
- 01 ws1 · attackmap → {'plane': 'endpoint', 'witness': 'ws1', 'skill': 'attackmap', 'checked': 13, 'found': 2, 't': '2026-09-01T16:23:11.8359414Z'}
- 02 ws2 · edges → {'plane': 'data', 'witness': 'ws2', 'skill': 'edges', 'logons': 8, 'explicit_creds': 0, 'special_privs': 0, 'conns': 0, 't': '2026-09-01T16:23:24.8139320Z'}
- 02 ws2 · explain → {'plane': 'data', 'witness': 'ws2', 'skill': 'explain', 'group_changes': 3, 'service_events': 3, 'task_events': 3, 'wmi_subscriptions': 0, 'audit_cleared': 0, 'proc_spawns': 20, 'lolbin_spawns': 20, 't': '2026-09-01T16:23:28.5951735Z'}
- 02 ws2 · pslogs → {'plane': 'data', 'witness': 'ws2', 'skill': 'pslogs', 'blocks': 8, 't': '2026-09-01T16:23:32.2514229Z'}
- 02 ws2 · kernring → {'plane': 'data', 'witness': 'ws2', 'skill': 'kernring', 'procs': 0, 'burst_seconds': 10, 'sysmon_status': 'Sysmon=Running', 't': '2026-09-01T16:23:45.3978226Z'}
- 02 ws2 · attackmap → {'plane': 'data', 'witness': 'ws2', 'skill': 'attackmap', 'checked': 13, 'found': 2, 't': '2026-09-01T16:23:49.1478482Z'}

## Holes

(none — every door answered)