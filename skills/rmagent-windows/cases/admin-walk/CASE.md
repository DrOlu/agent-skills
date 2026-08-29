# Case admin-walk

Track: ['Administrator', 'SYSTEM']
Window: 2h

## Hops

- 01 ws1 · edges → {'plane': 'endpoint', 'witness': 'ws1', 'skill': 'edges', 'logons': 50, 'explicit_creds': 0, 'special_privs': 0, 'conns': 0, 't': '2026-08-20T16:57:47.5182358Z'}
- 01 ws1 · pslogs → {'plane': 'endpoint', 'witness': 'ws1', 'skill': 'pslogs', 'blocks': 50, 't': '2026-08-20T16:57:57.3071938Z'}
- 02 ws2 · edges → {'plane': 'data', 'witness': 'ws2', 'skill': 'edges', 'logons': 0, 'explicit_creds': 0, 'special_privs': 0, 'conns': 0, 't': '2026-08-20T16:58:01.1579808Z'}
- 02 ws2 · pslogs → {'plane': 'data', 'witness': 'ws2', 'skill': 'pslogs', 'blocks': 0, 't': '2026-08-20T16:58:04.0755277Z'}

## Holes

- {"t": "2026-08-20T16:57:55Z", "asked": "ws1 explain", "empty": true, "why": "pull exceeded 32768 bytes"}