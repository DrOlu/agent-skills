# Case redteam-20260820-180354

Track: ['Administrator', 'SYSTEM']
Window: 1h

## Hops

- 01 ws1 · edges → {'plane': 'endpoint', 'witness': 'ws1', 'skill': 'edges', 'logons': 50, 'explicit_creds': 0, 'special_privs': 0, 'conns': 0, 't': '2026-08-20T17:04:20.0259218Z'}
- 01 ws1 · pslogs → {'plane': 'endpoint', 'witness': 'ws1', 'skill': 'pslogs', 'blocks': 50, 't': '2026-08-20T17:04:28.5587806Z'}
- 02 ws2 · edges → {'plane': 'data', 'witness': 'ws2', 'skill': 'edges', 'logons': 0, 'explicit_creds': 0, 'special_privs': 0, 'conns': 0, 't': '2026-08-20T17:04:32.4040723Z'}
- 02 ws2 · pslogs → {'plane': 'data', 'witness': 'ws2', 'skill': 'pslogs', 'blocks': 50, 't': '2026-08-20T17:04:35.8176997Z'}

## Holes

- {"t": "2026-08-20T17:04:25Z", "asked": "ws1 explain", "empty": true, "why": "pull exceeded 32768 bytes"}