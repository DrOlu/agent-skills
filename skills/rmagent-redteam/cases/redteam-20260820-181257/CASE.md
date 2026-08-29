# Case redteam-20260820-181257

Track: ['Administrator', 'SYSTEM']
Window: 1h

## Hops

- 01 ws1 · edges → {'plane': 'endpoint', 'witness': 'ws1', 'skill': 'edges', 'logons': 8, 'explicit_creds': 0, 'special_privs': 0, 'conns': 0, 't': '2026-08-20T17:13:21.4917394Z'}
- 01 ws1 · pslogs → {'plane': 'endpoint', 'witness': 'ws1', 'skill': 'pslogs', 'blocks': 8, 't': '2026-08-20T17:13:30.8786584Z'}
- 02 ws2 · edges → {'plane': 'data', 'witness': 'ws2', 'skill': 'edges', 'logons': 0, 'explicit_creds': 0, 'special_privs': 0, 'conns': 0, 't': '2026-08-20T17:13:34.2695297Z'}
- 02 ws2 · pslogs → {'plane': 'data', 'witness': 'ws2', 'skill': 'pslogs', 'blocks': 8, 't': '2026-08-20T17:13:37.3235200Z'}

## Holes

- {"t": "2026-08-20T17:13:28Z", "asked": "ws1 explain", "empty": true, "why": "pull exceeded 32768 bytes"}