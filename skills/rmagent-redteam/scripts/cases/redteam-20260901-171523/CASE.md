# Case redteam-20260901-171523

Track: ['Administrator', 'SYSTEM']
Window: 1h

## Hops

- 01 ws1 · edges → {'plane': 'endpoint', 'witness': 'ws1', 'skill': 'edges', 'logons': 8, 'explicit_creds': 0, 'special_privs': 0, 'conns': 0, 't': '2026-09-01T16:16:00.3285460Z'}
- 01 ws1 · explain → {'plane': 'endpoint', 'witness': 'ws1', 'skill': 'explain', 'group_changes': 3, 'service_events': 3, 'task_events': 3, 'wmi_subscriptions': 0, 'audit_cleared': 0, 'proc_spawns': 20, 'lolbin_spawns': 20, 't': '2026-09-01T16:16:03.9259719Z'}
- 01 ws1 · pslogs → {'plane': 'endpoint', 'witness': 'ws1', 'skill': 'pslogs', 'blocks': 8, 't': '2026-09-01T16:16:07.4093418Z'}
- 01 ws1 · kernring → {'plane': 'endpoint', 'witness': 'ws1', 'skill': 'kernring', 'procs': 0, 'burst_seconds': 10, 'sysmon_status': 'Sysmon64=Running', 't': '2026-09-01T16:16:20.5687647Z'}
- 01 ws1 · attackmap → {'plane': 'endpoint', 'witness': 'ws1', 'skill': 'attackmap', 'checked': 13, 'found': 2, 't': '2026-09-01T16:16:24.5709460Z'}
- 02 ws2 · edges → {'plane': 'data', 'witness': 'ws2', 'skill': 'edges', 'logons': 8, 'explicit_creds': 0, 'special_privs': 0, 'conns': 0, 't': '2026-09-01T16:16:36.4491250Z'}
- 02 ws2 · explain → {'plane': 'data', 'witness': 'ws2', 'skill': 'explain', 'group_changes': 3, 'service_events': 3, 'task_events': 3, 'wmi_subscriptions': 0, 'audit_cleared': 0, 'proc_spawns': 20, 'lolbin_spawns': 20, 't': '2026-09-01T16:16:40.2412329Z'}
- 02 ws2 · pslogs → {'plane': 'data', 'witness': 'ws2', 'skill': 'pslogs', 'blocks': 8, 't': '2026-09-01T16:16:43.6787493Z'}
- 02 ws2 · kernring → {'plane': 'data', 'witness': 'ws2', 'skill': 'kernring', 'procs': 0, 'burst_seconds': 10, 'sysmon_status': 'Sysmon=Running', 't': '2026-09-01T16:16:56.8547013Z'}
- 02 ws2 · attackmap → {'plane': 'data', 'witness': 'ws2', 'skill': 'attackmap', 'checked': 13, 'found': 2, 't': '2026-09-01T16:17:01.0706162Z'}

## Holes

(none — every door answered)