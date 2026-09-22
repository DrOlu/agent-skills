# Case redteam-detect-20260901-154057

Track: ['Administrator', 'SYSTEM']
Window: 1h

## Hops

- 01 ws1 · edges → {'plane': 'endpoint', 'witness': 'ws1', 'skill': 'edges', 'logons': 8, 'explicit_creds': 0, 'special_privs': 0, 'conns': 0, 't': '2026-09-01T14:41:41.9164920Z'}
- 01 ws1 · explain → {'plane': 'endpoint', 'witness': 'ws1', 'skill': 'explain', 'group_changes': 3, 'service_events': 3, 'task_events': 3, 'wmi_subscriptions': 0, 'audit_cleared': 0, 'proc_spawns': 20, 'lolbin_spawns': 20, 't': '2026-09-01T14:41:45.7633160Z'}
- 01 ws1 · pslogs → {'plane': 'endpoint', 'witness': 'ws1', 'skill': 'pslogs', 'blocks': 8, 't': '2026-09-01T14:41:49.0128343Z'}
- 01 ws1 · kernring → {'plane': 'endpoint', 'witness': 'ws1', 'skill': 'kernring', 'procs': 0, 'burst_seconds': 10, 'sysmon_status': 'Sysmon64=Running', 't': '2026-09-01T14:42:02.4797121Z'}
- 01 ws1 · attackmap → {'plane': 'endpoint', 'witness': 'ws1', 'skill': 'attackmap', 'checked': 13, 'found': 2, 't': '2026-09-01T14:42:06.2346231Z'}
- 02 ws2 · edges → {'plane': 'data', 'witness': 'ws2', 'skill': 'edges', 'logons': 8, 'explicit_creds': 0, 'special_privs': 0, 'conns': 0, 't': '2026-09-01T14:42:18.3827770Z'}
- 02 ws2 · explain → {'plane': 'data', 'witness': 'ws2', 'skill': 'explain', 'group_changes': 3, 'service_events': 3, 'task_events': 3, 'wmi_subscriptions': 0, 'audit_cleared': 0, 'proc_spawns': 20, 'lolbin_spawns': 20, 't': '2026-09-01T14:42:22.3514728Z'}
- 02 ws2 · pslogs → {'plane': 'data', 'witness': 'ws2', 'skill': 'pslogs', 'blocks': 8, 't': '2026-09-01T14:42:25.5837669Z'}
- 02 ws2 · kernring → {'plane': 'data', 'witness': 'ws2', 'skill': 'kernring', 'procs': 0, 'burst_seconds': 10, 'sysmon_status': 'Sysmon=Running', 't': '2026-09-01T14:42:38.9261696Z'}
- 02 ws2 · attackmap → {'plane': 'data', 'witness': 'ws2', 'skill': 'attackmap', 'checked': 13, 'found': 2, 't': '2026-09-01T14:42:42.7543615Z'}

## Holes

(none — every door answered)